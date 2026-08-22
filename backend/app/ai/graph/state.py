"""Graph state.

``findings`` is ``Annotated[list, operator.add]`` because the worker fan-out
writes that key *concurrently*: every ``assess_obligation`` branch returns its
own findings, and LangGraph needs a reducer to merge them. Without the
annotation the last writer would silently win and every other obligation's
finding would vanish.

Token and cost counters use the same reducer for the same reason.
"""

from __future__ import annotations

import operator
from datetime import date
from typing import Annotated, TypedDict

from app.db.models.enums import ImpactType


class FindingDraft(TypedDict, total=False):
    """A finding as it moves through the graph, before it is persisted."""

    obligation_id: int
    obligation_text: str
    policy_clause_id: int | None
    clause_number: str | None
    impact_type: str
    rationale: str
    confidence: float
    circular_span_start: int | None
    circular_span_end: int | None
    clause_span_start: int | None
    clause_span_end: int | None
    verified: bool
    verification_attempts: int
    # Populated when the finding was dropped; kept for the trace, not stored.
    dropped_reason: str | None


class ObligationTask(TypedDict):
    """One unit of the fan-out."""

    obligation_id: int
    text: str
    actor: str | None
    char_start: int
    char_end: int


class AssessmentState(TypedDict, total=False):
    """State threaded through the assessment graph."""

    # --- inputs (set once) ---
    assessment_id: int
    agent_run_id: int
    circular_id: int
    policy_pack_id: int
    as_of: date | None

    # --- planning ---
    obligations: list[ObligationTask]

    # --- concurrent worker output: reducers required ---
    findings: Annotated[list[FindingDraft], operator.add]
    tokens_used: Annotated[int, operator.add]
    cost_usd: Annotated[float, operator.add]

    # --- synthesis ---
    memo: str

    # --- limits ---
    capped: bool
    cap_reason: str | None


def impact_of(value: str) -> ImpactType:
    """Coerce a validated string into the enum, defaulting to NO_MATCH."""
    try:
        return ImpactType(value)
    except ValueError:
        return ImpactType.NO_MATCH
