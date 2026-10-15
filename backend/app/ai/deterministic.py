"""A deterministic, rule-based provider behind the gateway interface.

``LLM_PROVIDER=deterministic`` routes gateway calls here instead of to a
model API. It reads the same rendered prompts a model would, recognises the
task from the prompt's data markers, and answers in the same JSON shapes, so
the graph, the grounding check, and the persistence path run unchanged. It
exists so the synthetic demo and the end-to-end tests are reproducible,
offline, and free.

It is not a language model and makes no claim to judge regulation well. Its
verdicts come from a few transparent rules over the obligation and clause
text (term overlap, stated time limits, prohibition versus permission), and
its "confidence" is the term-overlap ratio. Runs it produces are recorded with
provider ``deterministic`` and model ``regdelta-rules-v1``, and the UI labels
them as rule-based.

Quotes are always cut verbatim from the source text, so grounding
verification still has real work to do: the same code path rejects a quote
that does not resolve.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.ai.extraction.rules import extract_obligations_by_rule

# Tag pairs the prompt templates wrap their data in.
_TAGGED = {
    "obligation": re.compile(r"<obligation>\n?(.*?)\n?</obligation>", re.S),
    "clause": re.compile(r"<policy_clause number=\"([^\"]*)\">\n?(.*?)\n?</policy_clause>", re.S),
    "paragraph": re.compile(r"<paragraph>\n?(.*?)\n?</paragraph>", re.S),
    "findings": re.compile(r"<findings>\n?(.*?)\n?</findings>", re.S),
    "circular": re.compile(r"<circular number=\"([^\"]*)\">\n?(.*?)\n?</circular>", re.S),
}

_STOPWORDS = frozenset(
    """a an and any are as at be been by each every for from has have in into is it its
    of on or such that the their them this to under was were which who will with within
    shall must may should not no all also other than only where whether upon per""".split()
)
# Words present in nearly every obligation and clause; they carry no signal
# about *which* requirement is meant.
_GENERIC = frozenset("intermediary intermediarie stock broker client sebi exchange board".split())

# "T+1 day", "6 hours", "five (5) years", "15 calendar days", "30 percent".
_QUANTITY = re.compile(
    r"T\s*\+\s*(?P<t>\d+)"
    r"|(?:\((?P<paren>\d+)\)|(?P<num>\d+))\s*(?:calendar\s+|working\s+|trading\s+)?"
    r"(?P<unit>days?|hours?|years?|months?|percent|%)",
    re.I,
)
_PROHIBITION = re.compile(
    r"\b(?:shall|must|may)\s+not\b|\bprohibited\b|\bno\s+\w+(?:\s+\w+)?\s+shall\b"
    r"|\bunder\s+no\s+circumstance",
    re.I,
)
_PERMISSION = re.compile(r"\bmay\b(?!\s+not)|\bpermitted\b|\bis\s+allowed\b", re.I)

_NO_MATCH_BELOW = 0.25
_COVERED_FROM = 0.5
_MAX_QUOTE = 240


class DeterministicTaskError(ValueError):
    """The prompt is not one of the tasks this provider implements."""


@dataclass(frozen=True)
class _Span:
    text: str
    start: int


def complete(prompt: str) -> str:
    """Answer one rendered prompt with the JSON (or text) a model would return."""
    if "<obligation>" in prompt and "<policy_clause" in prompt:
        return json.dumps(_judge(prompt))
    if "<findings>" in prompt:
        return _memo(prompt)
    if "<paragraph>" in prompt:
        return json.dumps(_extract(prompt))
    raise DeterministicTaskError("the deterministic provider does not implement this prompt")


# --- judge_impact ----------------------------------------------------------


def _judge(prompt: str) -> dict[str, object]:
    obligation = _required(_TAGGED["obligation"], prompt, 1)
    clause_match = _TAGGED["clause"].search(prompt)
    if clause_match is None:
        raise DeterministicTaskError("judge prompt has no policy clause")
    clause_number, clause = clause_match.group(1), clause_match.group(2)

    obligation_terms = _terms(obligation)
    clause_terms = _terms(clause)
    shared = obligation_terms & clause_terms
    overlap = len(shared) / len(obligation_terms) if obligation_terms else 0.0
    circular_quote = _trim(obligation)
    best = _best_sentence(clause, obligation_terms)

    if overlap < _NO_MATCH_BELOW or best is None:
        return _verdict(
            "NO_MATCH",
            overlap,
            circular_quote,
            "",
            f"Clause {clause_number} shares too few terms with the obligation "
            f"({_percent(overlap)} of its content words) to address the same requirement.",
        )

    ob_quantity = _quantity(obligation)
    clause_quantity = _quantity(clause)
    if ob_quantity and clause_quantity and ob_quantity[0] == clause_quantity[0]:
        unit, ob_value, ob_text = ob_quantity
        _, clause_value, clause_text = clause_quantity
        if ob_value != clause_value:
            return _verdict(
                "MODIFIED",
                overlap,
                _sentence_around(obligation, ob_text),
                _sentence_around(clause, clause_text),
                f"Both texts set a limit in {unit}, but the obligation states "
                f"{ob_text.strip()} while clause {clause_number} states "
                f"{clause_text.strip()}; the clause needs its figure updated.",
            )

    ob_prohibits = bool(_PROHIBITION.search(obligation))
    clause_prohibits = bool(_PROHIBITION.search(best.text))
    if ob_prohibits != clause_prohibits and overlap >= 0.4:
        permissive = obligation if not ob_prohibits else best.text
        if _PERMISSION.search(permissive):
            return _verdict(
                "CONFLICT",
                overlap,
                circular_quote,
                best.text,
                f"One text prohibits what the other permits: the obligation "
                f"{'forbids' if ob_prohibits else 'allows'} the conduct that clause "
                f"{clause_number} {'allows' if ob_prohibits else 'forbids'}.",
            )

    if overlap >= _COVERED_FROM:
        return _verdict(
            "ALREADY_COVERED",
            overlap,
            circular_quote,
            best.text,
            f"Clause {clause_number} addresses the same requirement "
            f"({_percent(overlap)} of the obligation's content words recur in it) and "
            "states no conflicting figure.",
        )
    return _verdict(
        "NEW_REQUIREMENT",
        overlap,
        circular_quote,
        best.text,
        f"Clause {clause_number} covers related ground but does not state this "
        "requirement; only part of the obligation's wording recurs in it.",
    )


def _verdict(
    impact: str, overlap: float, circular_span: str, clause_span: str, rationale: str
) -> dict[str, object]:
    return {
        "impact_type": impact,
        "rationale": rationale,
        "confidence": round(overlap, 2),
        "circular_span": circular_span,
        "clause_span": clause_span,
    }


# --- synthesize_memo ---------------------------------------------------------


def _memo(prompt: str) -> str:
    raw = _required(_TAGGED["findings"], prompt, 1)
    findings = json.loads(raw)
    circular = _TAGGED["circular"].search(prompt)
    number = circular.group(1) if circular else "this circular"

    by_impact: dict[str, list[str]] = {}
    for finding in findings:
        clause = finding.get("clause") or "no clause"
        by_impact.setdefault(str(finding.get("impact")), []).append(str(clause))

    def listed(impact: str) -> str:
        clauses = sorted(set(by_impact.get(impact, [])))
        return ", ".join(clauses) if clauses else "none"

    lines = [
        "Generated by the deterministic demo provider (rule-based, not a language model).",
        "",
        f"Summary: {len(findings)} verified finding(s) for {number}.",
        "",
        f"What needs to change — conflicts: {listed('CONFLICT')}; "
        f"modifications: {listed('MODIFIED')}.",
        f"Gaps — new requirements against: {listed('NEW_REQUIREMENT')}; "
        f"obligations with no matching clause: {len(by_impact.get('NO_MATCH', []))}.",
        f"Already covered: {listed('ALREADY_COVERED')}.",
    ]
    return "\n".join(lines)


# --- extract_obligations -----------------------------------------------------


def _extract(prompt: str) -> dict[str, object]:
    paragraph = _required(_TAGGED["paragraph"], prompt, 1)
    return {
        "obligations": [
            {
                "text": item.text,
                "actor": item.actor,
                "action": item.action,
                "modality": item.modality,
                "deadline": None,
                "condition": None,
                "confidence": None,
            }
            for item in extract_obligations_by_rule(paragraph)
        ]
    }


# --- text helpers -------------------------------------------------------------


def _required(pattern: re.Pattern[str], prompt: str, group: int) -> str:
    match = pattern.search(prompt)
    if match is None:
        raise DeterministicTaskError(f"prompt is missing {pattern.pattern[:20]!r}")
    return match.group(group)


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def _terms(text: str) -> set[str]:
    words = re.findall(r"[a-z][a-z\-]+", text.lower())
    stems = {_stem(w) for w in words if w not in _STOPWORDS}
    return {s for s in stems if s not in _GENERIC and len(s) > 2}


def _quantity(text: str) -> tuple[str, int, str] | None:
    """(unit family, value, matched text) of the first stated time/percent limit."""
    match = _QUANTITY.search(text)
    if match is None:
        return None
    if match.group("t"):
        return "T+ settlement days", int(match.group("t")), match.group(0)
    value = int(match.group("paren") or match.group("num"))
    unit = match.group("unit").lower().rstrip("s")
    return ("percent" if unit in {"percent", "%"} else unit + "s"), value, match.group(0)


def _sentences(text: str) -> list[_Span]:
    """Sentence-like spans of ``text`` with their offsets.

    A leading markdown heading line (a policy clause's ``### C.3 …``) is not
    part of any sentence.
    """
    body_start = 0
    if text.lstrip().startswith("#"):
        newline = text.find("\n")
        body_start = newline + 1 if newline != -1 else len(text)
    spans: list[_Span] = []
    for match in re.finditer(r"[^.;]+[.;]?", text[body_start:]):
        piece = match.group(0)
        stripped = piece.strip()
        if len(stripped) < 12:
            continue
        start = body_start + match.start() + (len(piece) - len(piece.lstrip()))
        spans.append(_Span(stripped, start))
    return spans


def _best_sentence(text: str, terms: set[str]) -> _Span | None:
    best: _Span | None = None
    best_score = 0
    for span in _sentences(text):
        score = len(_terms(span.text) & terms)
        if score > best_score:
            best, best_score = span, score
    if best is None:
        return None
    return _Span(_trim(best.text), best.start)


def _sentence_around(text: str, fragment: str) -> str:
    for span in _sentences(text):
        if fragment in span.text:
            return _trim(span.text)
    return fragment


def _trim(text: str) -> str:
    """At most ``_MAX_QUOTE`` characters, cut at a word boundary (still verbatim)."""
    text = text.strip()
    if len(text) <= _MAX_QUOTE:
        return text
    cut = text[:_MAX_QUOTE]
    return cut[: cut.rfind(" ")].rstrip(",;:") if " " in cut else cut


def _percent(value: float) -> str:
    return f"{round(value * 100)}%"
