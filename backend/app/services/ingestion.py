"""Ingestion: PDF on disk → circular + paragraphs + chunks, with provenance.

Failure isolation is a requirement, not a nicety: one malformed PDF in a
300-document batch is logged and skipped, never allowed to abort the run.
``ingest_batch`` therefore catches per-document and returns a report.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.extraction.chunking import chunk_paragraphs
from app.ai.extraction.pdf import PageExtract, extract_pages, render_page_png
from app.ai.extraction.segment import SegmentedParagraph, segment_pages
from app.ai.gateway import GatewayError, LLMGateway
from app.ai.prompts import load_prompt
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.models.corpus import Chunk, Circular, Paragraph
from app.db.models.enums import ExtractionMethod
from app.repositories.circulars import ChunkRepository, CircularRepository, ParagraphRepository

log = get_logger("app.services.ingestion")


@dataclass
class CircularMeta:
    """Metadata that accompanies a PDF (from the scrape manifest)."""

    circular_number: str
    title: str
    issue_date: date | None = None
    department: str | None = None
    doc_type: str = "circular"
    source_url: str | None = None


@dataclass
class IngestReport:
    ingested: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    vision_pages: int = 0
    total_pages: int = 0

    @property
    def vision_fraction(self) -> float:
        return self.vision_pages / self.total_pages if self.total_pages else 0.0


def checksum_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _page_text_via_vision(
    gateway: LLMGateway, pdf_path: Path, page: PageExtract, dpi: int
) -> tuple[str, ExtractionMethod]:
    """Transcribe one page with the vision model, falling back to its text layer.

    A vision failure degrades to the embedded text rather than losing the page:
    partial text beats a hole in the corpus, and the method recorded stays
    honest about which path produced it.
    """
    try:
        png = render_page_png(str(pdf_path), page.page_number, dpi)
        response = gateway.complete_vision(load_prompt("vision_page"), png)
        if response.refused or not response.text.strip():
            raise GatewayError(f"vision returned no text (stop={response.stop_reason})")
        return response.text, ExtractionMethod.VISION
    except Exception as exc:  # noqa: BLE001 - a page never aborts the document
        log.warning(
            "ingest.vision_failed",
            extra={"pdf": str(pdf_path), "page": page.page_number, "error": str(exc)},
        )
        return page.text, ExtractionMethod.TEXT


def build_pages(
    pdf_path: Path, settings: Settings, gateway: LLMGateway | None
) -> tuple[list[tuple[int, str, ExtractionMethod, float | None]], int]:
    """Extract every page, routing only low-quality/table-dominant ones to vision."""
    extracts = extract_pages(str(pdf_path), settings.text_quality_threshold)
    resolved: list[tuple[int, str, ExtractionMethod, float | None]] = []
    vision_used = 0

    for page in extracts:
        if page.needs_vision and gateway is not None:
            text, method = _page_text_via_vision(gateway, pdf_path, page, settings.vision_dpi)
            if method is ExtractionMethod.VISION:
                vision_used += 1
        else:
            text, method = page.text, ExtractionMethod.TEXT
        resolved.append((page.page_number, text, method, page.text_quality_score))

    return resolved, vision_used


async def ingest_pdf(
    session: AsyncSession,
    pdf_path: Path,
    meta: CircularMeta,
    *,
    settings: Settings | None = None,
    gateway: LLMGateway | None = None,
) -> Circular | None:
    """Ingest one PDF. Returns None when it was already ingested (by checksum)."""
    settings = settings or get_settings()
    circulars = CircularRepository(session)

    checksum = checksum_file(pdf_path)
    if await circulars.get_by_checksum(checksum) is not None:
        log.info("ingest.skip_duplicate", extra={"pdf": str(pdf_path)})
        return None

    page_inputs, vision_used = build_pages(pdf_path, settings, gateway)
    full_text, segmented = segment_pages(page_inputs)
    if not segmented:
        raise ValueError(f"no extractable text in {pdf_path}")

    circular = await circulars.add(
        Circular(
            circular_number=meta.circular_number,
            title=meta.title,
            issue_date=meta.issue_date,
            department=meta.department,
            doc_type=meta.doc_type,
            source_url=meta.source_url,
            pdf_path=str(pdf_path),
            full_text=full_text,
            page_count=len(page_inputs),
            vision_page_count=vision_used,
            checksum=checksum,
        )
    )

    paragraphs = await _save_paragraphs(session, circular.id, segmented)
    await _save_chunks(session, circular.id, segmented, paragraphs)

    log.info(
        "ingest.circular_done",
        extra={
            "circular_number": meta.circular_number,
            "pages": len(page_inputs),
            "vision_pages": vision_used,
            "paragraphs": len(paragraphs),
            "chars": len(full_text),
        },
    )
    return circular


async def _save_paragraphs(
    session: AsyncSession, circular_id: int, segmented: list[SegmentedParagraph]
) -> list[Paragraph]:
    rows = [
        Paragraph(
            circular_id=circular_id,
            order_index=p.order_index,
            para_number=p.para_number,
            heading_path=p.heading_path,
            text=p.text,
            char_start=p.char_start,
            char_end=p.char_end,
            page_number=p.page_number,
            extraction_method=p.extraction_method,
            text_quality_score=p.text_quality_score,
        )
        for p in segmented
    ]
    return await ParagraphRepository(session).add_all(rows)


async def _save_chunks(
    session: AsyncSession,
    circular_id: int,
    segmented: list[SegmentedParagraph],
    paragraphs: list[Paragraph],
) -> list[Chunk]:
    # Map the in-memory order_index onto the database ids just assigned.
    id_by_order = {p.order_index: row.id for p, row in zip(segmented, paragraphs, strict=True)}
    rows = [
        Chunk(
            circular_id=circular_id,
            order_index=c.order_index,
            paragraph_ids=[id_by_order[i] for i in c.paragraph_indices],
            heading_path=c.heading_path,
            text=c.text,
            char_start=c.char_start,
            char_end=c.char_end,
            token_count=c.token_count,
        )
        for c in chunk_paragraphs(segmented)
    ]
    return await ChunkRepository(session).add_all(rows)


async def ingest_batch(
    session: AsyncSession,
    items: list[tuple[Path, CircularMeta]],
    *,
    settings: Settings | None = None,
    gateway: LLMGateway | None = None,
) -> IngestReport:
    """Ingest many PDFs. A failure on one is recorded and the batch continues."""
    settings = settings or get_settings()
    report = IngestReport()

    for pdf_path, meta in items:
        try:
            circular = await ingest_pdf(
                session, pdf_path, meta, settings=settings, gateway=gateway
            )
            if circular is None:
                report.skipped.append(meta.circular_number)
                continue
            await session.commit()
            report.ingested.append(meta.circular_number)
            report.total_pages += circular.page_count
            report.vision_pages += circular.vision_page_count
        except Exception as exc:  # noqa: BLE001 - one bad PDF must not abort the batch
            await session.rollback()
            log.error(
                "ingest.failed",
                extra={"pdf": str(pdf_path), "circular_number": meta.circular_number,
                       "error": str(exc)},
            )
            report.failed.append((meta.circular_number, str(exc)))

    log.info(
        "ingest.batch_done",
        extra={
            "ingested": len(report.ingested),
            "skipped": len(report.skipped),
            "failed": len(report.failed),
            "vision_fraction": round(report.vision_fraction, 3),
        },
    )
    return report
