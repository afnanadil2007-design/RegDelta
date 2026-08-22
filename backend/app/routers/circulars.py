"""Circular listing and detail."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.db.models.corpus import (
    Circular,
    Citation,
    Obligation,
    Paragraph,
    Supersession,
)
from app.db.session import get_session
from app.repositories.circulars import CircularRepository, ParagraphRepository
from app.repositories.citations import CitationRepository, SupersessionRepository
from app.repositories.obligations import ObligationRepository
from app.routers.schemas import (
    CircularDetail,
    CircularSummary,
    CitationOut,
    ObligationOut,
    ParagraphOut,
    SupersessionOut,
)

router = APIRouter(tags=["circulars"])


def _summary(circular: Circular) -> CircularSummary:
    return CircularSummary(
        id=circular.id,
        circular_number=circular.circular_number,
        title=circular.title,
        issue_date=circular.issue_date,
        department=circular.department,
        doc_type=circular.doc_type,
        page_count=circular.page_count,
        vision_page_count=circular.vision_page_count,
    )


@router.get("/circulars", response_model=list[CircularSummary])
async def list_circulars(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    department: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[CircularSummary]:
    circulars = await CircularRepository(session).list_circulars(
        limit=limit, offset=offset, department=department, date_from=date_from, date_to=date_to
    )
    return [_summary(c) for c in circulars]


@router.get("/circulars/departments", response_model=list[str])
async def list_departments(session: AsyncSession = Depends(get_session)) -> list[str]:
    return await CircularRepository(session).departments()


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
    )


def _obligation_out(o: Obligation) -> ObligationOut:
    return ObligationOut(
        id=o.id,
        text=o.text,
        actor=o.actor,
        action=o.action,
        deadline=o.deadline,
        modality=o.modality,
        char_start=o.char_start,
        char_end=o.char_end,
        confidence=o.confidence,
    )


def _citation_out(c: Citation, numbers: dict[int, str]) -> CitationOut:
    return CitationOut(
        id=c.id,
        raw_reference=c.raw_reference,
        cited_circular_id=c.cited_circular_id,
        cited_circular_number=numbers.get(c.cited_circular_id or -1),
        resolved=c.resolved,
        resolution_method=c.resolution_method.value,
    )


def _supersession_out(s: Supersession, numbers: dict[int, str]) -> SupersessionOut:
    return SupersessionOut(
        id=s.id,
        superseding_circular_id=s.superseding_circular_id,
        superseding_number=numbers.get(s.superseding_circular_id),
        superseded_circular_id=s.superseded_circular_id,
        superseded_number=numbers.get(s.superseded_circular_id or -1),
        supersession_type=s.supersession_type.value,
        effective_date=s.effective_date,
        evidence_paragraph_id=s.evidence_paragraph_id,
    )


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
    supersessions = await SupersessionRepository(session).list_for_circular(circular_id)

    # Resolve referenced circular numbers in one query for the amendment chain.
    referenced = {c.cited_circular_id for c in citations if c.cited_circular_id}
    referenced |= {s.superseded_circular_id for s in supersessions if s.superseded_circular_id}
    referenced |= {s.superseding_circular_id for s in supersessions}
    numbers = await _numbers(session, [i for i in referenced if i])

    return CircularDetail(
        circular=_summary(circular),
        full_text=circular.full_text,
        paragraphs=[_paragraph_out(p) for p in paragraphs],
        obligations=[_obligation_out(o) for o in obligations],
        citations=[_citation_out(c, numbers) for c in citations],
        supersessions=[_supersession_out(s, numbers) for s in supersessions],
    )


async def _numbers(session: AsyncSession, ids: list[int]) -> dict[int, str]:
    """Circular numbers by id, for rendering the amendment chain."""
    summaries = await CircularRepository(session).summaries(ids)
    return {cid: number for cid, (number, _, _) in summaries.items()}
