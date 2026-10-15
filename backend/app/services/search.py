"""Search orchestration.

Exists so the router does not call into ``ai/`` directly: routers hold HTTP
concerns only, and retrieval is a model-layer operation. The service runs the
pipeline and hydrates the resulting chunk ids with the circular metadata the
caller needs to render them.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.retrieval.pipeline import SCORE_KIND, RetrievedChunk, ScoreKind, retrieve
from app.db.models.enums import RetrievalMode
from app.repositories.circulars import ChunkRepository, CircularRepository
from app.repositories.search import SearchFilters


@dataclass
class SearchHitData:
    """A retrieved chunk plus the circular metadata needed to display it."""

    hit: RetrievedChunk
    circular_number: str
    circular_title: str
    issue_date: date | None


@dataclass
class ExcludedCircularData:
    circular_id: int
    circular_number: str
    title: str


@dataclass
class SearchOutcome:
    mode: RetrievalMode
    hits: list[SearchHitData]
    refused: bool
    top_score: float | None
    threshold: float | None
    score_kind: ScoreKind
    excluded: list[ExcludedCircularData]
    elapsed_ms: int


async def search(
    session: AsyncSession,
    query: str,
    *,
    mode: RetrievalMode,
    filters: SearchFilters,
    top_k: int | None = None,
) -> SearchOutcome:
    """Retrieve, then attach circular metadata in a single follow-up query."""
    started = time.perf_counter()
    result = await retrieve(session, query, mode=mode, filters=filters, top_k=top_k)

    # The temporal banner names circulars, not chunks.
    excluded_chunks = await ChunkRepository(session).get_many(result.excluded_by_temporal_filter)
    excluded_ids = sorted({chunk.circular_id for chunk in excluded_chunks})

    names = await CircularRepository(session).summaries(
        [hit.circular_id for hit in result.hits] + excluded_ids
    )
    hits = [
        SearchHitData(
            hit=hit,
            circular_number=names[hit.circular_id][0] if hit.circular_id in names else "",
            circular_title=names[hit.circular_id][1] if hit.circular_id in names else "",
            issue_date=names[hit.circular_id][2] if hit.circular_id in names else None,
        )
        for hit in result.hits
    ]
    excluded = [
        ExcludedCircularData(cid, names[cid][0], names[cid][1])
        for cid in excluded_ids
        if cid in names
    ]
    return SearchOutcome(
        mode=result.mode,
        hits=hits,
        refused=result.below_threshold,
        top_score=result.top_score,
        threshold=result.threshold,
        score_kind=SCORE_KIND[result.mode],
        excluded=excluded,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )
