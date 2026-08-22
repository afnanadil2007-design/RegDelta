"""Structural chunking over paragraph boundaries.

Chunks are built by accumulating *whole* paragraphs — a paragraph is never
split, so every chunk boundary is also a paragraph boundary and every chunk's
span is a contiguous range of the circular's full text. A paragraph that on
its own exceeds the target size becomes a chunk of one rather than being cut.

Because paragraphs are contiguous in ``full_text`` and joined by the same
separator, a chunk's text is exactly ``full_text[char_start:char_end]``. The
integration test asserts this rather than trusting it.

Size is measured with a character-per-token approximation, not a real
tokenizer: chunk sizing only needs to keep chunks comfortably under the
embedding model's 512-token window, and calling a tokenizer per candidate
chunk across a 300-document corpus would dominate ingestion time for no
accuracy that matters here. ``token_count`` is therefore an estimate, and is
labelled as such wherever it surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.extraction.segment import SegmentedParagraph

# Mean characters per token for English prose under a subword tokenizer.
_CHARS_PER_TOKEN = 4.0
_SEPARATOR_LEN = 2  # "\n\n", matching segment._SEPARATOR


@dataclass
class Chunk:
    """A retrieval unit spanning one or more whole paragraphs."""

    order_index: int
    text: str
    char_start: int
    char_end: int
    token_count: int  # estimated; see module docstring
    heading_path: str | None
    paragraph_indices: list[int]  # order_index values, resolved to DB ids on save


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / _CHARS_PER_TOKEN))


def _emit(
    order_index: int, group: list[SegmentedParagraph]
) -> Chunk:
    text = "\n\n".join(p.text for p in group)
    return Chunk(
        order_index=order_index,
        text=text,
        char_start=group[0].char_start,
        char_end=group[-1].char_end,
        token_count=estimate_tokens(text),
        # A chunk's heading is the heading in force where it starts.
        heading_path=group[0].heading_path,
        paragraph_indices=[p.order_index for p in group],
    )


def _overlap_tail(
    group: list[SegmentedParagraph], overlap_tokens: int
) -> list[SegmentedParagraph]:
    """Trailing whole paragraphs that fit the overlap budget, in order."""
    tail: list[SegmentedParagraph] = []
    budget = overlap_tokens
    for para in reversed(group):
        cost = estimate_tokens(para.text)
        if cost > budget:
            break
        tail.insert(0, para)
        budget -= cost
    return tail


def chunk_paragraphs(
    paragraphs: list[SegmentedParagraph],
    *,
    target_tokens: int = 400,
    overlap_tokens: int = 60,
) -> list[Chunk]:
    """Group paragraphs into ~``target_tokens`` chunks with a trailing overlap."""
    if not paragraphs:
        return []

    chunks: list[Chunk] = []
    group: list[SegmentedParagraph] = []
    group_tokens = 0

    for para in paragraphs:
        para_tokens = estimate_tokens(para.text)

        # Flush before adding, so the target is a ceiling rather than a floor.
        if group and group_tokens + para_tokens > target_tokens:
            chunks.append(_emit(len(chunks), group))
            carry = _overlap_tail(group, overlap_tokens)
            group = list(carry)
            group_tokens = sum(estimate_tokens(p.text) for p in group)

        group.append(para)
        group_tokens += para_tokens

        # An oversized paragraph stands alone: emit immediately and reset, so
        # it is never merged with neighbours and never cut in half.
        if para_tokens >= target_tokens:
            chunks.append(_emit(len(chunks), group))
            group = []
            group_tokens = 0

    if group:
        chunks.append(_emit(len(chunks), group))
    return chunks
