"""Assessment graph nodes.

Control flow, and why it has this shape:

* ``plan_assessment`` loads the circular's obligations. They are independent —
  assessing one tells you nothing about the next — so they fan out.
* ``assess_obligation`` (the worker) ranks the policy pack's clauses against
  one obligation, judges each candidate above the relevance threshold, and
  verifies the judge's quotes. A grounding failure loops back to the judge up
  to ``MAX_VERIFICATION_RETRIES``; if the quotes still do not resolve, the
  judgement is stored as an *unverified* finding (quote status FAILED) so the
  analyst sees it rather than it vanishing. The worker persists its findings
  before returning, so a timeout or cap later in the run keeps them.
* ``synthesize_memo`` runs once, after the fan-in, over verified findings.

Every provider call first claims a slot from the shared ``CallBudget``; when
the call or token budget is spent, workers stop judging and the run ends
CAPPED with what it has. Errors that would fail every call the same way
(missing or rejected credentials, an unsupported provider) propagate and fail
the run; anything else fails only the task at hand, which is counted.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from langgraph.types import Send
from pydantic import ValidationError

from app.ai.extraction.schemas import JudgedImpact, json_schema_for
from app.ai.gateway import GatewayError, LLMGateway, LLMResponse
from app.ai.graph.budget import BudgetExhausted, CallBudget
from app.ai.graph.state import AssessmentState, FindingDraft, ObligationTask
from app.ai.graph.tracing import StepRecord, Tracer
from app.ai.prompts import render_prompt
from app.ai.verification.grounding import GroundingResult, verify_judgement
from app.core.config import Settings
from app.core.logging import get_logger
from app.db.models.assessment import Finding
from app.db.models.enums import ImpactType, QuoteStatus
from app.db.session import get_sessionmaker
from app.repositories.assessments import FindingRepository
from app.repositories.circulars import CircularRepository
from app.repositories.obligations import ObligationRepository
from app.repositories.policy import PolicyRepository

log = get_logger("app.ai.graph.nodes")

_JUDGE_SCHEMA = json_schema_for(JudgedImpact)
# How many candidate clauses each obligation is judged against.
_CLAUSES_PER_OBLIGATION = 3
# Gateway failure modes that would recur on every call: surface them as a run
# failure rather than as a run full of empty results.
FATAL_GATEWAY_CODES = frozenset(
    {"missing_api_key", "invalid_api_key", "invalid_request", "unsupported"}
)
# Findings the memo may describe: verified judgements, and retrieval
# no-matches (a statement about the policy pack, with no quote to verify).
_MEMO_ELIGIBLE = (QuoteStatus.VERIFIED.value, QuoteStatus.NOT_APPLICABLE.value)


@dataclass
class GraphContext:
    """Dependencies the nodes need, injected once when the graph is built."""

    gateway: LLMGateway
    settings: Settings
    tracer: Tracer
    budget: CallBudget
    # Tasks that failed outright. Kept here as well as in the graph state so
    # it survives a timeout, which discards the state.
    failed_tasks: int = 0


# --- plan ---------------------------------------------------------------


async def plan_assessment(state: AssessmentState, ctx: GraphContext) -> dict[str, Any]:
    """Load the circular's obligations; the conditional edge fans them out."""
    async with ctx.tracer.step("plan_assessment", {"circular_id": state["circular_id"]}) as step:
        async with get_sessionmaker()() as session:
            obligations = await ObligationRepository(session).list_for_circular(
                state["circular_id"]
            )

        tasks: list[ObligationTask] = [
            ObligationTask(
                obligation_id=o.id,
                text=o.text,
                actor=o.actor,
                char_start=o.char_start,
                char_end=o.char_end,
            )
            for o in obligations
        ]
        step.summary = f"Planned {len(tasks)} obligation(s) to assess"
        step.outputs = {"obligation_count": len(tasks)}
        return {"obligations": tasks}


def fan_out(state: AssessmentState) -> list[Send]:
    """One ``Send`` per obligation — the parallel branch the brief specifies."""
    return [
        Send(
            "assess_obligation",
            {
                "task": task,
                "assessment_id": state["assessment_id"],
                "policy_pack_id": state["policy_pack_id"],
            },
        )
        for task in state.get("obligations", [])
    ]


# --- worker -------------------------------------------------------------


@dataclass(frozen=True)
class RankedClause:
    id: int
    clause_number: str
    text: str
    char_start: int
    score: float


