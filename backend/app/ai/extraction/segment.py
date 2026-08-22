"""Segment page text into numbered paragraphs and build the circular's full text.

THE OFFSET CONTRACT
-------------------
``full_text`` is *derived from* the paragraphs, not parsed alongside them: each
paragraph's normalised text is appended to a buffer and its ``char_start`` /
``char_end`` recorded as it goes. This makes

    full_text[p.char_start:p.char_end] == p.text

true by construction for every paragraph, rather than true by careful
bookkeeping that can drift. Every downstream span — chunks, citations,
obligations, findings — resolves against this same string.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.db.models.enums import ExtractionMethod

# Paragraph separator inside full_text. Two newlines keeps the text readable
# when displayed raw and gives spans a clean boundary.
_SEPARATOR = "\n\n"

# Numbered paragraph starts seen in SEBI circulars: "1.", "2.1", "3.4.2",
# "(a)", "(iv)". Anchored to line start.
_NUMBERED_START = re.compile(
    r"^\s*(?:"
    r"\d+(?:\.\d+)*\.?"          # 1.  2.1  3.4.2
    r"|\([a-z]{1,3}\)"            # (a) (iv)
    r"|\([0-9]{1,2}\)"            # (1)
    r")\s+\S"
)

# Headings: "ANNEXURE", "PART A", or a short all-caps line. Used for heading_path.
_HEADING = re.compile(
    r"^\s*(?:"
    r"ANNEX(?:URE)?[\s\-–]*[A-Z0-9]*"   # ANNEXURE, ANNEX-1
    r"|PART\s+[A-Z0-9]+"                # PART A
    r"|[A-Z][A-Z \-&,/]{6,}"            # an all-caps title line
    r")\s*$"
)

# A markdown table row, which the vision path emits and must never be split.
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")


@dataclass
class SegmentedParagraph:
    """A paragraph with its resolved offsets into the circular's full text."""

    order_index: int
    text: str
    char_start: int
    char_end: int
    page_number: int
    para_number: str | None
    heading_path: str | None
    extraction_method: ExtractionMethod
    text_quality_score: float | None


def normalise(raw: str) -> str:
    """Normalise page text before any offset is computed.

    Applied once, here, so that stored offsets always index the normalised
    string. Collapses Windows line endings, non-breaking spaces, and runs of
    blank lines; trims trailing whitespace per line.
    """
    text = raw.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _para_number(line: str) -> str | None:
    match = _NUMBERED_START.match(line)
    if not match:
        return None
    return match.group(0).strip().split()[0].rstrip(".")


def split_page_blocks(page_text: str) -> list[str]:
    """Split one page's normalised text into paragraph-sized blocks.

    A new block starts at a numbered paragraph marker, a heading, or a blank
    line. Consecutive markdown table rows are kept together as one block so a
    table is never broken across paragraphs.
    """
    blocks: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            joined = "\n".join(current).strip()
            if joined:
                blocks.append(joined)
            current.clear()

    in_table = False
    for line in page_text.split("\n"):
        is_table_row = bool(_TABLE_ROW.match(line))
        if is_table_row and not in_table:
            flush()
            in_table = True
        elif in_table and not is_table_row:
            flush()
            in_table = False

        starts_new_block = (
            not line.strip() or _NUMBERED_START.match(line) or _HEADING.match(line)
        )
        if not in_table and starts_new_block:
            flush()
            if not line.strip():
                continue
        current.append(line)

    flush()
    return blocks


def segment_pages(
    pages: list[tuple[int, str, ExtractionMethod, float | None]],
) -> tuple[str, list[SegmentedParagraph]]:
    """Build ``(full_text, paragraphs)`` from per-page extracted text.

    Each input tuple is ``(page_number, raw_text, extraction_method, quality)``.
    """
    paragraphs: list[SegmentedParagraph] = []
    buffer: list[str] = []
    cursor = 0
    heading: str | None = None
    order = 0

    for page_number, raw_text, method, quality in pages:
        for block in split_page_blocks(normalise(raw_text)):
            first_line = block.split("\n", 1)[0]
            if _HEADING.match(first_line) and "|" not in block:
                heading = first_line.strip()

            start = cursor
            end = start + len(block)
            paragraphs.append(
                SegmentedParagraph(
                    order_index=order,
                    text=block,
                    char_start=start,
                    char_end=end,
                    page_number=page_number,
                    para_number=_para_number(first_line),
                    heading_path=heading,
                    extraction_method=method,
                    text_quality_score=quality,
                )
            )
            buffer.append(block)
            cursor = end + len(_SEPARATOR)
            order += 1

    return _SEPARATOR.join(buffer), paragraphs
