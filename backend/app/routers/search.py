"""Search endpoint.

``mode`` is part of the request so the evaluation harness and the UI traverse
the identical code path — an ablation that measured a parallel implementation
would be measuring the wrong thing.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.repositories.search import SearchFilters
from app.routers.schemas import SearchHit, SearchRequest, SearchResponse
from app.services.search import SearchHitData
from app.services.search import search as search_service

router = APIRouter(tags=["search"])


def _to_hit(row: SearchHitData) -> SearchHit:
    return SearchHit(
        chunk_id=row.hit.chunk_id,
        circular_id=row.hit.circular_id,
        circular_number=row.circular_number,
        circular_title=row.circular_title,
        issue_date=row.issue_date,
        text=row.hit.text,
        char_start=row.hit.char_start,
        char_end=row.hit.char_end,
        heading_path=row.hit.heading_path,
        score=row.hit.score,
        dense_rank=row.hit.dense_rank,
        lexical_rank=row.hit.lexical_rank,
        rrf_score=row.hit.rrf_score,
        rerank_score=row.hit.rerank_score,
    )


@router.post("/search", response_model=SearchResponse)
async def search(
    payload: SearchRequest, session: AsyncSession = Depends(get_session)
) -> SearchResponse:
    outcome = await search_service(
        session,
        payload.query,
        mode=payload.mode,
        filters=SearchFilters(
            as_of=payload.as_of,
            department=payload.department,
            date_from=payload.date_from,
            date_to=payload.date_to,
            doc_type=payload.doc_type,
        ),
        top_k=payload.top_k,
    )

    return SearchResponse(
        mode=outcome.mode,
        hits=[_to_hit(row) for row in outcome.hits],
        below_threshold=outcome.below_threshold,
        top_score=outcome.top_score,
        excluded_by_temporal_filter=outcome.excluded_by_temporal_filter,
    )