async def assess_obligation(payload: dict[str, Any], ctx: GraphContext) -> dict[str, Any]:
    """Rank clauses for one obligation, judge the candidates, persist the results."""
    task: ObligationTask = payload["task"]

    try:
        async with ctx.tracer.step(
            "retrieve_clauses",
            {"obligation_id": task["obligation_id"], "text": task["text"]},
        ) as step:
            ranked = await _rank_clauses(task, payload["policy_pack_id"])
            threshold = ctx.settings.relevance_threshold
            candidates = [c for c in ranked[:_CLAUSES_PER_OBLIGATION] if c.score >= threshold]
            step.summary = (
                f"{len(candidates)} clause(s) at or above the {threshold:.2f} threshold"
                if ranked
                else "The policy pack has no clauses"
            )
            step.outputs = {
                "candidates": [
                    {"clause": c.clause_number, "score": round(c.score, 4)} for c in candidates
                ],
                "best_below_threshold": _best_below(ranked, threshold),
            }
    except Exception:
        # The step itself recorded the error; one failed task, not a failed run.
        log.exception("graph.retrieval_failed", extra={"obligation_id": task["obligation_id"]})
        ctx.failed_tasks += 1
        return {"failed_tasks": 1}

    drafts: list[FindingDraft] = []
    failed = 0
    if not candidates:
        drafts.append(_no_candidate_draft(task, ranked, ctx.settings.relevance_threshold))
    for clause in candidates:
        if ctx.budget.exhausted:
            break
        outcome = await judge_and_verify(task, clause, ctx)
        if outcome.draft is not None:
            drafts.append(outcome.draft)
        failed += int(outcome.failed)

    if drafts:
        await _persist(payload["assessment_id"], drafts)
    ctx.failed_tasks += failed
    return {"findings": drafts, "failed_tasks": failed}


async def _rank_clauses(task: ObligationTask, pack_id: int) -> list[RankedClause]:
    """Score every clause in the pack against the obligation, best first.

    The pack is small (tens of clauses), so the cross-encoder ranks all of it
    rather than going through the chunk pipeline: clauses are a separate
    corpus with their own index.
    """
    from app.ai.retrieval.reranker import rerank

    async with get_sessionmaker()() as session:
        clauses = await PolicyRepository(session).list_clauses(pack_id)
    if not clauses:
        return []

    # Reranking is a synchronous CPU call; inline it would block the event
    # loop that also serves the live trace stream.
    scored = await asyncio.to_thread(rerank, task["text"], [(c.id, c.text) for c in clauses])
    by_id = {c.id: c for c in clauses}
    return [
        RankedClause(
            id=clause_id,
            clause_number=by_id[clause_id].clause_number,
            text=by_id[clause_id].text,
            char_start=by_id[clause_id].char_start,
            score=score,
        )
        for clause_id, score in scored
    ]


def _best_below(ranked: list[RankedClause], threshold: float) -> dict[str, Any] | None:
    below = [c for c in ranked if c.score < threshold]
    if not below:
        return None
    return {"clause": below[0].clause_number, "score": round(below[0].score, 4)}


def _no_candidate_draft(
    task: ObligationTask, ranked: list[RankedClause], threshold: float
) -> FindingDraft:
    """A retrieval-level no-match: no clause was close enough to judge."""
    if ranked:
        closest = ranked[0]
        detail = f" The closest was {closest.clause_number} at {closest.score:.2f}."
    else:
        detail = " The policy pack has no clauses."
    return FindingDraft(
        obligation_id=task["obligation_id"],
        policy_clause_id=None,
        clause_number=None,
        impact_type=ImpactType.NO_MATCH.value,
        rationale=(
            f"No policy clause scored at or above the relevance threshold ({threshold:.2f}) "
            f"for this obligation, so no judgement was made.{detail}"
        ),
        confidence=None,
        circular_span_start=None,
        circular_span_end=None,
        clause_span_start=None,
        clause_span_end=None,
        quote_status=QuoteStatus.NOT_APPLICABLE.value,
        verification_note=None,
        unlocated_quote=None,
        verification_attempts=0,
    )


async def _persist(assessment_id: int, drafts: list[FindingDraft]) -> None:
    async with get_sessionmaker()() as session:
        await FindingRepository(session).add_all(
            [
                Finding(
                    assessment_id=assessment_id,
                    obligation_id=d["obligation_id"],
                    policy_clause_id=d["policy_clause_id"],
                    impact_type=ImpactType(d["impact_type"]),
                    rationale=d["rationale"],
                    confidence=d["confidence"],
                    circular_span_start=d["circular_span_start"],
                    circular_span_end=d["circular_span_end"],
                    clause_span_start=d["clause_span_start"],
                    clause_span_end=d["clause_span_end"],
                    quote_status=QuoteStatus(d["quote_status"]),
                    verification_note=d["verification_note"],
                    unlocated_quote=d["unlocated_quote"],
                    verification_attempts=d["verification_attempts"],
                )
                for d in drafts
            ]
        )
        await session.commit()


