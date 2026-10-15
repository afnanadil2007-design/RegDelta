"""Graph state.

``findings`` and ``failed_tasks`` carry ``operator.add`` reducers because the
worker fan-out writes them *concurrently*: every ``assess_obligation`` branch
returns its own values, and without a reducer the last writer would silently
win. Token and cost accounting is not in the state at all; it lives in the
shared ``CallBudget`` (see nodes.py), which is checked before every call.
"""

from __future__ import annotations

import operator
from datetime import date
from typing import Annotated

# LangGraph derives a Pydantic schema from the state; on Python < 3.12
# Pydantic only accepts typing_extensions.TypedDict.
from typing_extensions import TypedDict

from app.db.models.enums import ImpactType


class FindingDraft(TypedDict):
    """A finding as it leaves a worker, ready to persist.

    Offsets are in full-text coordinates (circular) and policy-pack source
    coordinates (clause), the same space every other span uses.
    """

    obligation_id: int
    policy_clause_id: int | None
    clause_number: str | None
    impact_type: str
    rationale: str
    # The judge's self-reported score; None when no judgement was made.
    confidence: float | None
    circular_span_start: int | None
    circular_span_end: int | None
    clause_span_start: int | None
    clause_span_end: int | None
    quote_status: str
    verification_note: str | None
    verification_attempts: int


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
    failed_tasks: Annotated[int, operator.add]

    # --- synthesis ---
    memo: str | None
    # Why the memo is missing when the run otherwise completed.
    memo_note: str | None


def impact_of(value: str) -> ImpactType:
    """Coerce a validated string into the enum; raises on an unknown verdict."""
    return ImpactType(value)
