"""Circular listing and detail."""

from __future__ import annotations

from datetime import date
from pathlib import PurePath

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.db.models.corpus import Circular, Citation, Obligation, Paragraph, Supersession
from app.db.models.enums import REMOVES_FROM_FORCE
from app.db.session import get_session
from app.repositories.circulars import CircularRepository, ParagraphRepository
from app.repositories.citations import CitationRepository, SupersessionRepository
from app.repositories.obligations import ObligationRepository
from app.routers.schemas import (
    CircularDetail,
    CircularPage,
    CircularProvenance,
    CircularSummary,
    CitationOut,
    ObligationOut,
    ParagraphOut,
    SupersessionOut,
)

router = APIRouter(tags=["circulars"])

_SYNTHETIC_SCHEME = "synthetic://"

# (number, title, issue_date) per circular id, from CircularRepository.summaries.
_Names = dict[int, tuple[str, str, date | None]]


def _summary(circular: Circular, obligation_count: int) -> CircularSummary:
    return CircularSummary(
        id=circular.id,
        circular_number=circular.circular_number,
        title=circular.title,
        issue_date=circular.issue_date,
        department=circular.department,
        doc_type=circular.doc_type,
        page_count=circular.page_count,
        vision_page_count=circular.vision_page_count,
        source_url=circular.source_url,
        is_synthetic=(circular.source_url or "").startswith(_SYNTHETIC_SCHEME),
        obligation_count=obligation_count,
        ingested_at=circular.ingested_at,
    )


@router.get("/circulars", response_model=CircularPage)
async def list_circulars(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, max_length=200, description="matches number or title"),
    department: str | None = Query(None, max_length=64),
    date_from: date | None = None,
    date_to: date | None = None,
    session: AsyncSession = Depends(get_session),
) -> CircularPage:
    if date_from and date_to and date_from > date_to:
        raise ApiError(422, "invalid_date_range", "date_from must be on or before date_to.")
    repo = CircularRepository(session)
    circulars = await repo.list_circulars(
        limit=limit,
        offset=offset,
        query=q,
        department=department,
        date_from=date_from,
        date_to=date_to,
    )
    total = await repo.count_matching(
        query=q, department=department, date_from=date_from, date_to=date_to
    )
    counts = await ObligationRepository(session).counts_by_circular([c.id for c in circulars])
    return CircularPage(
        items=[_summary(c, counts.get(c.id, 0)) for c in circulars],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/circulars/departments", response_model=list[str])
async def list_departments(session: AsyncSession = Depends(get_session)) -> list[str]:
    return await CircularRepository(session).departments()


@router.get("/circulars/{circular_id}", response_model=CircularDetail)
async def get_circular(
    circular_id: int, session: AsyncSession = Depends(get_session)
) -> CircularDetail:
    circular = await CircularRepository(session).get(circular_id)
    if circular is None:
        raise ApiError(404, "circular_not_found", f"No circular with id {circular_id}.")

    paragraphs = await ParagraphRepository(session).list_for_circular(circular_id)
    obligations = await ObligationRepository(session).list_for_circular(circular_id)
    citations = await CitationRepository(session).list_for_circular(circular_id)
    cited_by = await CitationRepository(session).list_citing(circular_id)
    supersessions = await SupersessionRepository(session).list_for_circular(circular_id)

    referenced = {c.cited_circular_id for c in citations if c.cited_circular_id}
    referenced |= {c.citing_circular_id for c in cited_by}
    referenced |= {s.superseded_circular_id for s in supersessions if s.superseded_circular_id}
    referenced |= {s.superseding_circular_id for s in supersessions}
    names = await CircularRepository(session).summaries(sorted(referenced))

    return CircularDetail(
        circular=_summary(circular, len(obligations)),
        provenance=CircularProvenance(
            checksum=circular.checksum,
            # The file name only: the absolute path is a detail of one machine.
            pdf_filename=PurePath(circular.pdf_path).name if circular.pdf_path else None,
            ingested_at=circular.ingested_at,
        ),
        full_text=circular.full_text,
        paragraphs=[_paragraph_out(p) for p in paragraphs],
        obligations=[_obligation_out(o) for o in obligations],
        citations=[_citation_out(c, names) for c in citations],
        cited_by=[_citation_out(c, names) for c in cited_by],
        supersessions=[_supersession_out(s, circular_id, names) for s in supersessions],
    )


def _paragraph_out(p: Paragraph) -> ParagraphOut:
    return ParagraphOut(
        id=p.id,
        order_index=p.order_index,
        para_number=p.para_number,
        heading_path=p.heading_path,
        text=p.text,
        char_start=p.char_start,
        char_end=p.char_end,
        page_number=p.page_number,
        extraction_method=p.extraction_method.value,
        text_quality_score=p.text_quality_score,
    )


def _obligation_out(o: Obligation) -> ObligationOut:
    return ObligationOut(
        id=o.id,
        paragraph_id=o.paragraph_id,
        text=o.text,
        actor=o.actor,
        action=o.action,
        deadline=o.deadline,
        condition=o.condition,
        modality=o.modality,
        char_start=o.char_start,
        char_end=o.char_end,
        model_confidence=o.confidence,
        extractor=o.extractor,
    )


def _citation_out(c: Citation, names: _Names) -> CitationOut:
    cited = names.get(c.cited_circular_id) if c.cited_circular_id else None
    citing = names.get(c.citing_circular_id)
    return CitationOut(
        id=c.id,
        citing_circular_id=c.citing_circular_id,
        citing_circular_number=citing[0] if citing else None,
        citing_paragraph_id=c.citing_paragraph_id,
        raw_reference=c.raw_reference,
        cited_circular_id=c.cited_circular_id,
        cited_circular_number=cited[0] if cited else None,
        cited_circular_title=cited[1] if cited else None,
        resolved=c.resolved,
        resolution_method=c.resolution_method.value,
        char_start=c.char_start,
        char_end=c.char_end,
    )


def _supersession_out(s: Supersession, viewing_id: int, names: _Names) -> SupersessionOut:
    superseding = names.get(s.superseding_circular_id)
    superseded = names.get(s.superseded_circular_id) if s.superseded_circular_id else None
    return SupersessionOut(
        id=s.id,
        direction="outgoing" if s.superseding_circular_id == viewing_id else "incoming",
        superseding_circular_id=s.superseding_circular_id,
        superseding_number=superseding[0] if superseding else None,
        superseding_title=superseding[1] if superseding else None,
        superseded_circular_id=s.superseded_circular_id,
        superseded_number=superseded[0] if superseded else None,
        superseded_title=superseded[1] if superseded else None,
        supersession_type=s.supersession_type.value,
        removes_from_force=s.supersession_type in REMOVES_FROM_FORCE,
        effective_date=s.effective_date,
        resolved=s.resolved,
        raw_reference=s.raw_reference,
        evidence_paragraph_id=s.evidence_paragraph_id,
    )