@dataclass(frozen=True)
class JudgeOutcome:
    """A finding (verified or not), or a task that failed without one."""

    draft: FindingDraft | None
    failed: bool = False


async def judge_and_verify(
    task: ObligationTask, clause: RankedClause, ctx: GraphContext
) -> JudgeOutcome:
    """Judge one (obligation, clause) pair and verify its quotes.

    Up to ``max_verification_retries`` re-judgements are made when a quote does
    not resolve, each told which quote failed. A judgement whose quotes never
    resolve is returned as a FAILED-quote draft, not dropped.
    """
    feedback: str | None = None
    last: tuple[JudgedImpact, str] | None = None
    attempts = 0

    while attempts <= ctx.settings.max_verification_retries:
        attempts += 1
        try:
            async with ctx.tracer.step(
                "judge_impact",
                {
                    "obligation_id": task["obligation_id"],
                    "clause_number": clause.clause_number,
                    "attempt": attempts,
                },
            ) as step:
                # The provider call is synchronous network I/O; run it off the
                # event loop so the live trace stream keeps updating.
                judged, error = await asyncio.to_thread(_judge, task, clause, ctx, feedback, step)
                if judged is None:
                    step.summary = f"Judge failed: {error}"
                    step.outputs = {"error": error}
                else:
                    step.summary = (
                        f"{judged.impact_type.value} (model score {judged.confidence:.2f})"
                    )
                    step.outputs = {
                        "impact_type": judged.impact_type.value,
                        "confidence": judged.confidence,
                    }
        except BudgetExhausted:
            if last is None:
                return JudgeOutcome(None)
            return JudgeOutcome(_unverified(task, clause, last, attempts - 1))

        if judged is None:
            return JudgeOutcome(None, failed=True)

        async with ctx.tracer.step(
            "verify_grounding",
            {"obligation_id": task["obligation_id"], "attempt": attempts},
        ) as step:
            draft, problem = _verify(task, clause, judged, attempts)
            step.summary = "Quotes located in source" if draft else f"Quote not located: {problem}"
            step.outputs = {"quotes_located": draft is not None, "problem": problem}

        if draft is not None:
            return JudgeOutcome(draft)
        last = (judged, problem or "a quote could not be located")
        feedback = problem

    log.warning(
        "graph.quote_unverified",
        extra={"obligation_id": task["obligation_id"], "clause": clause.clause_number},
    )
    return JudgeOutcome(_unverified(task, clause, last, attempts) if last else None)


def _call(ctx: GraphContext, step: StepRecord, prompt: str) -> LLMResponse:
    """One budgeted, accounted provider call for the judge."""
    ctx.budget.acquire()
    response = ctx.gateway.complete(prompt, json_schema=_JUDGE_SCHEMA)
    ctx.budget.record(response)
    step.add_call(response)
    return response


def _judge(
    task: ObligationTask,
    clause: RankedClause,
    ctx: GraphContext,
    feedback: str | None,
    step: StepRecord,
) -> tuple[JudgedImpact | None, str | None]:
    """One judgement, with schema validation and a single repair attempt."""
    prompt = render_prompt(
        "judge_impact",
        obligation=task["text"],
        clause=clause.text,
        clause_number=clause.clause_number,
    )
    if feedback:
        prompt += (
            "\n\n## Previous attempt was not grounded\n\n"
            f"{feedback}\n\n"
            "Quote exactly from the material above this time."
        )

    try:
        response = _call(ctx, step, prompt)
    except GatewayError as exc:
        if exc.code in FATAL_GATEWAY_CODES:
            raise
        return None, f"gateway: {exc.human_message}"
    if response.refused:
        return None, "provider refused"

    try:
        return JudgedImpact.model_validate_json(response.text), None
    except ValueError as exc:  # pydantic.ValidationError subclasses ValueError
        error = _short_error(exc)

    repair_prompt = (
        f"{prompt}\n\n## Repair required\n\nYour previous response did not "
        f"satisfy the schema.\n\nResponse:\n{response.text[:1500]}\n\n"
        f"Error:\n{error}\n\nReturn corrected JSON only."
    )
    try:
        repair = _call(ctx, step, repair_prompt)
    except GatewayError as exc:
        if exc.code in FATAL_GATEWAY_CODES:
            raise
        return None, f"gateway during repair: {exc.human_message}"
    try:
        return JudgedImpact.model_validate_json(repair.text), None
    except ValueError as exc:
        return None, f"schema violation after repair: {_short_error(exc)}"


