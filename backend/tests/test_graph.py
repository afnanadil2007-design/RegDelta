"""Assessment graph: topology, reducers, limits, and the judge/verify worker."""

from __future__ import annotations

import json
import operator
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, get_args, get_origin, get_type_hints

import pytest

from app.ai.gateway import GatewayError, LLMResponse
from app.ai.graph.budget import BudgetExhausted, CallBudget
from app.ai.graph.build import GRAPH_VERSION, build_graph
from app.ai.graph.nodes import (
    GraphContext,
    RankedClause,
    _no_candidate_draft,
    fan_out,
    judge_and_verify,
)
from app.ai.graph.state import AssessmentState, ObligationTask, impact_of
from app.ai.graph.tracing import StepRecord
from app.core.config import Settings
from app.db.models.enums import ImpactType, QuoteStatus

# --- fakes ------------------------------------------------------------------


class ScriptedGateway:
    """Returns queued responses (or raises queued errors) and records prompts."""

    def __init__(self, *script: str | Exception) -> None:
        self.script = list(script)
        self.prompts: list[str] = []

    def complete(self, prompt: str, **_: Any) -> LLMResponse:
        self.prompts.append(prompt)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        refused = item == "<refused>"
        return LLMResponse(
            text="" if refused else item,
            model="scripted",
            provider="scripted",
            tokens_in=10,
            tokens_out=5,
            cost_usd=None,
            latency_ms=1,
            refused=refused,
        )


class MemoryTracer:
    """Records steps in memory instead of the database."""

    def __init__(self) -> None:
        self.steps: list[tuple[str, StepRecord]] = []

    @asynccontextmanager
    async def step(
        self, node: str, inputs: dict[str, Any] | None = None
    ) -> AsyncIterator[StepRecord]:
        record = StepRecord(step_id=len(self.steps) + 1)
        self.steps.append((node, record))
        yield record


def _ctx(gateway: Any, *, max_calls: int = 100, retries: int = 2) -> GraphContext:
    settings = Settings(_env_file=None, max_verification_retries=retries)  # type: ignore[call-arg]
    return GraphContext(
        gateway=gateway,
        settings=settings,
        tracer=MemoryTracer(),  # type: ignore[arg-type]
        budget=CallBudget(max_calls=max_calls, max_tokens=1_000_000),
    )


def _verdict(**overrides: Any) -> str:
    body = {
        "impact_type": "MODIFIED",
        "rationale": "The clause sets T+2 days where the obligation requires T+1 day.",
        "confidence": 0.8,
        "circular_span": "shall report short-collection",
        "clause_span": "reported to the Stock Exchange by T+2 days",
    }
    body.update(overrides)
    return json.dumps(body)


TASK = ObligationTask(
    obligation_id=7,
    text="Stock brokers shall report short-collection of margin by T+1 day.",
    actor="Stock brokers",
    char_start=1000,
    char_end=1066,
)
CLAUSE = RankedClause(
    id=3,
    clause_number="C.3",
    text="### C.3 Short-collection reporting\nInstances shall be reported to the Stock "
    "Exchange by T+2 days.",
    char_start=500,
    score=0.9,
)


# --- state and topology ------------------------------------------------------


def test_concurrently_written_keys_use_additive_reducers() -> None:
    """Workers write these keys concurrently; without operator.add they clobber."""
    hints = get_type_hints(AssessmentState, include_extras=True)
    for key in ("findings", "failed_tasks"):
        assert get_origin(hints[key]) is not None
        assert operator.add in get_args(hints[key]), f"{key} must accumulate"


def test_impact_of_rejects_an_unknown_verdict() -> None:
    assert impact_of("CONFLICT") is ImpactType.CONFLICT
    with pytest.raises(ValueError):
        impact_of("NOT_A_REAL_VERDICT")


def test_graph_has_the_specified_nodes() -> None:
    graph = build_graph(_ctx(ScriptedGateway())).get_graph()
    assert {"plan_assessment", "assess_obligation", "synthesize_memo"} <= set(graph.nodes)


def test_graph_version_is_recorded() -> None:
    assert GRAPH_VERSION == "v2"


def test_fan_out_emits_one_send_per_obligation() -> None:
    state: AssessmentState = {
        "assessment_id": 5,
        "policy_pack_id": 1,
        "obligations": [TASK, {**TASK, "obligation_id": 8}],
    }
    sends = fan_out(state)
    assert [s.node for s in sends] == ["assess_obligation", "assess_obligation"]
    assert all(s.arg["assessment_id"] == 5 for s in sends)


def test_fan_out_with_no_obligations_is_empty() -> None:
    assert fan_out({"obligations": [], "policy_pack_id": 1, "assessment_id": 1}) == []


# --- judge and verify ---------------------------------------------------------


@pytest.mark.asyncio
async def test_verbatim_quotes_are_verified_in_full_text_coordinates() -> None:
    ctx = _ctx(ScriptedGateway(_verdict()))
    outcome = await judge_and_verify(TASK, CLAUSE, ctx)

    draft = outcome.draft
    assert draft is not None and not outcome.failed
    assert draft["quote_status"] == QuoteStatus.VERIFIED.value
    assert draft["verification_attempts"] == 1
    start, end = draft["circular_span_start"], draft["circular_span_end"]
    assert TASK["text"][start - TASK["char_start"] : end - TASK["char_start"]] == (
        "shall report short-collection"
    )
    local = draft["clause_span_start"] - CLAUSE.char_start
    assert CLAUSE.text[local:].startswith("reported to the Stock Exchange")


