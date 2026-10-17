"""Run an assessment: create the records, execute the graph, record the outcome.

``POST /api/assessments`` returns a run_id immediately and this runs in a
background task inside the API process, so the wall-clock limit and every
failure path live here. Outcomes:

* COMPLETED — the graph finished. ``error_reason`` may carry a note (no
  obligations to assess, or why the memo is missing).
* CAPPED — a hard limit stopped the run: the call/token budget, or the wall
  clock. Findings persisted before the limit are kept.
* FAILED — a provider configuration error or an unexpected exception. The
  stored reason is safe to show; technical detail stays in the server log.

Single-process scope: a restart abandons in-flight runs, so startup marks
anything left PENDING/RUNNING as FAILED (``recover_interrupted_runs``) rather
than leaving it spinning forever in the UI.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import date

from app.ai.gateway import GatewayError, LLMGateway
from app.ai.graph.budget import CallBudget
from app.ai.graph.build import GRAPH_VERSION, build_graph
from app.ai.graph.nodes import GraphContext
from app.ai.graph.state import AssessmentState
from app.ai.graph.tracing import Tracer
from app.core.config import Settings, get_settings
from app.core.logging import bind_run_id, get_logger
from app.db.models.assessment import AgentRun, Assessment
from app.db.models.enums import AssessmentStatus
from app.db.session import get_sessionmaker
from app.repositories.agent_runs import AgentRunRepository
from app.repositories.assessments import AssessmentRepository

log = get_logger("app.services.assessment")

INTERRUPTED_REASON = (
    "Interrupted: the API process stopped while this assessment was running. "
    "Findings recorded before then are kept; start a new run to finish it."
)


class AssessmentInProgress(Exception):
    """A run with the same inputs is already PENDING or RUNNING."""

    def __init__(self, run_id: uuid.UUID) -> None:
        super().__init__(f"assessment {run_id} is already in progress")
        self.run_id = run_id


class ProviderUnavailable(Exception):
    """The configured provider cannot run (e.g. its API key is not set)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class RunOutcome:
    status: AssessmentStatus
    detail: str | None
    memo: str | None = None


async def create_assessment(
    circular_id: int,
    policy_pack_id: int,
    as_of: date | None = None,
    *,
    settings: Settings | None = None,
) -> uuid.UUID:
    """Create the assessment and its agent run; return the public run_id."""
    settings = settings or get_settings()
    ready, reason = settings.provider_readiness()
    if not ready:
        raise ProviderUnavailable(reason or "The assessment provider is not configured.")

    async with get_sessionmaker()() as session:
        assessments = AssessmentRepository(session)
        await assessments.lock_launch(circular_id, policy_pack_id)
        active = await assessments.find_active(circular_id, policy_pack_id, as_of)
        if active is not None:
            raise AssessmentInProgress(active.run_id)

        assessment = await assessments.add(
            Assessment(
                circular_id=circular_id,
                policy_pack_id=policy_pack_id,
                as_of_date=as_of,
                status=AssessmentStatus.PENDING,
            )
        )
        await AgentRunRepository(session).add(
            AgentRun(
                assessment_id=assessment.id,
                graph_version=GRAPH_VERSION,
                status=AssessmentStatus.PENDING,
                provider=settings.llm_provider,
                model=settings.effective_model,
            )
        )
        await session.commit()
        return assessment.run_id


