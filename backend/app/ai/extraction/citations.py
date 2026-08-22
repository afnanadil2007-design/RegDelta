"""Citation and supersession extraction from circular text.

Regex is the primary extractor, not the LLM. SEBI reference numbers are a
structured identifier family, so a regex resolves them deterministically, for
free, and with no hallucination risk. The LLM is reserved for references the
regex resolver cannot bind (Stage 4's ``resolve_ambiguous``) — a fallback, not
the main path.

Unresolved references are kept with ``resolved=False`` rather than discarded:
they measure corpus coverage, and the gold-set builder reports on them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

# --- reference formats --------------------------------------------------
#
# Classic family, in use for most of the corpus:
#   SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2023/17
#   SEBI/HO/CFD/PoD-2/P/CIR/2023/120
#   CIR/MRD/DP/54/2017            (pre-2016 short form)
#
# Newer family introduced alongside the PoD reorganisation:
#   SEBI/HO/DDHS/DDHS-RACPOD1/P/CIR/2023/108
#
# The two share enough structure that one permissive pattern beats two brittle
# ones; the normaliser below collapses the variants to a comparable key.
# One path segment: alphanumeric plus the punctuation SEBI actually uses
# (hyphen, underscore, ampersand, dot), and one optional internal space for
# the handful of references like ``CIR/CFD/POLICY CELL/2/2015``.
_SEG = r"[A-Za-z0-9][A-Za-z0-9&_.\-]*(?: [A-Z][A-Za-z]+)?"

# Departments that appear at the head of the legacy, pre-SEBI-prefix forms.
# Anchoring on a known department is what keeps "2/3 in 2023" from matching.
_DEPT = r"(?:MRD2?|MIRSD|IMD|CFD|ISD|DDHS|OIAE|AFD|ITD|GSD|LAD(?:-NRO)?|DNPD|IVD|CDMRD)"

_SEBI_REF = re.compile(
    r"\b(?:"
    # SEBI-prefixed, both classic and PoD-era: at least three segments,
    # ending in the serial number (which may be zero-padded to 10 digits).
    rf"SEBI(?:[/-]{_SEG}){{2,8}}[/-]\d{{1,10}}"
    # Pre-2016 short form: CIR/MRD/DP/54/2017
    rf"|CIR(?:[/-]{_SEG}){{1,6}}[/-]\d{{4}}(?:[/-]\d{{1,4}})?"
    # Legacy department-first: MRD/DoP/SE/Cir-16/2010, IMD/FII&C/2010/07
    rf"|{_DEPT}(?:[/-]{_SEG}){{1,6}}[/-]\d{{4}}(?:[/-]\d{{1,4}})?"
    r")"
)

# "dated October 06, 2023" / "dated 6 October 2023" / "dated 06.10.2023"
_DATED = re.compile(
    r"\bdated\s+(?:"
    r"(?P<month_first>[A-Z][a-z]+\s+\d{1,2},?\s+\d{4})"
    r"|(?P<day_first>\d{1,2}\s+[A-Z][a-z]+,?\s+\d{4})"
    r"|(?P<numeric>\d{1,2}[./-]\d{1,2}[./-]\d{4})"
    r")",
    re.IGNORECASE,
)

# Language that asserts one circular displaces another.
_SUPERSESSION_CUES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bshall\s+supersede\b", re.I), "supersedes"),
    (re.compile(r"\bstands?\s+superseded\b", re.I), "supersedes"),
    (re.compile(r"\bsupersedes\b", re.I), "supersedes"),
    (re.compile(r"\bstands?\s+rescinded\b", re.I), "rescinds"),
    (re.compile(r"\bhereby\s+rescinded\b", re.I), "rescinds"),
    (re.compile(r"\bstands?\s+withdrawn\b", re.I), "rescinds"),
    (re.compile(r"\brepealed\b", re.I), "rescinds"),
    (re.compile(r"\bshall\s+stand\s+modified\b", re.I), "amends"),
    (re.compile(r"\bpartially\s+modified\b", re.I), "partial"),
    (re.compile(r"\bstands?\s+modified\b", re.I), "amends"),
    (re.compile(r"\bamend(?:ed|ment\s+to)\b", re.I), "amends"),
    # Master circulars list what they replace in an annexure.
    (re.compile(r"\bAnnex(?:ure)?[\s\-–]*1\b", re.I), "supersedes"),
]

_DATE_FORMATS = (
    "%B %d, %Y",
    "%B %d %Y",
    "%d %B %Y",
    "%d %B, %Y",
    "%d.%m.%Y",
    "%d-%m-%Y",
    "%d/%m/%Y",
)


@dataclass(frozen=True)
class RawReference:
    """A reference string found in text, with its offsets into full_text."""

    raw: str
    char_start: int
    char_end: int
    normalised: str


@dataclass(frozen=True)
class DateReference:
    raw: str
    char_start: int
    char_end: int
    parsed: date | None


def normalise_reference(raw: str) -> str:
    """Collapse a reference to a comparable key.

    Uppercased, separators unified to ``/``, and surrounding punctuation
    stripped. Two references that name the same circular normalise equal even
    when one uses hyphens or trailing punctuation.
    """
    text = raw.strip().strip(".,;:()[]").upper().replace("-", "/")
    text = re.sub(r"/{2,}", "/", text)
    return text.strip("/")


def find_references(text: str, offset: int = 0) -> list[RawReference]:
    """All SEBI-style reference strings in ``text``, offset into full_text."""
    seen: set[tuple[int, int]] = set()
    refs: list[RawReference] = []
    for match in _SEBI_REF.finditer(text):
        span = (match.start(), match.end())
        if span in seen:
            continue
        seen.add(span)
        raw = match.group(0)
        refs.append(
            RawReference(
                raw=raw,
                char_start=offset + match.start(),
                char_end=offset + match.end(),
                normalised=normalise_reference(raw),
            )
        )
    return refs


def parse_date_token(token: str) -> date | None:
    cleaned = token.strip().replace(",", "")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt.replace(",", "")).date()
        except ValueError:
            continue
    return None


def find_dated_references(text: str, offset: int = 0) -> list[DateReference]:
    """Date-qualified references such as ``dated October 06, 2023``."""
    out: list[DateReference] = []
    for match in _DATED.finditer(text):
        token = next(g for g in match.groups() if g)
        out.append(
            DateReference(
                raw=match.group(0),
                char_start=offset + match.start(),
                char_end=offset + match.end(),
                parsed=parse_date_token(token),
            )
        )
    return out


def detect_supersession(text: str) -> str | None:
    """The supersession type asserted by this text, if any.

    Returns the ``SupersessionType`` value, or None when the text makes no
    such assertion. The first cue wins; cues are ordered strongest-first so
    "shall supersede" is not shadowed by a later "modified".
    """
    for pattern, kind in _SUPERSESSION_CUES:
        if pattern.search(text):
            return kind
    return None
