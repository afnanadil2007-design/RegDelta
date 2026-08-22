"""Assessment routes, including the Server-Sent Events trace stream.

``POST /api/assessments`` returns ``{run_id}`` immediately and runs the graph
as a background task. The UI then opens the SSE stream and renders each node
as it completes — never a spinner for the whole assessment.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.errors import ApiError
from app.db.models.assessment import Assessment
from app.db.models.corpus import Circular
from app.db.models.enums import AnalystDecision, AssessmentStatus
from app.db.session import get_session, get_sessionmaker
from app.repositories.agent_runs import AgentRunRepository
from app.repositories.assessments import AssessmentRepository, FindingRepository
from app.repositories.obligations import ObligationRepository
from app.repositories.policy import PolicyRepository
from app.routers.schemas import (
    AgentStepOut,
    AssessmentOut,
    CreateAssessmentRequest,
    CreateAssessmentResponse,
    DecisionRequest,
    FindingOut,
)
from app.services.assessment import create_assessment, run_assessment

router = APIRouter(tags=["assessments"])

# How often the stream polls agent_steps for new rows.
_POLL_SECONDS = 0.5
# Stop streaming after this long even if the run never reaches a terminal state.
_STREAM_TIMEOUT_SECONDS = 900


@router.post("/assessments", response_model=CreateAssessmentResponse, status_code=202)
async def start_assessment(
    payload: CreateAssessmentRequest,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> CreateAssessmentResponse:
    circular = await session.get(Circular, payload.circular_id)
    if circular is None:
        raise ApiError(404, "circular_not_found", f"No circular with id {payload.circular_id}.")

    run_id = await create_assessment(payload.circular_id, payload.policy_pack_id, payload.as_of)
    background.add_task(run_assessment, run_id)
    return CreateAssessmentResponse(run_id=run_id)


@router.get("/assessments", response_model=list[AssessmentOut])
async def list_assessments(
    limit: int = 50, session: AsyncSession = Depends(get_session)
) -> list[AssessmentOut]:
    rows = await AssessmentRepository(session).list_assessments(limit=limit)
    return [await _to_out(session, a, with_findings=False) for a in rows]


@router.get("/assessments/{run_id}", response_model=AssessmentOut)
async def get_assessment(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> AssessmentOut:
    assessment = await AssessmentRepository(session).get_by_run_id(run_id)
    if assessment is None:
        raise ApiError(404, "assessment_not_found", f"No assessment with run_id {run_id}.")
    return await _to_out(session, assessment, with_findings=True)


@router.get("/assessments/{run_id}/steps", response_model=list[AgentStepOut])
async def get_steps(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[AgentStepOut]:
    """The full trace, for reloading a finished run's timeline."""
    assessment = await AssessmentRepository(session).get_by_run_id(run_id)
    if assessment is None:
        raise ApiError(404, "assessment_not_found", f"No assessment with run_id {run_id}.")
    runs = AgentRunRepository(session)
    agent_run = await runs.get_for_assessment(assessment.id)
    if agent_run is None:
        return []
    return [_step_out(s) for s in await runs.list_steps(agent_run.id)]


@router.post("/assessments/findings/{finding_id}/decision", response_model=FindingOut)
async def set_decision(
    finding_id: int,
    payload: DecisionRequest,
    session: AsyncSession = Depends(get_session),
) -> FindingOut:
    finding = await FindingRepository(session).set_decision(
        finding_id, AnalystDecision(payload.decision)
    )
    if finding is None:
        raise ApiError(404, "finding_not_found", f"No finding with id {finding_id}.")
    await session.commit()
    return (await _findings_out(session, [finding]))[0]


@router.get("/assessments/{run_id}/stream")
async def stream_assessment(run_id: uuid.UUID) -> EventSourceResponse:
    """One SSE event per completed graph node.

    Polls ``agent_steps`` by sequence number rather than holding a session
    open: the graph writes steps from concurrent tasks with their own
    sessions, so polling is both simpler and safer than a shared listener.
    """
    return EventSourceResponse(_event_stream(run_id))