def _short_error(exc: ValueError) -> str:
    if isinstance(exc, ValidationError) and exc.errors():
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first.get("loc", ()))
        return f"{location}: {first.get('msg', 'invalid')}" if location else first.get("msg", "")
    return str(exc)[:300]


def _verify(
    task: ObligationTask,
    clause: RankedClause,
    judged: JudgedImpact,
    attempts: int,
) -> tuple[FindingDraft | None, str | None]:
    """Layer 1 groundedness — see app/ai/verification/grounding.py."""
    result = _ground(task, clause, judged)
    if not result.grounded:
        return None, result.problem
    return _draft(task, clause, judged, attempts, QuoteStatus.VERIFIED, None, result), None


def _unverified(
    task: ObligationTask,
    clause: RankedClause,
    last: tuple[JudgedImpact, str],
    attempts: int,
) -> FindingDraft:
    judged, problem = last
    result = _ground(task, clause, judged)
    return _draft(task, clause, judged, attempts, QuoteStatus.FAILED, problem, result)


def _ground(task: ObligationTask, clause: RankedClause, judged: JudgedImpact) -> GroundingResult:
    return verify_judgement(
        judged,
        obligation_text=task["text"],
        obligation_char_start=task["char_start"],
        clause_text=clause.text,
        clause_char_start=clause.char_start,
    )


def _draft(
    task: ObligationTask,
    clause: RankedClause,
    judged: JudgedImpact,
    attempts: int,
    status: QuoteStatus,
    note: str | None,
    result: GroundingResult,
) -> FindingDraft:
    """A finding from a judgement; only quotes that resolved get offsets."""
    circular, clause_span = result.circular_span, result.clause_span
    unlocated = None
    if status is QuoteStatus.FAILED:
        unlocated = judged.circular_span if circular is None else judged.clause_span
    return FindingDraft(
        obligation_id=task["obligation_id"],
        policy_clause_id=clause.id,
        clause_number=clause.clause_number,
        impact_type=judged.impact_type.value,
        rationale=judged.rationale,
        confidence=judged.confidence,
        circular_span_start=circular.char_start if circular else None,
        circular_span_end=circular.char_end if circular else None,
        clause_span_start=clause_span.char_start if clause_span else None,
        clause_span_end=clause_span.char_end if clause_span else None,
        quote_status=status.value,
        verification_note=note,
        unlocated_quote=unlocated or None,
        verification_attempts=attempts,
    )


# --- synthesis ----------------------------------------------------------


async def synthesize_memo(state: AssessmentState, ctx: GraphContext) -> dict[str, Any]:
    """Write the analyst-facing memo from the verified findings."""
    findings = [f for f in state.get("findings", []) if f["quote_status"] in _MEMO_ELIGIBLE]

    async with ctx.tracer.step("synthesize_memo", {"finding_count": len(findings)}) as step:
        if not findings:
            step.summary = "No verified findings; memo skipped"
            return {"memo": None, "memo_note": "No verified findings, so no memo was written."}

        async with get_sessionmaker()() as session:
            circular = await CircularRepository(session).get(state["circular_id"])

        rendered = json.dumps(
            [
                {
                    "clause": f["clause_number"],
                    "impact": f["impact_type"],
                    "rationale": f["rationale"],
                }
                for f in findings
            ],
            indent=2,
        )
        prompt = render_prompt(
            "synthesize_memo",
            findings=rendered,
            circular_number=circular.circular_number if circular else "",
            circular_title=circular.title if circular else "",
        )

        try:
            ctx.budget.acquire()
            response = await asyncio.to_thread(ctx.gateway.complete, prompt, max_tokens=4000)
        except BudgetExhausted:
            step.summary = "Budget spent before the memo; memo skipped"
            return {"memo": None, "memo_note": None}
        except GatewayError as exc:
            if exc.code in FATAL_GATEWAY_CODES:
                raise
            step.summary = f"Memo failed: {exc.human_message}"
            return {
                "memo": None,
                "memo_note": f"The memo could not be written: {exc.human_message}",
            }

        ctx.budget.record(response)
        step.add_call(response)
        step.summary = f"Memo written ({len(response.text)} chars)"
        return {"memo": response.text, "memo_note": None}
