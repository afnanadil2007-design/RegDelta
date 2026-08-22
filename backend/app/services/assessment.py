"""Run an assessment: create the records, execute the graph, persist findings.

``POST /api/assessments`` returns a run_id immediately and this runs in a
background task, so the wall-clock timeout and the failure paths live here
rather than in the router.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date

from app.ai.gateway import GatewayError, LLMGateway
from app.ai.graph.build import GRAPH_VERSION, build_graph
from app.ai.graph.nodes import GraphContext
from app.ai.graph.state import AssessmentState, impact_of
from app.ai.graph.tracing import Tracer
from app.core.config import Settings, get_settings
from app.core.logging import bind_run_id, get_logger
from app.db.models.assessment import AgentRun, Assessment, Finding
from app.db.models.enums import AssessmentStatus
from app.db.session import get_sessionmaker
from app.repositories.agent_runs import AgentRunRepository
from app.repositories.assessments import AssessmentRepository, FindingRepository

log = get_logger("app.services.assessment")


async def create_assessment(
    circular_id: int, policy_pack_id: int, as_of: date | None = None
) -> uuid.UUID:
    """Create the assessment and its agent run; return the public run_id."""
    async with get_sessionmaker()() as session:
        assessment = await AssessmentRepository(session).add(
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
        circular_id = assessment.circular_id
        pack_id = assessment.policy_pack_id
        as_of = assessment.as_of_date

        await AssessmentRepository(session).set_status(assessment_id, AssessmentStatus.RUNNING)
        agent_run.status = AssessmentStatus.RUNNING
        await session.commit()

    ctx = GraphContext(
        gateway=LLMGateway(settings), settings=settings, tracer=Tracer(agent_run_pk)
    )
    graph = build_graph(ctx)

    initial: AssessmentState = {
        "assessment_id": assessment_id,
        "agent_run_id": agent_run_pk,
        "circular_id": circular_id,
        "policy_pack_id": pack_id,
        "as_of": as_of,
        "findings": [],
        "tokens_used": 0,
        "cost_usd": 0.0,
    }

    try:
        final = await asyncio.wait_for(
            graph.ainvoke(initial), timeout=settings.assessment_timeout_seconds
        )
    except TimeoutError:
        await _finish(
            assessment_id,
            agent_run_pk,
            AssessmentStatus.FAILED,
            error=f"Assessment exceeded the {settings.assessment_timeout_seconds}s wall clock.",
        )
        return
    except GatewayError as exc:
        # Provider failures get a short, secret-free reason for the analyst; the
        # full technical detail stays in the logs.
        log.exception("assessment.failed", extra={"run_id": str(run_id), "code": exc.code})
        await _finish(
            assessment_id,
            agent_run_pk,
            AssessmentStatus.FAILED,
            error=f"{exc.human_message} (provider error: {exc.code})",
        )
        return
    except Exception as exc:  # noqa: BLE001 - a failed run is stored, not raised
        log.exception("assessment.failed", extra={"run_id": str(run_id)})
        await _finish(
            assessment_id, agent_run_pk, AssessmentStatus.FAILED, error=str(exc)
        )
        return

    await _persist_findings(assessment_id, final)
    status = AssessmentStatus.CAPPED if final.get("capped") else AssessmentStatus.COMPLETED
    await _finish(
        assessment_id,
        agent_run_pk,
        status,
        error=final.get("cap_reason"),
        memo=final.get("memo"),
        tokens=int(final.get("tokens_used", 0)),
        cost=float(final.get("cost_usd", 0.0)),
    )


async def _persist_findings(assessment_id: int, final: AssessmentState) -> None:
    drafts = [f for f in final.get("findings", []) if f.get("verified")]
    if not drafts:
        return
    async with get_sessionmaker()() as session:
        await FindingRepository(session).add_all(
            [
                Finding(
                    assessment_id=assessment_id,
                    obligation_id=d["obligation_id"],
                    policy_clause_id=d.get("policy_clause_id"),
                    impact_type=impact_of(d["impact_type"]),
                    rationale=d["rationale"],
                    confidence=float(d.get("confidence", 0.0)),
                    circular_span_start=d.get("circular_span_start"),
                    circular_span_end=d.get("circular_span_end"),
                    clause_span_start=d.get("clause_span_start"),
                    clause_span_end=d.get("clause_span_end"),
                    verified=True,
                    verification_attempts=int(d.get("verification_attempts", 1)),
                )
                for d in drafts
            ]
        )
        await session.commit()


async def _finish(
    assessment_id: int,
    agent_run_pk: int,
    status: AssessmentStatus,
    *,
    error: str | None = None,
    memo: str | None = None,
    tokens: int = 0,
    cost: float = 0.0,
) -> None:
    async with get_sessionmaker()() as session:
        assessments = AssessmentRepository(session)
        await assessments.set_status(assessment_id, status, error_reason=error)
        if memo:
            await assessments.set_memo(assessment_id, memo)
        if tokens or cost:
            await assessments.record_usage(assessment_id, tokens, cost)
        await AgentRunRepository(session).finish(agent_run_pk, status, error=error)
        await session.commit()
    log.info(
        "assessment.finished",
        extra={"status": status.value, "tokens": tokens, "cost_usd": round(cost, 4)},
    )
