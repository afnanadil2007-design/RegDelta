"""Assessment graph nodes.

Control flow, and why it has this shape:

* ``plan_assessment`` loads the circular's obligations. It fans out because the
  obligations are *independent* — assessing one tells you nothing about the
  next — so there is no reason to serialise them.
* ``assess_obligation`` (the worker) retrieves candidate clauses and judges the
  impact. Retrieval is inside the worker because each obligation needs its own
  query.
* ``verify_grounding`` checks the judge's quotes actually resolve. On failure
  it loops back to ``judge_impact`` up to ``MAX_VERIFICATION_RETRIES``, then
  drops the claim. Dropping beats storing an unverifiable finding.
* ``synthesize_memo`` runs once, after the fan-in.

Every node returns readable errors instead of raising: an exception inside a
LangGraph node aborts the whole run, which would lose the findings that did
succeed.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from langgraph.types import Send
from pydantic import ValidationError

from app.ai.extraction.schemas import JudgedImpact, json_schema_for
from app.ai.gateway import GatewayError, LLMGateway
from app.ai.graph.state import AssessmentState, FindingDraft, ObligationTask
from app.ai.graph.tracing import Tracer
from app.ai.prompts import load_prompt
from app.ai.retrieval.pipeline import retrieve
from app.ai.verification.grounding import verify_judgement
from app.core.config import Settings
from app.core.logging import get_logger
from app.db.models.enums import ImpactType, RetrievalMode
from app.db.session import get_sessionmaker
from app.repositories.circulars import CircularRepository
from app.repositories.obligations import ObligationRepository
from app.repositories.policy import PolicyRepository
from app.repositories.search import SearchFilters

log = get_logger("app.ai.graph.nodes")

_JUDGE_SCHEMA = json_schema_for(JudgedImpact)
# How many candidate clauses each obligation is judged against.
_CLAUSES_PER_OBLIGATION = 3
# Gateway failure modes that are pointless to work around per-clause: a
# misconfigured provider fails every call the same way, so surface it as a run
# failure rather than an empty result.
_FATAL_GATEWAY_CODES = frozenset({"missing_api_key", "invalid_api_key", "invalid_request"})


class GraphContext:
    """Dependencies the nodes need, injected once when the graph is built."""

    def __init__(self, gateway: LLMGateway, settings: Settings, tracer: Tracer) -> None:
        self.gateway = gateway
        self.settings = settings
        self.tracer = tracer


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
    obligations = state.get("obligations", [])
    if not obligations:
        return []
    return [
        Send(
            "assess_obligation",
            {
                "task": task,
                "policy_pack_id": state["policy_pack_id"],
                "as_of": state.get("as_of"),
                "tokens_used": state.get("tokens_used", 0),
            },
        )
        for task in obligations
    ]


# --- worker -------------------------------------------------------------


async def assess_obligation(payload: dict[str, Any], ctx: GraphContext) -> dict[str, Any]:
    """Retrieve candidate clauses for one obligation, then judge each."""
    task: ObligationTask = payload["task"]
    pack_id: int = payload["policy_pack_id"]

    async with ctx.tracer.step(
        "retrieve_clauses",
        {"obligation_id": task["obligation_id"], "text": task["text"]},
    ) as step:
        clauses = await _retrieve_clauses(task, pack_id, ctx)
        step.summary = f"Retrieved {len(clauses)} candidate clause(s)"
        step.outputs = {"clause_numbers": [c["clause_number"] for c in clauses]}

    if not clauses:
        # An honest no-match, recorded rather than silently skipped.
        return {
            "findings": [
                FindingDraft(
                    obligation_id=task["obligation_id"],
                    obligation_text=task["text"],
                    policy_clause_id=None,
                    clause_number=None,
                    impact_type=ImpactType.NO_MATCH.value,
                    rationale="No policy clause cleared the relevance threshold "
                    "for this obligation.",
                    confidence=0.4,
                    verified=True,
                    verification_attempts=0,
                )
            ]
        }

    findings: list[FindingDraft] = []
    tokens = 0
    cost = 0.0
    for clause in clauses:
        draft, used, spent = await judge_and_verify(task, clause, ctx)
        if draft is not None:
            findings.append(draft)
        tokens += used
        cost += spent

    return {"findings": findings, "tokens_used": tokens, "cost_usd": cost}


async def _retrieve_clauses(
    task: ObligationTask, pack_id: int, ctx: GraphContext
) -> list[dict[str, Any]]:
    """Rank the pack's clauses against the obligation text.

    The pack is small (tens of clauses), so this ranks the whole pack with the
    cross-encoder rather than going through the chunk pipeline — the clause
    table is a different corpus with its own index.
    """
    from app.ai.retrieval.reranker import rerank

    async with get_sessionmaker()() as session:
        clauses = await PolicyRepository(session).list_clauses(pack_id)

    if not clauses:
        return []

    # Offloaded to a thread: reranking the policy pack is a synchronous CPU call.
    # Running it inline would block the event loop that also serves the SSE trace
    # stream, so the assessment would appear frozen while it ran.
    scored = await asyncio.to_thread(
        rerank, task["text"], [(c.id, c.text) for c in clauses]
    )
    by_id = {c.id: c for c in clauses}

    out: list[dict[str, Any]] = []
    for clause_id, score in scored[:_CLAUSES_PER_OBLIGATION]:
        if score < ctx.settings.relevance_threshold:
            continue
        clause = by_id[clause_id]
        out.append(
            {
                "id": clause.id,
                "clause_number": clause.clause_number,
                "text": clause.text,
                "char_start": clause.char_start,
                "score": score,
            }
        )
    return out


async def judge_and_verify(
    task: ObligationTask, clause: dict[str, Any], ctx: GraphContext
) -> tuple[FindingDraft | None, int, float]:
    """Judge one (obligation, clause) pair and verify its spans.

    Returns ``(finding_or_None, tokens, cost)``. A finding whose spans never
    verify within the retry budget is dropped.
    """
    attempts = 0
    tokens = 0
    cost = 0.0
    feedback: str | None = None
    max_attempts = ctx.settings.max_verification_retries + 1

    while attempts < max_attempts:
        attempts += 1
        async with ctx.tracer.step(
            "judge_impact",
            {
                "obligation_id": task["obligation_id"],
                "clause_number": clause["clause_number"],
                "attempt": attempts,
            },
        ) as step:
            # The judge's LLM calls are synchronous network I/O; run them off the
            # event loop so the live trace stream keeps updating during the run.
            judged, used, spent, error = await asyncio.to_thread(
                _judge, task, clause, ctx, feedback
            )
            tokens += used
            cost += spent
            step.tokens_in = used
            step.cost_usd = spent
            if judged is None:
                step.summary = f"Judge failed: {error}"
                step.outputs = {"error": error}
            else:
                step.summary = f"{judged.impact_type.value} ({judged.confidence:.2f})"
                step.outputs = {
                    "impact_type": judged.impact_type.value,
                    "confidence": judged.confidence,
                }

        if judged is None:
            return None, tokens, cost

        async with ctx.tracer.step(
            "verify_grounding",
            {"obligation_id": task["obligation_id"], "attempt": attempts},
        ) as step:
            draft, problem = _verify(task, clause, judged, attempts)
            step.summary = "Grounded" if draft else f"Ungrounded: {problem}"
            step.outputs = {"verified": draft is not None, "problem": problem}

        if draft is not None:
            return draft, tokens, cost

        # Feed the specific grounding failure back for the retry.
        feedback = problem

    log.warning(
        "graph.finding_dropped",
        extra={"obligation_id": task["obligation_id"], "clause": clause["clause_number"]},
    )
    return None, tokens, cost


def _judge(
    task: ObligationTask,
    clause: dict[str, Any],
    ctx: GraphContext,
    feedback: str | None,
) -> tuple[JudgedImpact | None, int, float, str | None]:
    """One judge call, with schema validation and a single repair attempt."""
    prompt = (
        load_prompt("judge_impact")
        .replace("{obligation}", task["text"])
        .replace("{clause}", clause["text"])
        .replace("{clause_number}", clause["clause_number"])
    )
    if feedback:
        prompt += (
            "\n\n## Previous attempt was not grounded\n\n"
            f"{feedback}\n\n"
            "Quote exactly from the material above this time."
        )

    try:
        response = ctx.gateway.complete(prompt, json_schema=_JUDGE_SCHEMA)
    except GatewayError as exc:
        # A missing/invalid key (or a rejected request) will fail every clause
        # identically — retrying the next obligation is pointless and produces a
        # misleading "no findings" result. Let it abort the run with a clear
        # reason instead of silently dropping the finding.
        if exc.code in _FATAL_GATEWAY_CODES:
            raise
        return None, 0, 0.0, f"gateway: {exc}"

    tokens = response.total_tokens
    cost = response.cost_usd
    if response.refused:
        return None, tokens, cost, "provider refused"

    try:
        return JudgedImpact.model_validate_json(response.text), tokens, cost, None
    except (ValidationError, ValueError):
        pass

    # One repair attempt with the validation error fed back.
    try:
        JudgedImpact.model_validate_json(response.text)
    except Exception as exc:
        error = str(exc)

    repair_prompt = (
        f"{prompt}\n\n## Repair required\n\nYour previous response did not "
        f"satisfy the schema.\n\nResponse:\n{response.text[:1500]}\n\n"
        f"Error:\n{error}\n\nReturn corrected JSON only."
    )
    try:
        repair = ctx.gateway.complete(repair_prompt, json_schema=_JUDGE_SCHEMA)
    except GatewayError as exc:
        return None, tokens, cost, f"gateway during repair: {exc}"

    tokens += repair.total_tokens
    cost += repair.cost_usd
    try:
        return JudgedImpact.model_validate_json(repair.text), tokens, cost, None
    except (ValidationError, ValueError) as exc:
        return None, tokens, cost, f"schema violation after repair: {exc}"


def _verify(
    task: ObligationTask,
    clause: dict[str, Any],
    judged: JudgedImpact,
    attempts: int,
) -> tuple[FindingDraft | None, str | None]:
    """Layer 1 groundedness — see app/ai/verification/grounding.py."""
    result = verify_judgement(
        judged,
        obligation_text=task["text"],
        obligation_char_start=task["char_start"],
        clause_text=clause["text"],
        clause_char_start=clause["char_start"],
    )
    if not result.grounded:
        return None, result.problem

    return (
        FindingDraft(
            obligation_id=task["obligation_id"],
            obligation_text=task["text"],
            policy_clause_id=clause["id"],
            clause_number=clause["clause_number"],
            impact_type=judged.impact_type.value,
            rationale=judged.rationale,
            confidence=judged.confidence,
            circular_span_start=(
                result.circular_span.char_start if result.circular_span else None
            ),
            circular_span_end=(
                result.circular_span.char_end if result.circular_span else None
            ),
            clause_span_start=result.clause_span.char_start if result.clause_span else None,
            clause_span_end=result.clause_span.char_end if result.clause_span else None,
            verified=True,
            verification_attempts=attempts,
        ),
        None,
    )


# --- synthesis ----------------------------------------------------------


async def synthesize_memo(state: AssessmentState, ctx: GraphContext) -> dict[str, Any]:
    """Write the analyst-facing memo from the verified findings."""
    findings = [f for f in state.get("findings", []) if f.get("verified")]

    async with ctx.tracer.step("synthesize_memo", {"finding_count": len(findings)}) as step:
        if not findings:
            step.summary = "No verified findings; memo skipped"
            return {"memo": "No verified findings were produced for this circular."}

        async with get_sessionmaker()() as session:
            circular = await CircularRepository(session).get(state["circular_id"])

        rendered = json.dumps(
            [
                {
                    "clause": f.get("clause_number"),
                    "impact": f.get("impact_type"),
                    "confidence": round(float(f.get("confidence", 0)), 2),
                    "rationale": f.get("rationale"),
                }
                for f in findings
            ],
            indent=2,
        )
        prompt = (
            load_prompt("synthesize_memo")
            .replace("{findings}", rendered)
            .replace("{circular_number}", circular.circular_number if circular else "")
            .replace("{circular_title}", circular.title if circular else "")
        )

        try:
            response = await asyncio.to_thread(ctx.gateway.complete, prompt, max_tokens=4000)
        except GatewayError as exc:
            step.summary = f"Memo failed: {exc}"
            return {"memo": f"Memo generation failed: {exc}"}

        step.tokens_in = response.tokens_in
        step.tokens_out = response.tokens_out
        step.cost_usd = response.cost_usd
        step.summary = f"Memo written ({len(response.text)} chars)"
        return {
            "memo": response.text,
            "tokens_used": response.total_tokens,
            "cost_usd": response.cost_usd,
        }


async def retrieve_context_for_query(
    query: str, as_of: Any = None, mode: RetrievalMode = RetrievalMode.HYBRID_RERANK
) -> dict[str, Any]:
    """The agent's only external capability: read-only corpus retrieval.

    Returns a readable error string rather than raising — a tool that throws
    into the graph would abort the run.
    """
    try:
        async with get_sessionmaker()() as session:
            result = await retrieve(
                session, query, mode=mode, filters=SearchFilters(as_of=as_of)
            )
        if result.below_threshold:
            return {"error": "No result cleared the relevance threshold."}
        return {"hits": [{"chunk_id": h.chunk_id, "text": h.text} for h in result.hits]}
    except Exception as exc:  # noqa: BLE001 - tools never raise into the graph
        return {"error": f"Error: retrieval failed ({exc})"}
