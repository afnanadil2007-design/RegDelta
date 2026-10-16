"""Search orchestration.

Exists so the router does not call into ``ai/`` directly: routers hold HTTP
concerns only, and retrieval is a model-layer operation. The service runs the
pipeline and hydrates the resulting chunk ids with the circular metadata the
caller needs to render them.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import astuple, dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.retrieval.pipeline import (
    SCORE_KIND,
    RetrievalResult,
    RetrievedChunk,
    ScoreKind,
    retrieve,
)
from app.core.logging import get_logger
from app.db.models.enums import RetrievalMode
from app.db.session import get_sessionmaker
from app.repositories.circulars import ChunkRepository, CircularRepository
from app.repositories.search import SearchFilters

log = get_logger("app.services.search")

# Identical reranked searches share one computation. Reranking takes tens of
# seconds on a CPU and runs in a worker thread that a closed browser request
# cannot stop, and inference is serialised; so a reload, a retry after
# Cancel, or a second tab would otherwise start the same work again and queue
# it behind the first. A search already running is joined; a finished one is
# reused for a few minutes. Other modes take milliseconds and are not shared.
SHARED_TTL_SECONDS = 300.0
SHARED_MAX_ENTRIES = 32
_SharedKey = tuple[object, ...]
_running: dict[_SharedKey, asyncio.Task[RetrievalResult]] = {}
_finished: OrderedDict[_SharedKey, tuple[float, RetrievalResult]] = OrderedDict()


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


async def _retrieve_alone(
    query: str, mode: RetrievalMode, filters: SearchFilters, top_k: int | None
) -> RetrievalResult:
    # Its own session: the requests that wait on it may end before it does.
    async with get_sessionmaker()() as session:
        return await retrieve(session, query, mode=mode, filters=filters, top_k=top_k)


async def shared_rerank(
    query: str, mode: RetrievalMode, filters: SearchFilters, top_k: int | None
) -> tuple[RetrievalResult, str]:
    """The reranked result for this request, and whether it was computed,
    joined (an identical search was running) or reused (one finished recently)."""
    key: _SharedKey = (query, mode, astuple(filters), top_k)
    loop = asyncio.get_running_loop()
    hit = _finished.get(key)
    if hit is not None and loop.time() - hit[0] < SHARED_TTL_SECONDS:
        _finished.move_to_end(key)
        return hit[1], "reused"
    task = _running.get(key)
    how = "joined"
    if task is None:
        how = "computed"
        task = asyncio.create_task(_retrieve_alone(query, mode, filters, top_k))
        _running[key] = task

        def finished(done: asyncio.Task[RetrievalResult]) -> None:
            _running.pop(key, None)
            if not done.cancelled() and done.exception() is None:
                _finished[key] = (loop.time(), done.result())
                while len(_finished) > SHARED_MAX_ENTRIES:
                    _finished.popitem(last=False)

        task.add_done_callback(finished)
    # Shielded: a request that goes away does not cancel the shared work.
    return await asyncio.shield(task), how


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
    if mode is RetrievalMode.HYBRID_RERANK:
        result, how = await shared_rerank(query, mode, filters, top_k)
        log.info("search.rerank", extra={"served": how})
    else:
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
