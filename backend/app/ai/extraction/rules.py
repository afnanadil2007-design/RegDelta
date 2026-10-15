"""Rule-based obligation extraction: a modality regex over paragraph text.

Used by ``ingestion.extract_obligations --mode rules`` and by the
deterministic provider, so the demo database can be populated and assessed
without a model. It is a seeding aid, not the extraction the project measures:
it has no notion of confidence and reports none.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

EXTRACTOR_NAME = "rules-v1"

# "<Actor> shall|must|may|should <action>." — up to four capitalised words of
# actor, then the modality, then an action that runs to the sentence end.
_RULE = re.compile(
    r"(?P<actor>(?:[A-Z][\w'\-]*\s+){0,4}?[A-Za-z][\w'\-]*)\s+"
    r"(?P<modality>shall|must|may|should)\s+"
    r"(?P<action>[^.]{10,400}\.)",
)
# Sentences that are structurally obligations but carry no requirement.
_EXCLUDE = re.compile(
    r"(issued in exercise of powers|stand superseded|shall stand modified|"
    r"shall be read together|continue to apply|shall come into force)",
    re.I,
)


@dataclass(frozen=True)
class RuleObligation:
    """One matched obligation; offsets are relative to the scanned text."""

    text: str
    actor: str
    action: str
    modality: str
    char_start: int
    char_end: int


def extract_obligations_by_rule(text: str) -> list[RuleObligation]:
    out: list[RuleObligation] = []
    for match in _RULE.finditer(text):
        span_text = match.group(0).strip()
        if _EXCLUDE.search(span_text) or len(span_text) < 25:
            continue
        start = match.start() + (len(match.group(0)) - len(match.group(0).lstrip()))
        out.append(
            RuleObligation(
                text=span_text,
                actor=match.group("actor").strip(),
                action=match.group("action").strip().rstrip("."),
                modality=match.group("modality").lower(),
                char_start=start,
                char_end=start + len(span_text),
            )
        )
    return out
