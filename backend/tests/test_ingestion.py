"""Stage 3 integration tests: full ingestion of 3 circulars, against Postgres.

These assert the provenance chain end-to-end — that what is stored in the
database still satisfies the offset contract after a round trip, not merely
that the in-memory segmenter is self-consistent.
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

from app.ai.gateway import GatewayError, LLMGateway, LLMResponse
from app.core.config import get_settings
from app.db.models.enums import ExtractionMethod
from app.repositories.circulars import ChunkRepository, CircularRepository, ParagraphRepository
from app.services.ingestion import CircularMeta, ingest_batch, ingest_pdf
from tests.fixtures import ALL_FIXTURES, write_fixture_pdf, write_scanned_pdf


class FakeGateway(LLMGateway):
    """Records vision calls and returns a canned transcription.

    Ingestion tests must not hit a real provider: they would be slow, costly,
    and non-deterministic. The vision *routing* is what is under test here.
    """

    def __init__(self, text: str = "1. Transcribed by vision.\n\n| A | B |\n| - | - |\n| 1 | 2 |"):
        self.calls = 0
        self._text = text

    def complete_vision(self, prompt, image_png, **kwargs) -> LLMResponse:  # type: ignore[override]
        self.calls += 1
        return LLMResponse(
            text=self._text,
            model="fake",
            provider="fake",
            tokens_in=10,
            tokens_out=20,
            cost_usd=0.0,
            latency_ms=1,
            stop_reason="end_turn",
        )


class FailingGateway(LLMGateway):
    """Every vision call fails — exercises the degrade-to-text path."""

    def __init__(self) -> None:
        self.calls = 0

    def complete_vision(self, prompt, image_png, **kwargs) -> LLMResponse:  # type: ignore[override]
        self.calls += 1
        raise GatewayError("provider unavailable")


def _unique(circular_number: str) -> str:
    """Namespace a fixture's number to this test run.

    ``circulars.circular_number`` is unique, and the same dev database may
    already hold a demo corpus (``make ingest``). Without this, a developer who
    seeds the database cannot run the test suite.
    """
    return f"{circular_number}/T{uuid.uuid4().hex[:8]}"


def _meta(fixture, n: int) -> CircularMeta:
    return CircularMeta(
        circular_number=_unique(fixture.circular_number),
        title=fixture.title,
        issue_date=date(2024, 1, n + 1),
        department="MIRSD",
        source_url=f"https://example.invalid/{n}",
    )


@pytest.mark.asyncio
async def test_ingest_three_circulars_end_to_end(session, tmp_path: Path) -> None:
    items = [
        (write_fixture_pdf(f, tmp_path / str(i)), _meta(f, i)) for i, f in enumerate(ALL_FIXTURES)
    ]
    report = await ingest_batch(session, items, gateway=FakeGateway())

    assert len(report.ingested) == 3, report.failed
    assert not report.failed

    circulars = CircularRepository(session)
    for _, meta in items:
        circular = await circulars.get_by_number(meta.circular_number)
        assert circular is not None
        assert circular.full_text
        assert circular.checksum and len(circular.checksum) == 64
        assert circular.page_count >= 1

        paragraphs = await ParagraphRepository(session).list_for_circular(circular.id)
        assert paragraphs, f"no paragraphs for {meta.circular_number}"
        # The provenance contract, verified against what the database returned.
        for para in paragraphs:
            assert circular.full_text[para.char_start : para.char_end] == para.text

        chunks = await ChunkRepository(session).list_for_circular(circular.id)
        assert chunks
        para_ids = {p.id for p in paragraphs}
        for chunk in chunks:
            assert circular.full_text[chunk.char_start : chunk.char_end] == chunk.text
            assert chunk.paragraph_ids, "a chunk must record the paragraphs it spans"
            assert set(chunk.paragraph_ids) <= para_ids


@pytest.mark.asyncio
async def test_chunks_cover_every_paragraph(session, tmp_path: Path) -> None:
    fixture = ALL_FIXTURES[0]
    pdf = write_fixture_pdf(fixture, tmp_path)
    circular = await ingest_pdf(session, pdf, _meta(fixture, 0), gateway=FakeGateway())
    assert circular is not None

    paragraphs = await ParagraphRepository(session).list_for_circular(circular.id)
    chunks = await ChunkRepository(session).list_for_circular(circular.id)
    covered = {pid for c in chunks for pid in c.paragraph_ids}
    assert covered == {p.id for p in paragraphs}


@pytest.mark.asyncio
async def test_reingesting_the_same_pdf_is_skipped(session, tmp_path: Path) -> None:
    """Checksum makes re-ingestion idempotent rather than duplicating a circular."""
    fixture = ALL_FIXTURES[1]
    pdf = write_fixture_pdf(fixture, tmp_path)
    meta = _meta(fixture, 0)

    first = await ingest_pdf(session, pdf, meta, gateway=FakeGateway())
    await session.commit()
    assert first is not None

    # Same bytes, so the checksum matches and the second pass is a no-op.
    second = await ingest_pdf(session, pdf, meta, gateway=FakeGateway())
    assert second is None

    count = (
        await session.execute(
            text("SELECT count(*) FROM circulars WHERE circular_number = :n"),
            {"n": meta.circular_number},
        )
    ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_vision_runs_only_on_low_quality_pages(session, tmp_path: Path) -> None:
    """Vision is expensive; clean pages must never take that path."""
    gateway = FakeGateway()
    fixture = ALL_FIXTURES[2]
    pdf = write_fixture_pdf(fixture, tmp_path)
    circular = await ingest_pdf(session, pdf, _meta(fixture, 0), gateway=gateway)

    assert circular is not None
    assert gateway.calls == 0, "clean text pages must not call the vision model"
    assert circular.vision_page_count == 0

    paragraphs = await ParagraphRepository(session).list_for_circular(circular.id)
    assert all(p.extraction_method is ExtractionMethod.TEXT for p in paragraphs)


@pytest.mark.asyncio
async def test_scanned_page_takes_vision_and_is_recorded_as_such(session, tmp_path: Path) -> None:
    gateway = FakeGateway()
    pdf = write_scanned_pdf(tmp_path)
    meta = CircularMeta(
        circular_number=_unique("SEBI/HO/TEST/SCAN/2024/1"), title="Scanned fixture"
    )

    circular = await ingest_pdf(session, pdf, meta, gateway=gateway)
    assert circular is not None
    assert gateway.calls == 1
    assert circular.vision_page_count == 1

    paragraphs = await ParagraphRepository(session).list_for_circular(circular.id)
    assert any(p.extraction_method is ExtractionMethod.VISION for p in paragraphs)
    # The markdown table the vision model returned survives as one paragraph.
    assert any("|" in p.text for p in paragraphs)


@pytest.mark.asyncio
async def test_vision_failure_degrades_to_text_without_losing_the_document(
    session, tmp_path: Path
) -> None:
    """A provider outage must not abort ingestion of an otherwise good PDF.

    The document here mixes a scanned page (which attempts vision and fails)
    with a clean text page, so the degraded path is exercised alongside a page
    that never needed it.
    """
    import pymupdf

    path = tmp_path / "mixed.pdf"
    doc = pymupdf.open()
    doc.new_page()  # scanned: attempts vision
    page = doc.new_page()
    page.insert_textbox(
        pymupdf.Rect(56, 56, 556, 736), ALL_FIXTURES[0].pages[0], fontsize=11, fontname="helv"
    )
    doc.save(str(path))
    doc.close()

    gateway = FailingGateway()
    meta = CircularMeta(circular_number=_unique("SEBI/HO/TEST/DEGRADE/2024/1"), title="Mixed")
    circular = await ingest_pdf(session, path, meta, gateway=gateway)

    assert circular is not None
    assert gateway.calls == 1, "the scanned page should have attempted vision"
    assert circular.vision_page_count == 0, "a failed vision call is not a vision page"
    paragraphs = await ParagraphRepository(session).list_for_circular(circular.id)
    assert paragraphs, "document must still be ingested from its text layer"
    assert all(p.extraction_method is ExtractionMethod.TEXT for p in paragraphs)


@pytest.mark.asyncio
async def test_one_bad_pdf_does_not_abort_the_batch(session, tmp_path: Path) -> None:
    """Failure isolation: the corrupt file is reported, the rest still land."""
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.7\nthis is not a valid pdf body")

    items = [
        (write_fixture_pdf(ALL_FIXTURES[0], tmp_path / "a"), _meta(ALL_FIXTURES[0], 0)),
        (
            broken,
            CircularMeta(circular_number=_unique("SEBI/HO/TEST/BROKEN/2024/9"), title="Broken"),
        ),
        (write_fixture_pdf(ALL_FIXTURES[1], tmp_path / "b"), _meta(ALL_FIXTURES[1], 1)),
    ]
    report = await ingest_batch(session, items, gateway=FakeGateway())

    assert len(report.ingested) == 2
    assert len(report.failed) == 1
    assert report.failed[0][0].startswith("SEBI/HO/TEST/BROKEN/2024/9")


@pytest.mark.asyncio
async def test_vision_fraction_is_reported(session, tmp_path: Path) -> None:
    """The fraction of pages taking the vision path is an ingestion KPI."""
    items = [
        (write_fixture_pdf(ALL_FIXTURES[0], tmp_path / "a"), _meta(ALL_FIXTURES[0], 0)),
        (
            write_scanned_pdf(tmp_path / "b"),
            CircularMeta(circular_number=_unique("SEBI/HO/TEST/SCAN/2024/2"), title="Scan"),
        ),
    ]
    report = await ingest_batch(session, items, gateway=FakeGateway())

    assert report.total_pages == 3  # 2 text pages + 1 scanned
    # Only the scanned page takes vision; both real pages parse cleanly.
    assert report.vision_pages == 1
    assert report.vision_fraction == pytest.approx(1 / 3)


def test_settings_expose_the_ingestion_knobs() -> None:
    settings = get_settings()
    assert 0.0 < settings.text_quality_threshold < 1.0
    assert settings.vision_dpi == 200
    assert settings.scrape_delay_seconds >= 2.0