@pytest.mark.asyncio
async def test_a_grounding_failure_is_retried_with_feedback() -> None:
    gateway = ScriptedGateway(_verdict(circular_span="brokers may skip reporting"), _verdict())
    outcome = await judge_and_verify(TASK, CLAUSE, _ctx(gateway))

    assert outcome.draft is not None
    assert outcome.draft["quote_status"] == QuoteStatus.VERIFIED.value
    assert outcome.draft["verification_attempts"] == 2
    assert "Previous attempt was not grounded" in gateway.prompts[1]


@pytest.mark.asyncio
async def test_quotes_that_never_resolve_are_kept_as_unverified_not_dropped() -> None:
    bad = _verdict(clause_span="margin is optional for retail clients")
    outcome = await judge_and_verify(TASK, CLAUSE, _ctx(ScriptedGateway(bad, bad, bad)))

    draft = outcome.draft
    assert draft is not None and not outcome.failed
    assert draft["quote_status"] == QuoteStatus.FAILED.value
    assert draft["verification_attempts"] == 3
    assert "clause_span" in (draft["verification_note"] or "")
    # The circular quote did resolve; the clause quote has no offsets.
    assert draft["circular_span_start"] is not None
    assert draft["clause_span_start"] is None


@pytest.mark.asyncio
async def test_schema_violation_gets_one_repair() -> None:
    gateway = ScriptedGateway('{"impact_type": "MAYBE"}', _verdict())
    outcome = await judge_and_verify(TASK, CLAUSE, _ctx(gateway))
    assert outcome.draft is not None
    assert outcome.draft["quote_status"] == QuoteStatus.VERIFIED.value
    assert "Repair required" in gateway.prompts[1]


@pytest.mark.asyncio
async def test_a_second_schema_violation_fails_the_task() -> None:
    gateway = ScriptedGateway("not json", "still not json")
    outcome = await judge_and_verify(TASK, CLAUSE, _ctx(gateway))
    assert outcome.draft is None and outcome.failed


@pytest.mark.asyncio
async def test_a_refusal_fails_the_task() -> None:
    outcome = await judge_and_verify(TASK, CLAUSE, _ctx(ScriptedGateway("<refused>")))
    assert outcome.draft is None and outcome.failed


@pytest.mark.asyncio
async def test_a_transient_provider_error_fails_only_the_task() -> None:
    gateway = ScriptedGateway(GatewayError("429", code="rate_limited"))
    outcome = await judge_and_verify(TASK, CLAUSE, _ctx(gateway))
    assert outcome.draft is None and outcome.failed


@pytest.mark.asyncio
async def test_a_credential_error_fails_the_run() -> None:
    gateway = ScriptedGateway(GatewayError("bad key", code="invalid_api_key"))
    with pytest.raises(GatewayError):
        await judge_and_verify(TASK, CLAUSE, _ctx(gateway))


@pytest.mark.asyncio
async def test_a_spent_budget_stops_further_calls() -> None:
    bad = _verdict(circular_span="not in the obligation")
    gateway = ScriptedGateway(bad, bad, bad)
    ctx = _ctx(gateway, max_calls=1)
    outcome = await judge_and_verify(TASK, CLAUSE, ctx)

    assert len(gateway.prompts) == 1, "no call may be made past the budget"
    assert ctx.budget.exhausted
    # The one judgement that was made is kept, marked unverified.
    assert outcome.draft is not None
    assert outcome.draft["quote_status"] == QuoteStatus.FAILED.value


def test_a_no_candidate_finding_claims_no_judgement() -> None:
    ranked = [RankedClause(1, "C.5", "### C.5 Evidence retention\nRetain.", 0, 0.12)]
    draft = _no_candidate_draft(TASK, ranked, 0.35)
    assert draft["impact_type"] == ImpactType.NO_MATCH.value
    assert draft["quote_status"] == QuoteStatus.NOT_APPLICABLE.value
    assert draft["confidence"] is None, "no model produced a score"
    assert "0.35" in draft["rationale"] and "C.5" in draft["rationale"]


# --- budget -------------------------------------------------------------------


def test_call_budget_is_exact_under_thread_contention() -> None:
    budget = CallBudget(max_calls=10, max_tokens=10**9)
    granted: list[bool] = []
    lock = threading.Lock()

    def worker() -> None:
        for _ in range(5):
            try:
                budget.acquire()
                ok = True
            except BudgetExhausted:
                ok = False
            with lock:
                granted.append(ok)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert granted.count(True) == 10
    assert "Call budget" in (budget.exhausted_reason or "")


def test_token_budget_refuses_the_next_call_and_counts_unpriced_calls() -> None:
    budget = CallBudget(max_calls=100, max_tokens=50)
    budget.acquire()
    budget.record(
        LLMResponse("x", "m", "p", tokens_in=40, tokens_out=20, cost_usd=None, latency_ms=1)
    )
    with pytest.raises(BudgetExhausted, match="Token budget"):
        budget.acquire()
    assert budget.unpriced_calls == 1
    assert budget.cost_usd == 0.0


def test_limits_are_configured_not_hardcoded() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.max_verification_retries >= 1
    assert settings.max_assessment_calls > 0
    assert settings.max_assessment_tokens > 0
    assert settings.assessment_timeout_seconds > 0


def test_agent_has_no_external_action_tools() -> None:
    """Security property: the graph's only capabilities are reads and judgements.

    Nothing a prompt injection in a circular could reach can take an action
    outside this database.
    """
    import app.ai.graph.nodes as nodes

    exported = {name for name in dir(nodes) if not name.startswith("_")}
    forbidden = {"requests", "httpx", "subprocess", "os", "send_email", "post", "write_file"}
    assert not (forbidden & exported)
