"""Layer-1 groundedness: programmatic verification that a claim is supported.

This is the check that makes a finding evidence rather than assertion. The
judge quotes; this module re-locates both quotes in the source text and
converts them to offsets. A quote that cannot be found means the model
described something the document does not say, and the claim is rejected —
never stored with a guessed offset.

Layer 2 (an LLM judge over rationales, calibrated against human labels) is a
separate, unimplemented suite; see docs/evaluation.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ai.extraction.schemas import JudgedImpact
from app.ai.extraction.spans import ResolvedSpan, resolve_span
from app.db.models.enums import ImpactType


@dataclass(frozen=True)
class GroundingResult:
    """The outcome of verifying one judged impact."""

    circular_span: ResolvedSpan | None
    clause_span: ResolvedSpan | None
    problem: str | None = None

    @property
    def grounded(self) -> bool:
        return self.problem is None


def verify_judgement(
    judged: JudgedImpact,
    obligation_text: str,
    obligation_char_start: int,
    clause_text: str,
    clause_char_start: int,
) -> GroundingResult:
    """Resolve both quoted spans against their sources.

    ``*_char_start`` are the source's own offsets, so the returned spans are in
    the same coordinate space every other span in the system uses.

    A ``NO_MATCH`` verdict is not required to quote a clause — there is, by
    definition, no clause text supporting it.
    """
    circular_span = None
    if judged.circular_span:
        circular_span = resolve_span(
            judged.circular_span, obligation_text, base_offset=obligation_char_start
        )
        if circular_span is None:
            return GroundingResult(
                None,
                None,
                "circular_span is not a verbatim quote of the obligation",
            )

    clause_span = None
    if judged.impact_type is not ImpactType.NO_MATCH and judged.clause_span:
        clause_span = resolve_span(
            judged.clause_span, clause_text, base_offset=clause_char_start
        )
        if clause_span is None:
            return GroundingResult(
                circular_span,
                None,
                "clause_span is not a verbatim quote of the policy clause",
            )

    return GroundingResult(circular_span, clause_span)


def spans_appear_in_context(spans: list[str], retrieved_texts: list[Any]) -> bool:
    """Whether every span text occurs in the retrieved context.

    The stricter half of layer 1: a finding must not only quote the source, it
    must quote something the retriever actually put in front of the model.
    Used by the groundedness evaluation over stored findings.
    """
    haystack = "\n".join(str(text) for text in retrieved_texts)
    return all(span and span in haystack for span in spans)
