"""Assemble the assessment graph.

    plan_assessment ──(Send per obligation)──▶ assess_obligation ──▶ synthesize_memo

``assess_obligation`` internally runs retrieve_clauses → judge_impact →
verify_grounding, looping back to judge_impact on a grounding failure up to
``MAX_VERIFICATION_RETRIES``. That loop lives inside the worker rather than as
graph edges because it is per-(obligation, clause) pair, and encoding it as
edges would require the fan-out state to carry per-pair retry counters.

Three hard limits are enforced, all from settings:
``MAX_VERIFICATION_RETRIES`` (in the worker), ``MAX_ASSESSMENT_TOKENS``
(checked before synthesis; halts and marks the run capped rather than failing),
and ``ASSESSMENT_TIMEOUT_SECONDS`` (a wall clock around the whole run).
"""

from __future__ import annotations

from functools import partial
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.ai.graph.nodes import (
    GraphContext,
    assess_obligation,
    fan_out,
    plan_assessment,
    synthesize_memo,
)
from app.ai.graph.state import AssessmentState
from app.core.logging import get_logger

log = get_logger("app.ai.graph.build")

GRAPH_VERSION = "v1"


async def _check_token_cap(state: AssessmentState, ctx: GraphContext) -> dict[str, Any]:
    """Halt before synthesis when the token budget is exhausted.

    A capped run is *not* a failure: its findings are kept and the assessment
    is marked CAPPED so the analyst can see why the memo is missing.
    """
    used = state.get("tokens_used", 0)
    cap = ctx.settings.max_assessment_tokens
    if used >= cap:
        log.warning("graph.token_cap_reached", extra={"used": used, "cap": cap})
        return {
            "capped": True,
            "cap_reason": f"Token cap reached: {used} >= {cap}. "
            "Findings are retained; the memo was not generated.",
        }
    return {"capped": False}


def _after_cap(state: AssessmentState) -> str:
    return END if state.get("capped") else "synthesize_memo"


def build_graph(ctx: GraphContext) -> CompiledStateGraph:
    """Compile the assessment graph with its dependencies bound."""
    graph = StateGraph(AssessmentState)

    graph.add_node("plan_assessment", partial(plan_assessment, ctx=ctx))
    graph.add_node("assess_obligation", partial(assess_obligation, ctx=ctx))
    graph.add_node("check_token_cap", partial(_check_token_cap, ctx=ctx))
    graph.add_node("synthesize_memo", partial(synthesize_memo, ctx=ctx))

    graph.add_edge(START, "plan_assessment")
    # Conditional edge returning a list of Send(...) — the documented LangGraph
    # fan-out. Workers write `findings` concurrently, which is why that key
    # carries an operator.add reducer.
    # LangGraph annotates this parameter as returning Hashable, but returning a
    # list of Send(...) is its own documented fan-out API. Their annotation is
    # narrower than the runtime contract, hence the ignore below.
    graph.add_conditional_edges(
        "plan_assessment",
        fan_out,  # type: ignore[arg-type]
        ["assess_obligation"],
    )
    graph.add_edge("assess_obligation", "check_token_cap")
    graph.add_conditional_edges("check_token_cap", _after_cap, [END, "synthesize_memo"])
    graph.add_edge("synthesize_memo", END)

    return graph.compile()
