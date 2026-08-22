"""Stage 3 unit tests: quality scoring, segmentation offsets, chunking."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from app.ai.extraction.chunking import chunk_paragraphs, estimate_tokens
from app.ai.extraction.pdf import extract_pages, render_page_png
from app.ai.extraction.segment import normalise, segment_pages, split_page_blocks
from app.db.models.enums import ExtractionMethod
from tests.fixtures import ALL_FIXTURES, write_fixture_pdf, write_scanned_pdf

PAGE_ONE = """SEBI/HO/MIRSD/CIR/P/2024/17

UPFRONT COLLECTION OF MARGINS

1. All stock brokers shall collect upfront margin from clients.

2.1 The margin shall be collected before the order is placed.

2.2 Brokers shall report short-collection by T+1 day.
"""

PAGE_TWO = """ANNEXURE A

| Segment | Margin % |
| --- | --- |
| Cash | 20 |

3. This circular supersedes SEBI/HO/MIRSD/CIR/P/2020/99 dated October 06, 2020.
"""


def _segment_two_pages():
    return segment_pages(
        [
            (1, PAGE_ONE, ExtractionMethod.TEXT, 0.8),
            (2, PAGE_TWO, ExtractionMethod.VISION, 0.05),
        ]
    )


# --- segmentation / the offset contract ---------------------------------


def test_every_paragraph_span_resolves_exactly() -> None:
    """The invariant the whole system rests on, at the point it is created."""
    full_text, paragraphs = _segment_two_pages()
    assert paragraphs
    for para in paragraphs:
        assert full_text[para.char_start : para.char_end] == para.text


def test_spans_are_ordered_and_non_overlapping() -> None:
    _, paragraphs = _segment_two_pages()
    for prev, nxt in zip(paragraphs, paragraphs[1:], strict=False):
        assert prev.char_end <= nxt.char_start


def test_paragraph_numbers_and_headings_are_captured() -> None:
    _, paragraphs = _segment_two_pages()
    numbers = [p.para_number for p in paragraphs if p.para_number]
    assert numbers == ["1", "2.1", "2.2", "3"]
    assert any(p.heading_path == "UPFRONT COLLECTION OF MARGINS" for p in paragraphs)
    assert any(p.heading_path == "ANNEXURE A" for p in paragraphs)


def test_markdown_table_is_not_split_across_paragraphs() -> None:
    """Vision emits markdown tables; a split table is a corrupted table."""
    _, paragraphs = _segment_two_pages()
    table_paras = [p for p in paragraphs if "|" in p.text]
    assert len(table_paras) == 1
    assert table_paras[0].text.count("\n") >= 2


def test_extraction_method_is_recorded_per_page() -> None:
    _, paragraphs = _segment_two_pages()
    assert {p.extraction_method for p in paragraphs if p.page_number == 1} == {
        ExtractionMethod.TEXT
    }
    assert {p.extraction_method for p in paragraphs if p.page_number == 2} == {
        ExtractionMethod.VISION
    }


def test_normalise_collapses_line_endings_and_blank_runs() -> None:
    assert normalise("a\r\n\r\n\r\n\r\nb") == "a\n\nb"
    assert normalise("trailing   \nnext") == "trailing\nnext"


def test_blank_input_produces_no_paragraphs() -> None:
    full_text, paragraphs = segment_pages([(1, "   \n\n  ", ExtractionMethod.TEXT, 0.0)])
    assert paragraphs == []
    assert full_text == ""


def test_split_page_blocks_starts_a_block_at_each_number() -> None:
    blocks = split_page_blocks(normalise(PAGE_ONE))
    assert sum(1 for b in blocks if b.startswith(("1.", "2.1", "2.2"))) == 3


# --- chunking -----------------------------------------------------------


def test_chunks_never_split_a_paragraph() -> None:
    _, paragraphs = _segment_two_pages()
    chunks = chunk_paragraphs(paragraphs, target_tokens=40, overlap_tokens=10)
    covered = {i for c in chunks for i in c.paragraph_indices}
    assert covered == {p.order_index for p in paragraphs}


def test_chunk_text_equals_its_span_of_full_text() -> None:
    """Chunks are contiguous paragraph runs, so their span must resolve."""
    full_text, paragraphs = _segment_two_pages()
    for chunk in chunk_paragraphs(paragraphs, target_tokens=40, overlap_tokens=10):
        assert full_text[chunk.char_start : chunk.char_end] == chunk.text


def test_oversized_paragraph_becomes_its_own_chunk() -> None:
    long_text = "9. " + ("The broker shall maintain records. " * 200)
    _, paragraphs = segment_pages([(1, long_text, ExtractionMethod.TEXT, 0.9)])
    chunks = chunk_paragraphs(paragraphs, target_tokens=400, overlap_tokens=60)
    assert len(chunks) == 1
    assert chunks[0].token_count > 400


def test_overlap_repeats_trailing_paragraphs() -> None:
    _, paragraphs = _segment_two_pages()
    chunks = chunk_paragraphs(paragraphs, target_tokens=30, overlap_tokens=20)
    assert len(chunks) > 1
    overlaps = [
        set(a.paragraph_indices) & set(b.paragraph_indices)
        for a, b in zip(chunks, chunks[1:], strict=False)
    ]
    assert any(overlaps), "expected at least one chunk pair to share a paragraph"


def test_estimate_tokens_is_monotonic() -> None:
    assert estimate_tokens("short") < estimate_tokens("short" * 50)


# --- PDF extraction and quality scoring ---------------------------------


def test_text_pdf_scores_above_threshold_and_skips_vision(tmp_path: Path) -> None:
    pdf = write_fixture_pdf(ALL_FIXTURES[0], tmp_path)
    pages = extract_pages(str(pdf), quality_threshold=0.15)
    assert len(pages) == 2
    assert all(not p.needs_vision for p in pages), "clean text must not take vision"
    assert all(p.text_quality_score > 0.15 for p in pages)


def test_quality_score_separates_real_pages_from_scanned_ones(tmp_path: Path) -> None:
    """Calibration guard.

    Real SEBI layout is sparse (~400-600 chars/page), so the score must still
    rank every genuine page far above an image-only one. If this margin
    collapses, ingestion starts paying for vision on pages that parse fine.
    """
    real_scores = []
    for fixture in ALL_FIXTURES:
        pdf = write_fixture_pdf(fixture, tmp_path / fixture.circular_number[-5:])
        real_scores += [p.text_quality_score for p in extract_pages(str(pdf), 0.15)]
    scanned = extract_pages(str(write_scanned_pdf(tmp_path / "scan")), 0.15)[0]

    assert scanned.text_quality_score == 0.0
    assert min(real_scores) > 0.15 * 2, (
        f"real pages score too close to the threshold: {sorted(real_scores)}"
    )


def test_scanned_pdf_scores_low_and_requests_vision(tmp_path: Path) -> None:
    pdf = write_scanned_pdf(tmp_path)
    pages = extract_pages(str(pdf), quality_threshold=0.15)
    assert len(pages) == 1
    assert pages[0].text_quality_score < 0.15
    assert pages[0].needs_vision


def test_render_page_png_produces_a_png(tmp_path: Path) -> None:
    pdf = write_fixture_pdf(ALL_FIXTURES[1], tmp_path)
    png = render_page_png(str(pdf), 1, dpi=200)
    assert png.startswith(b"\x89PNG\r\n")
    assert len(png) > 1000


def test_extract_pages_routes_each_page_independently(tmp_path: Path) -> None:
    """An image-only page takes vision; a real text page beside it does not."""
    path = tmp_path / "mixed.pdf"
    doc = pymupdf.open()
    doc.new_page()  # image-only: no text layer at all
    page = doc.new_page()
    page.insert_textbox(
        pymupdf.Rect(56, 56, 556, 736),
        ALL_FIXTURES[2].pages[0],
        fontsize=11,
        fontname="helv",
    )
    doc.save(str(path))
    doc.close()

    pages = extract_pages(str(path), quality_threshold=0.15)
    assert len(pages) == 2
    assert pages[0].needs_vision, "image-only page must take the vision path"
    assert not pages[1].needs_vision, "real text page must not take the vision path"


@pytest.mark.parametrize("fixture", ALL_FIXTURES, ids=lambda f: f.circular_number)
def test_all_fixtures_round_trip_through_extraction(fixture, tmp_path: Path) -> None:
    pdf = write_fixture_pdf(fixture, tmp_path)
    pages = extract_pages(str(pdf), quality_threshold=0.15)
    inputs = [
        (p.page_number, p.text, ExtractionMethod.TEXT, p.text_quality_score) for p in pages
    ]
    full_text, paragraphs = segment_pages(inputs)
    assert paragraphs
    for para in paragraphs:
        assert full_text[para.char_start : para.char_end] == para.text
    # The reference number survives extraction intact — the citation graph
    # depends on it matching character for character.
    assert fixture.circular_number in full_text.replace("\n", "")