async def run_assessment(run_id: uuid.UUID, settings: Settings | None = None) -> None:
    """Execute the graph for an assessment. Never raises into the caller."""
    settings = settings or get_settings()
    bind_run_id(str(run_id))

    async with get_sessionmaker()() as session:
        assessment = await AssessmentRepository(session).get_by_run_id(run_id)
        if assessment is None:
            log.error("assessment.not_found", extra={"run_id": str(run_id)})
            return
        agent_run = await AgentRunRepository(session).get_for_assessment(assessment.id)
        if agent_run is None:
            log.error("assessment.no_agent_run", extra={"run_id": str(run_id)})
            return
        assessment_id, agent_run_pk = assessment.id, agent_run.id
        initial: AssessmentState = {
            "assessment_id": assessment.id,
            "agent_run_id": agent_run.id,
            "circular_id": assessment.circular_id,
            "policy_pack_id": assessment.policy_pack_id,
            "as_of": assessment.as_of_date,
            "findings": [],
            "failed_tasks": 0,
        }
        await AssessmentRepository(session).set_status(assessment_id, AssessmentStatus.RUNNING)
        await AgentRunRepository(session).set_status(agent_run_pk, AssessmentStatus.RUNNING)
        await session.commit()

    budget = CallBudget(settings.max_assessment_calls, settings.max_assessment_tokens)
    ctx = GraphContext(
        gateway=LLMGateway(settings),
        settings=settings,
        tracer=Tracer(agent_run_pk),
        budget=budget,
    )
    outcome = await _execute(ctx, initial, run_id)
    await _finish(assessment_id, agent_run_pk, outcome, ctx)


async def _execute(ctx: GraphContext, initial: AssessmentState, run_id: uuid.UUID) -> RunOutcome:
    timeout = ctx.settings.assessment_timeout_seconds
    try:
        final = await asyncio.wait_for(build_graph(ctx).ainvoke(initial), timeout=timeout)
    except TimeoutError:
        return RunOutcome(
            AssessmentStatus.CAPPED,
            f"Stopped at the {timeout}s wall-clock limit. Findings recorded before then "
            "are kept; the memo was not written.",
        )
    except GatewayError as exc:
        log.exception("assessment.failed", extra={"run_id": str(run_id), "code": exc.code})
        return RunOutcome(
            AssessmentStatus.FAILED, f"{exc.human_message} (provider error: {exc.code})"
        )
    except Exception as exc:  # noqa: BLE001 - a failed run is stored, not raised
        log.exception("assessment.failed", extra={"run_id": str(run_id)})
        return RunOutcome(
            AssessmentStatus.FAILED,
            f"The assessment stopped on an unexpected {type(exc).__name__}. "
            f"The server log has details for run {run_id}.",
        )

    if ctx.budget.exhausted:
        return RunOutcome(
            AssessmentStatus.CAPPED,
            f"{ctx.budget.exhausted_reason} Findings recorded before the limit are kept; "
            "the memo was not written.",
        )
    if not final.get("obligations"):
        return RunOutcome(
            AssessmentStatus.COMPLETED,
            "This circular has no extracted obligations, so there was nothing to assess.",
        )
    return RunOutcome(AssessmentStatus.COMPLETED, final.get("memo_note"), final.get("memo"))


async def _finish(
    assessment_id: int, agent_run_pk: int, outcome: RunOutcome, ctx: GraphContext
) -> None:
    budget = ctx.budget
    async with get_sessionmaker()() as session:
        await AssessmentRepository(session).finish(
            assessment_id,
            outcome.status,
            detail=outcome.detail,
            memo=outcome.memo,
            tokens=budget.tokens,
            cost_usd=budget.cost_usd,
            unpriced_calls=budget.unpriced_calls,
            failed_tasks=ctx.failed_tasks,
        )
        await AgentRunRepository(session).finish(
            agent_run_pk,
            outcome.status,
            error=outcome.detail if outcome.status is not AssessmentStatus.COMPLETED else None,
            tokens=budget.tokens,
            cost_usd=budget.cost_usd,
        )
        await session.commit()
    log.info(
        "assessment.finished",
        extra={
            "status": outcome.status.value,
            "calls": budget.calls,
            "tokens": budget.tokens,
            "cost_usd": round(budget.cost_usd, 6),
            "unpriced_calls": budget.unpriced_calls,
            "failed_tasks": ctx.failed_tasks,
        },
    )


async def recover_interrupted_runs() -> int:
    """Fail runs a previous process left PENDING/RUNNING. Returns how many."""
    async with get_sessionmaker()() as session:
        assessment_ids = await AssessmentRepository(session).fail_unfinished(INTERRUPTED_REASON)
        await AgentRunRepository(session).fail_unfinished(INTERRUPTED_REASON)
        await session.commit()
    if assessment_ids:
        log.warning("assessment.interrupted_runs_failed", extra={"count": len(assessment_ids)})
    return len(assessment_ids)
