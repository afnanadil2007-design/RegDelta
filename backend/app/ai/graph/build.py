"""Assemble the assessment graph.

    plan_assessment ──(Send per obligation)──▶ assess_obligation ──▶ synthesize_memo

``assess_obligation`` internally runs rank clauses → judge_impact →
verify_grounding, looping back to judge_impact on a grounding failure up to
``MAX_VERIFICATION_RETRIES``. That loop lives inside the worker rather than as
graph edges because it is per-(obligation, clause) pair, and encoding it as
edges would require the fan-out state to carry per-pair retry counters.

Three hard limits are enforced, all from settings: ``MAX_VERIFICATION_RETRIES``
(in the worker), ``MAX_ASSESSMENT_CALLS`` / ``MAX_ASSESSMENT_TOKENS`` (the
``CallBudget``, checked before every provider call; a spent budget skips the
memo and the run ends CAPPED), and ``ASSESSMENT_TIMEOUT_SECONDS`` (a wall clock
around the whole run, enforced by the service).
"""

from __future__ import annotations

from functools import partial

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

# Recorded on every agent run so a stored trace stays interpretable after the
# graph changes. v2: the budget is checked before every provider call, workers
# persist their own findings, and unverified judgements are kept as findings
# with quote status FAILED instead of being dropped. v3: the memo is told which
# findings' quotes were located and no longer calls findings "verified".
GRAPH_VERSION = "v3"


def _after_fan_in(_: AssessmentState, ctx: GraphContext) -> str:
    return END if ctx.budget.exhausted else "synthesize_memo"


def build_graph(ctx: GraphContext) -> CompiledStateGraph:
    """Compile the assessment graph with its dependencies bound."""
    graph = StateGraph(AssessmentState)

    graph.add_node("plan_assessment", partial(plan_assessment, ctx=ctx))
    graph.add_node("assess_obligation", partial(assess_obligation, ctx=ctx))
    graph.add_node("synthesize_memo", partial(synthesize_memo, ctx=ctx))

    graph.add_edge(START, "plan_assessment")
    # A conditional edge returning a list of Send(...) is LangGraph's
    # documented fan-out; its type annotation says Hashable, hence the ignore.
    graph.add_conditional_edges(
        "plan_assessment",
        fan_out,  # type: ignore[arg-type]
        ["assess_obligation"],
    )
    graph.add_conditional_edges(
        "assess_obligation", partial(_after_fan_in, ctx=ctx), [END, "synthesize_memo"]
    )
    graph.add_edge("synthesize_memo", END)

    return graph.compile()
