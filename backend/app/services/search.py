"""Search orchestration.

Exists so the router does not call into ``ai/`` directly: routers hold HTTP
concerns only, and retrieval is a model-layer operation. The service runs the
pipeline and hydrates the resulting chunk ids with the circular metadata the
caller needs to render them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.retrieval.pipeline import RetrievedChunk, retrieve
from app.db.models.enums import RetrievalMode
from app.repositories.circulars import CircularRepository
from app.repositories.search import SearchFilters


@dataclass
class SearchHitData:
    """A retrieved chunk plus the circular metadata needed to display it."""

    hit: RetrievedChunk
    circular_number: str
    circular_title: str
    issue_date: date | None


@dataclass
class SearchOutcome:
    mode: RetrievalMode
    hits: list[SearchHitData]
    below_threshold: bool
    top_score: float | None
    excluded_by_temporal_filter: list[int]


async def search(
    session: AsyncSession,
    query: str,
    *,
    mode: RetrievalMode,
    filters: SearchFilters,
    top_k: int | None = None,
) -> SearchOutcome:
    """Retrieve, then attach circular metadata in a single follow-up query."""
    result = await retrieve(session, query, mode=mode, filters=filters, top_k=top_k)

    summaries = await CircularRepository(session).summaries(
        [hit.circular_id for hit in result.hits]
    )
    hits = [
        SearchHitData(
            hit=hit,
            circular_number=summaries.get(hit.circular_id, ("", "", None))[0],
            circular_title=summaries.get(hit.circular_id, ("", "", None))[1],
            issue_date=summaries.get(hit.circular_id, ("", "", None))[2],
        )
        for hit in result.hits
    ]

    return SearchOutcome(
        mode=result.mode,
        hits=hits,
        below_threshold=result.below_threshold,
        top_score=result.top_score,
        excluded_by_temporal_filter=result.excluded_by_temporal_filter,
    )
