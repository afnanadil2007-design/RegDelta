"""PDF page extraction with a quality score that decides the vision fallback.

Two heuristics decide whether a page's embedded text can be trusted:

*text density* — extractable characters per square inch of page. A scanned
page yields almost none; a normal text page yields tens. Normalised to 0..1
against ``_CHARS_PER_SQIN_FULL`` so the threshold in settings is readable.

*table dominance* — the fraction of the page covered by detected table
bounding boxes. pymupdf's text extraction flattens tables into ambiguous
whitespace, so a table-dominant page goes to vision even when its text layer
is otherwise fine.

Vision is deliberately *not* run on pages that parse cleanly: it is slower and
costs money, and the fraction of pages taking that path is logged as an
ingestion KPI.
"""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf

from app.core.logging import get_logger

log = get_logger("app.ai.extraction.pdf")

# Characters per square inch at which a page is considered to have a fully
# working text layer. Calibrated against real SEBI layout, which is sparse:
# wide margins and short numbered paragraphs mean a legitimate page carries
# only ~400-600 characters, not the ~2800 a dense page of prose would.
# The score's job is to detect whether a text layer exists *at all* — a scanned
# page yields zero characters — so the scale is set near the low end of
# legitimate pages, and the default 0.15 threshold lands at roughly 70
# characters per page. Raising this constant sends real pages to vision.
_CHARS_PER_SQIN_FULL = 5.0
_POINTS_PER_INCH = 72.0
# Above this share of the page covered by tables, prefer vision.
_TABLE_DOMINANT_RATIO = 0.40


@dataclass
class PageExtract:
    """One page's text plus the signals that decided how it was extracted."""

    page_number: int  # 1-indexed, as printed
    text: str
    text_quality_score: float
    table_area_ratio: float
    needs_vision: bool

    @property
    def is_table_dominant(self) -> bool:
        return self.table_area_ratio >= _TABLE_DOMINANT_RATIO


def _page_area_sqin(page: pymupdf.Page) -> float:
    rect = page.rect
    return max((rect.width / _POINTS_PER_INCH) * (rect.height / _POINTS_PER_INCH), 1e-6)


def text_quality_score(page: pymupdf.Page, text: str) -> float:
    """Extractable characters per square inch, normalised to 0..1."""
    density = len(text.strip()) / _page_area_sqin(page)
    return min(1.0, density / _CHARS_PER_SQIN_FULL)


def table_area_ratio(page: pymupdf.Page) -> float:
    """Share of the page covered by detected tables (0..1).

    ``find_tables`` is heuristic and can raise on malformed content streams;
    a failure here means "no tables detected", never an aborted ingestion.
    """
    try:
        tables = page.find_tables()
    except Exception:  # noqa: BLE001 - detection is best-effort by design
        return 0.0

    page_area = abs(page.rect.get_area())
    if page_area <= 0:
        return 0.0

    covered = 0.0
    for table in tables:
        rect = pymupdf.Rect(table.bbox)
        covered += abs(rect.get_area())
    return min(1.0, covered / page_area)


def extract_page(page: pymupdf.Page, quality_threshold: float) -> PageExtract:
    """Extract one page and decide whether it needs the vision path."""
    text = page.get_text("text") or ""
    quality = text_quality_score(page, text)
    tables = table_area_ratio(page)
    needs_vision = quality < quality_threshold or tables >= _TABLE_DOMINANT_RATIO

    return PageExtract(
        page_number=page.number + 1,
        text=text,
        text_quality_score=quality,
        table_area_ratio=tables,
        needs_vision=needs_vision,
    )


def extract_pages(pdf_path: str, quality_threshold: float) -> list[PageExtract]:
    """Extract every page of a PDF, tagging which ones need vision."""
    pages: list[PageExtract] = []
    with pymupdf.open(pdf_path) as doc:
        for page in doc:
            pages.append(extract_page(page, quality_threshold))

    vision_count = sum(1 for p in pages if p.needs_vision)
    log.info(
        "ingest.pages_extracted",
        extra={
            "pdf": pdf_path,
            "pages": len(pages),
            "vision_pages": vision_count,
            "vision_fraction": round(vision_count / len(pages), 3) if pages else 0.0,
        },
    )
    return pages


def render_page_png(pdf_path: str, page_number: int, dpi: int) -> bytes:
    """Render one 1-indexed page to PNG bytes for the vision model."""
    with pymupdf.open(pdf_path) as doc:
        page = doc[page_number - 1]
        pixmap = page.get_pixmap(dpi=dpi)
        return bytes(pixmap.tobytes("png"))
