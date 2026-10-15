"""Assessment routes, including the Server-Sent Events trace stream.

``POST /api/assessments`` returns ``{run_id}`` immediately and runs the graph
as a background task. The UI then opens the SSE stream (protocol in
``app.services.assessment_stream``) and renders each node as it changes.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.models.assessment import AgentRun, AgentStep, Assessment
from app.db.models.enums import AnalystDecision, ImpactType, QuoteStatus
from app.db.session import get_session
from app.repositories.agent_runs import AgentRunRepository
from app.repositories.assessments import (
    AssessmentRepository,
    FindingContext,
    FindingCounts,
    FindingRepository,
)
from app.repositories.circulars import CircularRepository
from app.repositories.obligations import ObligationRepository
from app.repositories.policy import PolicyRepository
from app.routers.schemas import (
    AgentStepOut,
    AssessmentDetail,
    AssessmentPage,
    AssessmentSummary,
    CreateAssessmentRequest,
    CreateAssessmentResponse,
    DecisionRequest,
    FindingCountsOut,
    FindingOut,
    ProviderOut,
    UsageOut,
)
from app.services.assessment import (
    AssessmentInProgress,
    ProviderUnavailable,
    create_assessment,
    run_assessment,
)
from app.services.assessment_stream import trace_events

router = APIRouter(tags=["assessments"])


@router.post("/assessments", response_model=CreateAssessmentResponse, status_code=202)
async def start_assessment(
    payload: CreateAssessmentRequest,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> CreateAssessmentResponse:
    if await CircularRepository(session).get(payload.circular_id) is None:
        raise ApiError(404, "circular_not_found", f"No circular with id {payload.circular_id}.")
    if await PolicyRepository(session).get_pack(payload.policy_pack_id) is None:
        raise ApiError(
            404, "policy_pack_not_found", f"No policy pack with id {payload.policy_pack_id}."
        )

    try:
        run_id = await create_assessment(
            payload.circular_id, payload.policy_pack_id, payload.as_of, settings=settings
        )
    except ProviderUnavailable as exc:
        raise ApiError(503, "provider_unavailable", exc.reason) from exc
    except AssessmentInProgress as exc:
        raise ApiError(
            409,
            "assessment_in_progress",
            "An assessment of this circular against this policy pack is already running.",
            detail={"run_id": str(exc.run_id)},
        ) from exc

    background.add_task(run_assessment, run_id, settings)
    return CreateAssessmentResponse(run_id=run_id)


@router.get("/assessments", response_model=AssessmentPage)
async def list_assessments(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> AssessmentPage:
    repo = AssessmentRepository(session)
    rows = await repo.list_assessments(limit=limit, offset=offset)
    items = await _summaries(session, rows)
    return AssessmentPage(items=items, total=await repo.count(), limit=limit, offset=offset)


@router.get("/assessments/{run_id}", response_model=AssessmentDetail)
async def get_assessment(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> AssessmentDetail:
    assessment = await AssessmentRepository(session).get_by_run_id(run_id)
    if assessment is None:
        raise ApiError(404, "assessment_not_found", f"No assessment with run_id {run_id}.")
    summary = (await _summaries(session, [assessment]))[0]
    findings = await FindingRepository(session).list_with_context(assessment.id)
    return AssessmentDetail(
        **summary.model_dump(),
        memo=assessment.memo,
        findings=[finding_out(f) for f in findings],
    )


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
    return [step_out(s) for s in await runs.list_steps(agent_run.id)]


@router.post("/assessments/findings/{finding_id}/decision", response_model=FindingOut)
async def set_decision(
    finding_id: int,
    payload: DecisionRequest,
    session: AsyncSession = Depends(get_session),
) -> FindingOut:
    findings = FindingRepository(session)
    if await findings.set_decision(finding_id, payload.decision) is None:
        raise ApiError(404, "finding_not_found", f"No finding with id {finding_id}.")
    await session.commit()
    context = await findings.get_with_context(finding_id)
    if context is None:  # pragma: no cover - the row was just written
        raise ApiError(404, "finding_not_found", f"No finding with id {finding_id}.")
    return finding_out(context)


@router.get("/assessments/{run_id}/stream")
async def stream_assessment(run_id: uuid.UUID, request: Request) -> EventSourceResponse:
    """The live trace; see app.services.assessment_stream for the protocol."""
    events = trace_events(
        run_id,
        step_view=lambda step: step_out(step).model_dump(mode="json"),
        is_disconnected=request.is_disconnected,
    )
    return EventSourceResponse(events)


# --- views ----------------------------------------------------------------


def step_out(step: AgentStep) -> AgentStepOut:
    inputs: dict[str, Any] = step.inputs or {}
    return AgentStepOut(
        seq=step.seq,
        node=step.node,
        status=step.status,
        summary=step.summary,
        tokens=step.tokens_in + step.tokens_out,
        cost_usd=step.cost_usd,
        latency_ms=step.latency_ms,
        error=step.error,
        obligation_id=_int_or_none(inputs.get("obligation_id")),
        clause_number=inputs.get("clause_number"),
        attempt=_int_or_none(inputs.get("attempt")),
        started_at=step.started_at,
        finished_at=step.finished_at,
    )


def finding_out(context: FindingContext) -> FindingOut:
    f = context.finding
    return FindingOut(
        id=f.id,
        circular_id=context.circular_id,
        obligation_id=f.obligation_id,
        obligation_text=context.obligation_text,
        obligation_char_start=context.obligation_char_start,
        obligation_char_end=context.obligation_char_end,
        policy_clause_id=f.policy_clause_id,
        clause_number=context.clause_number,
        clause_heading=context.clause_heading,
        clause_text=context.clause_text,
        clause_char_start=context.clause_char_start,
        impact_type=f.impact_type,
        rationale=f.rationale,
        model_confidence=f.confidence,
        circular_span_start=f.circular_span_start,
        circular_span_end=f.circular_span_end,
        clause_span_start=f.clause_span_start,
        clause_span_end=f.clause_span_end,
        quote_status=f.quote_status,
        verification_note=f.verification_note,
        verification_attempts=f.verification_attempts,
        analyst_decision=f.analyst_decision,
        decided_at=f.decided_at,
    )


async def _summaries(session: AsyncSession, rows: list[Assessment]) -> list[AssessmentSummary]:
    """Hydrate assessments with their circular, pack, run, and counts in batch."""
    ids = [a.id for a in rows]
    circular_ids = list({a.circular_id for a in rows})
    circulars = await CircularRepository(session).summaries(circular_ids)
    packs = await PolicyRepository(session).get_many_packs(list({a.policy_pack_id for a in rows}))
    runs = await AgentRunRepository(session).latest_for_assessments(ids)
    counts = await FindingRepository(session).counts(ids)
    obligation_counts = await ObligationRepository(session).counts_by_circular(circular_ids)

    out: list[AssessmentSummary] = []
    for a in rows:
        circular = circulars.get(a.circular_id)
        pack = packs.get(a.policy_pack_id)
        run = runs.get(a.id)
        out.append(
            AssessmentSummary(
                id=a.id,
                run_id=a.run_id,
                circular_id=a.circular_id,
                circular_number=circular[0] if circular else None,
                circular_title=circular[1] if circular else None,
                policy_pack_id=a.policy_pack_id,
                policy_pack_name=pack.name if pack else None,
                policy_pack_version=pack.version if pack else None,
                as_of=a.as_of_date,
                status=a.status,
                status_detail=a.error_reason,
                provider=_provider_out(run),
                graph_version=run.graph_version if run else None,
                usage=_usage_out(a),
                failed_tasks=a.failed_tasks,
                obligation_count=obligation_counts.get(a.circular_id, 0),
                counts=_counts_out(counts.get(a.id, FindingCounts())),
                created_at=a.created_at,
                completed_at=a.completed_at,
            )
        )
    return out


def _provider_out(run: AgentRun | None) -> ProviderOut | None:
    if run is None or run.provider is None:
        return None
    return ProviderOut(
        name=run.provider, model=run.model, deterministic=run.provider == "deterministic"
    )


def _usage_out(assessment: Assessment) -> UsageOut:
    """Cost is unknown, not zero, when nothing that ran had a list price."""
    priced_nothing = assessment.unpriced_calls > 0 and assessment.total_cost_usd == 0
    return UsageOut(
        total_tokens=assessment.total_tokens,
        estimated_cost_usd=None if priced_nothing else assessment.total_cost_usd,
        cost_complete=assessment.unpriced_calls == 0,
        unpriced_calls=assessment.unpriced_calls,
    )


def _counts_out(counts: FindingCounts) -> FindingCountsOut:
    return FindingCountsOut(
        total=counts.total,
        assessed_obligations=counts.assessed_obligations,
        quote_verified=counts.by_quote_status.get(QuoteStatus.VERIFIED, 0),
        quote_failed=counts.by_quote_status.get(QuoteStatus.FAILED, 0),
        quote_not_applicable=counts.by_quote_status.get(QuoteStatus.NOT_APPLICABLE, 0),
        by_impact={impact: counts.by_impact.get(impact, 0) for impact in ImpactType},
        decision_pending=counts.by_decision.get(AnalystDecision.PENDING, 0),
        decision_accepted=counts.by_decision.get(AnalystDecision.ACCEPTED, 0),
        decision_rejected=counts.by_decision.get(AnalystDecision.REJECTED, 0),
    )


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) else None
