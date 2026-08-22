"""Resolve a quoted span back to offsets in the source text.

Models cannot count characters, but they can quote. So every span in RegDelta
is produced as a *quote* and converted to offsets here, by code that either
finds the quote or reports that it could not. That makes an unsupported claim
a detectable failure rather than a plausible-looking wrong offset.

Matching is exact first, then whitespace-normalised — a model that collapses a
line break inside a quoted sentence is still quoting faithfully, and rejecting
that would discard good extractions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedSpan:
    char_start: int
    char_end: int
    text: str

    @property
    def length(self) -> int:
        return self.char_end - self.char_start


def _normalise_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def resolve_span(quote: str, source: str, base_offset: int = 0) -> ResolvedSpan | None:
    """Locate ``quote`` inside ``source``; return offsets shifted by base.

    Returns None when the quote cannot be found, which callers must treat as a
    failed extraction — never as a zero-length span.
    """
    quote = quote.strip()
    if not quote or not source:
        return None

    index = source.find(quote)
    if index != -1:
        return ResolvedSpan(base_offset + index, base_offset + index + len(quote), quote)

    # Whitespace-tolerant fallback: match the quote's tokens against the source
    # with flexible separators, so a re-wrapped line still resolves.
    tokens = [re.escape(t) for t in _normalise_ws(quote).split(" ") if t]
    if not tokens:
        return None
    pattern = re.compile(r"\s+".join(tokens))
    match = pattern.search(source)
    if match is None:
        return None
    return ResolvedSpan(
        base_offset + match.start(), base_offset + match.end(), match.group(0)
    )


def span_within(inner: ResolvedSpan, outer_start: int, outer_end: int) -> bool:
    """Whether a resolved span sits inside the given bounds."""
    return outer_start <= inner.char_start < inner.char_end <= outer_end
