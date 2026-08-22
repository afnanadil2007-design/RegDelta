"""Extract obligations from paragraphs, with span validation and one repair.

Two guards make an extraction trustworthy:

1. **Schema validation.** The model's JSON must satisfy ``ObligationExtraction``.
   A violation gets exactly one repair attempt with the validation error fed
   back; a second failure records an extraction failure and returns nothing.
2. **Span resolution.** Each obligation's quoted text must be locatable inside
   the source paragraph. An obligation whose quote does not resolve is
   *dropped*, because a span that cannot be verified cannot be shown to an
   analyst as evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.ai.extraction.schemas import (
    ExtractedObligation,
    ObligationExtraction,
    json_schema_for,
)
from app.ai.extraction.spans import ResolvedSpan, resolve_span
from app.ai.gateway import GatewayError, LLMGateway
from app.ai.prompts import load_prompt
from app.core.logging import get_logger

log = get_logger("app.ai.extraction.obligations")

_SCHEMA = json_schema_for(ObligationExtraction)


@dataclass
class ObligationCandidate:
    """A validated obligation whose span resolved against the source."""

    extracted: ExtractedObligation
    span: ResolvedSpan


@dataclass
class ExtractionOutcome:
    candidates: list[ObligationCandidate] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    repaired: bool = False
    failed: bool = False
    failure_reason: str | None = None
    dropped_unresolvable: int = 0


def _parse(payload: str) -> ObligationExtraction:
    """Parse and validate; raises ValidationError or ValueError."""
    text = payload.strip()
    # Structured outputs return bare JSON, but a fenced block is a common
    # near-miss and is cheap to tolerate.
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    return ObligationExtraction.model_validate(json.loads(text))


def extract_from_paragraph(
    gateway: LLMGateway,
    paragraph_text: str,
    paragraph_char_start: int,
) -> ExtractionOutcome:
    """Extract obligations from one paragraph.

    ``paragraph_char_start`` is the paragraph's offset into the circular's
    full text, so resolved spans come back in full-text coordinates and need
    no further arithmetic at the call site.
    """
    outcome = ExtractionOutcome()
    prompt = load_prompt("extract_obligations").replace("{paragraph}", paragraph_text)

    try:
        response = gateway.complete(prompt, json_schema=_SCHEMA)
    except GatewayError as exc:
        outcome.failed = True
        outcome.failure_reason = f"gateway: {exc}"
        return outcome

    outcome.tokens_in += response.tokens_in
    outcome.tokens_out += response.tokens_out
    outcome.cost_usd += response.cost_usd

    if response.refused:
        outcome.failed = True
        outcome.failure_reason = "provider refused the request"
        return outcome

    try:
        parsed = _parse(response.text)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        parsed_or_none, repair = _repair(gateway, prompt, response.text, str(exc), outcome)
        if parsed_or_none is None:
            outcome.failed = True
            outcome.failure_reason = f"schema violation after repair: {repair}"
            log.warning("obligations.extraction_failed", extra={"error": repair})
            return outcome
        parsed = parsed_or_none
        outcome.repaired = True

    for item in parsed.obligations:
        span = resolve_span(item.text, paragraph_text, base_offset=paragraph_char_start)
        if span is None:
            # An unverifiable quote is dropped, not stored with a guessed span.
            outcome.dropped_unresolvable += 1
            continue
        outcome.candidates.append(ObligationCandidate(extracted=item, span=span))

    return outcome


def _repair(
    gateway: LLMGateway,
    original_prompt: str,
    bad_output: str,
    error: str,
    outcome: ExtractionOutcome,
) -> tuple[ObligationExtraction | None, str]:
    """One repair attempt, feeding the validation error back to the model."""
    repair_prompt = (
        f"{original_prompt}\n\n"
        "## Repair required\n\n"
        "Your previous response did not satisfy the schema.\n\n"
        f"Previous response:\n{bad_output[:2000]}\n\n"
        f"Validation error:\n{error}\n\n"
        "Return corrected JSON only. Do not explain the correction."
    )
    try:
        response = gateway.complete(repair_prompt, json_schema=_SCHEMA)
    except GatewayError as exc:
        return None, f"gateway during repair: {exc}"

    outcome.tokens_in += response.tokens_in
    outcome.tokens_out += response.tokens_out
    outcome.cost_usd += response.cost_usd

    try:
        return _parse(response.text), ""
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        return None, str(exc)
