"""Stage 9 tests: graph topology, state reducers, limits, and grounding."""

from __future__ import annotations

import operator
from typing import get_args, get_origin, get_type_hints

import pytest
from app.db.models.enums import ImpactType

from app.ai.extraction.schemas import JudgedImpact
from app.ai.gateway import LLMGateway
from app.ai.graph.build import GRAPH_VERSION, build_graph
from app.ai.graph.nodes import GraphContext, _verify, fan_out
from app.ai.graph.state import AssessmentState, ObligationTask, impact_of
from app.ai.graph.tracing import Tracer
from app.core.config import get_settings


def _ctx() -> GraphContext:
    settings = get_settings()
    return GraphContext(LLMGateway(settings), settings, Tracer(1))


# --- state ---------------------------------------------------------------


def test_findings_uses_an_additive_reducer() -> None:
    """Workers write `findings` concurrently; without operator.add they clobber."""
    hints = get_type_hints(AssessmentState, include_extras=True)
    annotated = hints["findings"]
    assert get_origin(annotated) is not None
    assert operator.add in get_args(annotated), (
        "findings must be Annotated[list, operator.add] or concurrent worker "
        "writes will overwrite one another"
    )


def test_token_and_cost_counters_also_accumulate() -> None:
    hints = get_type_hints(AssessmentState, include_extras=True)
    for key in ("tokens_used", "cost_usd"):
        assert operator.add in get_args(hints[key]), f"{key} must accumulate"


def test_impact_of_falls_back_to_no_match() -> None:
    assert impact_of("CONFLICT") is ImpactType.CONFLICT
    assert impact_of("NOT_A_REAL_VERDICT") is ImpactType.NO_MATCH


# --- topology ------------------------------------------------------------


def test_graph_has_the_specified_nodes() -> None:
    graph = build_graph(_ctx()).get_graph()
    nodes = set(graph.nodes)
    assert {"plan_assessment", "assess_obligation", "synthesize_memo"} <= nodes


def test_graph_version_is_pinned() -> None:
    """Traces stay interpretable only if the topology version is recorded."""
    assert GRAPH_VERSION


def test_fan_out_emits_one_send_per_obligation() -> None:
    state: AssessmentState = {
        "policy_pack_id": 1,
        "obligations": [
            ObligationTask(obligation_id=1, text="a", actor=None, char_start=0, char_end=1),
            ObligationTask(obligation_id=2, text="b", actor=None, char_start=2, char_end=3),
        ],
    }
    sends = fan_out(state)
    assert len(sends) == 2
    assert {s.node for s in sends} == {"assess_obligation"}


def test_fan_out_with_no_obligations_is_empty() -> None:
    assert fan_out({"obligations": [], "policy_pack_id": 1}) == []


# --- grounding verification ---------------------------------------------


_TASK = ObligationTask(
    obligation_id=7,
    text="Stock brokers shall collect upfront margin before accepting orders.",
    actor="Stock brokers",
    char_start=1000,
    char_end=1066,
)
_CLAUSE = {
    "id": 3,
    "clause_number": "C.1",
    "text": "Upfront margin shall be collected from clients before the acceptance of orders.",
    "char_start": 500,
}


def test_verification_accepts_verbatim_quotes() -> None:
    judged = JudgedImpact(
        impact_type=ImpactType.ALREADY_COVERED,
        rationale="The clause already requires upfront margin before order acceptance.",
        confidence=0.9,
        circular_span="shall collect upfront margin",
        clause_span="Upfront margin shall be collected",
    )
    draft, problem = _verify(_TASK, _CLAUSE, judged, attempts=1)
    assert problem is None
    assert draft is not None
    assert draft["verified"] is True
    # Offsets are resolved into full-text coordinates, not paragraph-relative.
    assert draft["circular_span_start"] >= _TASK["char_start"]
    assert draft["clause_span_start"] >= _CLAUSE["char_start"]


def test_verification_rejects_a_hallucinated_circular_quote() -> None:
    judged = JudgedImpact(
        impact_type=ImpactType.CONFLICT,
        rationale="This rationale is long enough to satisfy the schema constraint.",
        confidence=0.8,
        circular_span="brokers shall waive all margin requirements",
        clause_span="Upfront margin shall be collected",
    )
    draft, problem = _verify(_TASK, _CLAUSE, judged, attempts=1)
    assert draft is None
    assert problem is not None and "circular_span" in problem


def test_verification_rejects_a_hallucinated_clause_quote() -> None:
    judged = JudgedImpact(
        impact_type=ImpactType.MODIFIED,
        rationale="This rationale is long enough to satisfy the schema constraint.",
        confidence=0.8,
        circular_span="shall collect upfront margin",
        clause_span="margin is optional for retail clients",
    )
    draft, problem = _verify(_TASK, _CLAUSE, judged, attempts=1)
    assert draft is None
    assert problem is not None and "clause_span" in problem


def test_no_match_does_not_require_a_clause_quote() -> None:
    judged = JudgedImpact(
        impact_type=ImpactType.NO_MATCH,
        rationale="The clause concerns record retention, not margin collection.",
        confidence=0.6,
        circular_span="shall collect upfront margin",
        clause_span="",
    )
    draft, problem = _verify(_TASK, _CLAUSE, judged, attempts=1)
    assert problem is None
    assert draft is not None
    assert draft["clause_span_start"] is None


def test_verification_records_the_attempt_count() -> None:
    judged = JudgedImpact(
        impact_type=ImpactType.ALREADY_COVERED,
        rationale="The clause already requires upfront margin before order acceptance.",
        confidence=0.9,
        circular_span="shall collect upfront margin",
        clause_span="Upfront margin shall be collected",
    )
    draft, _ = _verify(_TASK, _CLAUSE, judged, attempts=3)
    assert draft is not None
    assert draft["verification_attempts"] == 3


# --- hard limits ---------------------------------------------------------


@pytest.mark.asyncio
async def test_token_cap_halts_before_synthesis() -> None:
    """A capped run keeps its findings and is marked, not failed."""
    from app.ai.graph.build import _check_token_cap

    ctx = _ctx()
    over = {"tokens_used": ctx.settings.max_assessment_tokens + 1}
    result = await _check_token_cap(over, ctx)
    assert result["capped"] is True
    assert "cap" in (result["cap_reason"] or "").lower()

    under = {"tokens_used": 0}
    assert (await _check_token_cap(under, ctx))["capped"] is False


def test_limits_are_configured_not_hardcoded() -> None:
    settings = get_settings()
    assert settings.max_verification_retries >= 1
    assert settings.max_assessment_tokens > 0
    assert settings.assessment_timeout_seconds > 0


def test_agent_has_no_external_action_tools() -> None:
    """Security property: retrieval is the agent's only capability.

    Nothing a prompt injection in a circular could reach can take an action
    outside this database.
    """
    import app.ai.graph.nodes as nodes

    exported = [name for name in dir(nodes) if not name.startswith("_")]
    forbidden = {"requests", "httpx", "subprocess", "os", "send_email", "post", "write_file"}
    assert not (forbidden & set(exported)), (
        f"agent node module exposes action-capable names: {forbidden & set(exported)}"
    )
