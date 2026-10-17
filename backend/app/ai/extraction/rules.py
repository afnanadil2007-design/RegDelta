"""Rule-based obligation extraction: one obligation per modal sentence.

Used by ``ingestion.extract_obligations --mode rules`` and by the
deterministic provider, so the demo database can be populated and assessed
without a model. It is a seeding aid, not the extraction the project measures,
and it has no notion of confidence, so it reports none.

v2 (2026-10): the actor is the sentence's whole subject phrase before the
modal verb ("The risk disclosure document shall …"), where v1 kept only a run
of capitalised words and so started many obligations mid-sentence; and
cross-reference sentences ("shall read this circular together with …") are
excluded. Revised after inspecting the synthetic corpus, so its scores on that
corpus are not held-out (docs/evaluation.md).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

EXTRACTOR_NAME = "rules-v2"

# A sentence ends at "." or ";" followed by whitespace and an uppercase letter,
# an opening bracket, or a digit; reference numbers use "/" and never split.
_SENTENCE_END = re.compile(r"(?<=[.;])\s+(?=[A-Z(\d])")
# Leading list markers: "1.", "2.1", "3.4.2", "(a)", "(iv)", "(1)".
_ENUMERATOR = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?|\([a-z0-9]{1,4}\))\s+")
_MODAL = re.compile(r"\b(shall|must|may|should)\b")
# Subject phrases longer than this are not a named actor but a clause.
_MAX_ACTOR_WORDS = 8
# Sentences that are structurally obligations but carry no requirement.
_EXCLUDE = re.compile(
    r"(issued in exercise of powers|stand superseded|shall stand modified|"
    r"read (?:this circular )?together with|continue to apply|shall come into force)",
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


def _sentences(text: str) -> list[tuple[int, str]]:
    """(offset, sentence) pairs covering ``text``."""
    out: list[tuple[int, str]] = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        out.append((start, text[start : match.start()]))
        start = match.end()
    out.append((start, text[start:]))
    return out


def extract_obligations_by_rule(text: str) -> list[RuleObligation]:
    out: list[RuleObligation] = []
    for offset, sentence in _sentences(text):
        marker = _ENUMERATOR.match(sentence)
        body_start = marker.end() if marker else 0
        body = sentence[body_start:].rstrip()
        modal = _MODAL.search(body)
        if modal is None or _EXCLUDE.search(body):
            continue
        actor = body[: modal.start()].strip()
        action = body[modal.end() :].strip().rstrip(".;").strip()
        if not actor or len(actor.split()) > _MAX_ACTOR_WORDS or len(action) < 10:
            continue
        span = body.rstrip(";")
        start = offset + body_start
        out.append(
            RuleObligation(
                text=span,
                actor=actor,
                action=action,
                modality=modal.group(1),
                char_start=start,
                char_end=start + len(span),
            )
        )
    return out