async def _event_stream(run_id: uuid.UUID) -> AsyncIterator[dict]:
    last_seq = 0
    waited = 0.0

    while waited < _STREAM_TIMEOUT_SECONDS:
        async with get_sessionmaker()() as session:
            assessment = await AssessmentRepository(session).get_by_run_id(run_id)
            if assessment is None:
                yield {
                    "event": "error",
                    "data": json.dumps({"message": f"No assessment with run_id {run_id}."}),
                }
                return

            runs = AgentRunRepository(session)
            agent_run = await runs.get_for_assessment(assessment.id)
            if agent_run is not None:
                for step in await runs.list_steps_after(agent_run.id, last_seq):
                    last_seq = step.seq
                    yield {"event": "step", "data": _step_out(step).model_dump_json()}

            status = assessment.status

        if status in (
            AssessmentStatus.COMPLETED,
            AssessmentStatus.FAILED,
            AssessmentStatus.CAPPED,
        ):
            yield {
                "event": "done",
                "data": json.dumps(
                    {"status": status.value, "error_reason": assessment.error_reason}
                ),
            }
            return

        await asyncio.sleep(_POLL_SECONDS)
        waited += _POLL_SECONDS

    yield {"event": "error", "data": json.dumps({"message": "Stream timed out."})}


def _step_out(step) -> AgentStepOut:
    return AgentStepOut(
        seq=step.seq,
        node=step.node,
        status=step.status.value,
        summary=step.summary,
        tokens=step.tokens_in + step.tokens_out,
        latency_ms=step.latency_ms,
    )


async def _to_out(
    session: AsyncSession, assessment: Assessment, *, with_findings: bool
) -> AssessmentOut:
    circular = await session.get(Circular, assessment.circular_id)
    findings = []
    if with_findings:
        rows = await FindingRepository(session).list_for_assessment(assessment.id)
        findings = await _findings_out(session, rows)

    return AssessmentOut(
        id=assessment.id,
        run_id=assessment.run_id,
        circular_id=assessment.circular_id,
        circular_number=circular.circular_number if circular else None,
        policy_pack_id=assessment.policy_pack_id,
        status=assessment.status.value,
        error_reason=assessment.error_reason,
        memo=assessment.memo,
        total_tokens=assessment.total_tokens,
        total_cost_usd=assessment.total_cost_usd,
        created_at=assessment.created_at,
        completed_at=assessment.completed_at,
        findings=findings,
    )


async def _findings_out(session: AsyncSession, rows: list) -> list[FindingOut]:
    """Hydrate findings with their obligation and clause text for the UI."""
    if not rows:
        return []
    obligation_ids = [f.obligation_id for f in rows]
    clause_ids = [f.policy_clause_id for f in rows if f.policy_clause_id]

    obligations = {
        o.id: o for o in await ObligationRepository(session).get_many(obligation_ids)
    }
    clauses = {
        c.id: c for c in await PolicyRepository(session).get_many_clauses(clause_ids)
    }

    return [
        FindingOut(
            id=f.id,
            obligation_id=f.obligation_id,
            obligation_text=obligations[f.obligation_id].text
            if f.obligation_id in obligations
            else None,
            policy_clause_id=f.policy_clause_id,
            clause_number=clauses[f.policy_clause_id].clause_number
            if f.policy_clause_id in clauses
            else None,
            clause_text=clauses[f.policy_clause_id].text
            if f.policy_clause_id in clauses
            else None,
            impact_type=f.impact_type,
            rationale=f.rationale,
            confidence=f.confidence,
            circular_span_start=f.circular_span_start,
            circular_span_end=f.circular_span_end,
            clause_span_start=f.clause_span_start,
            clause_span_end=f.clause_span_end,
            verified=f.verified,
            verification_attempts=f.verification_attempts,
            analyst_decision=f.analyst_decision,
        )
        for f in rows
    ]
