"""The retrieval pipeline.

Order, fixed by the architecture and not to be varied without stating why:

    dense (pgvector cosine) ─┐
                             ├─ RRF (k=60, ranks only) ─ top 50 ─ cross-encoder
    lexical (tsvector) ──────┘                                   ─ top 8
                                                                 ─ threshold

Both retrievers run over the *same* metadata and ``as_of`` filter, so fusion
compares like with like. Below ``RELEVANCE_THRESHOLD`` the pipeline returns an
explicit no-result signal: callers must treat that as a refusal, not as an
empty list they can quietly ignore.

``mode`` exists so the evaluation harness and the UI traverse identical code —
an ablation that measured a different code path than production would be
measuring the wrong thing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.retrieval.embeddings import embed_query
from app.ai.retrieval.fusion import reciprocal_rank_fusion
from app.ai.retrieval.reranker import rerank
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.models.corpus import Chunk
from app.db.models.enums import RetrievalMode
from app.repositories.circulars import ChunkRepository
from app.repositories.search import SearchFilters, SearchRepository

log = get_logger("app.ai.retrieval.pipeline")


@dataclass
class RetrievedChunk:
    """One result, carrying provenance and every retriever's contribution."""

    chunk_id: int
    circular_id: int
    text: str
    char_start: int
    char_end: int
    heading_path: str | None
    score: float
    dense_rank: int | None = None
    lexical_rank: int | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None


@dataclass
class RetrievalResult:
    """The pipeline's output, including why it may be empty."""

    hits: list[RetrievedChunk] = field(default_factory=list)
    mode: RetrievalMode = RetrievalMode.HYBRID_RERANK
    # True when nothing cleared the relevance threshold. Callers MUST refuse
    # rather than answer from an empty context.
    below_threshold: bool = False
    top_score: float | None = None
    # Chunks that would have ranked but were removed by the as_of filter.
    excluded_by_temporal_filter: list[int] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.hits


async def _load_chunks(session: AsyncSession, chunk_ids: list[int]) -> dict[int, Chunk]:
    chunks = await ChunkRepository(session).get_many(chunk_ids)
    return {c.id: c for c in chunks}


async def retrieve(
    session: AsyncSession,
    query: str,
    *,
    mode: RetrievalMode = RetrievalMode.HYBRID_RERANK,
    filters: SearchFilters | None = None,
    settings: Settings | None = None,
    top_k: int | None = None,
) -> RetrievalResult:
    """Run the pipeline in the requested mode."""
    settings = settings or get_settings()
    filters = filters or SearchFilters()
    top_k = top_k or settings.rerank_top_k
    repo = SearchRepository(session)

    use_dense = mode in (RetrievalMode.DENSE, RetrievalMode.HYBRID, RetrievalMode.HYBRID_RERANK)
    use_lexical = mode in (
        RetrievalMode.LEXICAL,
        RetrievalMode.HYBRID,
        RetrievalMode.HYBRID_RERANK,
    )
    # Embed once; the temporal-exclusion probe below reuses the same vector.
    # Offloaded to a thread: the model runs on CPU synchronously, and doing it
    # inline would block the event loop for the whole call — freezing every
    # other request, including the assessment's live trace stream.
    embedding = await asyncio.to_thread(embed_query, query) if use_dense else None

    dense_hits = (
        await repo.dense(embedding, filters, settings.retrieve_top_n) if embedding else []
    )
    lexical_hits = (
        await repo.lexical(query, filters, settings.retrieve_top_n) if use_lexical else []
    )

    excluded = await _temporal_exclusions(
        repo, query, embedding, use_lexical, filters, settings
    )

    result = await _assemble(
        session, query, mode, dense_hits, lexical_hits, settings, top_k, excluded
    )

    log.info(
        "retrieval.done",
        extra={
            "mode": mode.value,
            "dense": len(dense_hits),
            "lexical": len(lexical_hits),
            "returned": len(result.hits),
            "top_score": result.top_score,
            "below_threshold": result.below_threshold,
        },
    )
    return result


async def _temporal_exclusions(
    repo: SearchRepository,
    query: str,
    embedding: list[float] | None,
    use_lexical: bool,
    filters: SearchFilters,
    settings: Settings,
) -> list[int]:
    """Chunks that would have ranked, but were removed by the ``as_of`` filter.

    This must re-run retrieval *without* the temporal predicate. The main
    retrievers already exclude superseded circulars in SQL, so asking which of
    their results were excluded would always answer "none" — the UI banner
    would silently never appear.

    The probe keeps every other filter and skips reranking: the banner needs to
    say "results were hidden", not to rank them.
    """
    if not filters.as_of:
        return []

    unfiltered = SearchFilters(
        as_of=None,
        department=filters.department,
        date_from=filters.date_from,
        # Still bound by the as-of date itself: a circular issued *after* the
        # date was never in force, so it is not "excluded", it is irrelevant.
        date_to=filters.as_of,
        doc_type=filters.doc_type,
    )

    ranked: dict[str, list[int]] = {}
    if embedding is not None:
        hits = await repo.dense(embedding, unfiltered, settings.retrieve_top_n)
        ranked["dense"] = [cid for cid, _ in hits]
    if use_lexical:
        hits = await repo.lexical(query, unfiltered, settings.retrieve_top_n)
        ranked["lexical"] = [cid for cid, _ in hits]
    if not ranked:
        return []

    fused = reciprocal_rank_fusion(ranked, k=settings.rrf_k)
    candidates = [hit.chunk_id for hit in fused[: settings.rerank_top_k]]
    return await repo.excluded_by_temporal_filter(candidates, filters.as_of)


# (chunk_id, score, dense_rank, lexical_rank) as it stands before reranking.
_Candidate = tuple[int, float, int | None, int | None]


def _order_candidates(
    mode: RetrievalMode,
    dense_hits: list[tuple[int, float]],
    lexical_hits: list[tuple[int, float]],
    settings: Settings,
) -> list[_Candidate]:
    """Single-retriever modes keep their own scores; no fusion is meaningful."""
    if mode is RetrievalMode.DENSE:
        return [(cid, score, i + 1, None) for i, (cid, score) in enumerate(dense_hits)]
    if mode is RetrievalMode.LEXICAL:
        return [(cid, score, None, i + 1) for i, (cid, score) in enumerate(lexical_hits)]

    fused = reciprocal_rank_fusion(
        {
            "dense": [cid for cid, _ in dense_hits],
            "lexical": [cid for cid, _ in lexical_hits],
        },
        k=settings.rrf_k,
    )
    return [(h.chunk_id, h.rrf_score, h.dense_rank, h.lexical_rank) for h in fused]


def _hydrate(
    candidates: list[_Candidate],
    chunk_map: dict[int, Chunk],
    mode: RetrievalMode,
    rerank_scores: dict[int, float],
) -> list[RetrievedChunk]:
    """Join ranked ids back onto their chunk rows, dropping any that vanished."""
    hits: list[RetrievedChunk] = []
    keeps_rrf = mode in (RetrievalMode.HYBRID, RetrievalMode.HYBRID_RERANK)
    for chunk_id, base_score, dense_rank, lexical_rank in candidates:
        chunk = chunk_map.get(chunk_id)
        if chunk is None:
            continue
        hits.append(
            RetrievedChunk(
                chunk_id=chunk_id,
                circular_id=chunk.circular_id,
                text=chunk.text,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                heading_path=chunk.heading_path,
                score=rerank_scores.get(chunk_id, base_score),
                dense_rank=dense_rank,
                lexical_rank=lexical_rank,
                rrf_score=base_score if keeps_rrf else None,
                rerank_score=rerank_scores.get(chunk_id),
            )
        )
    return hits


async def _assemble(
    session: AsyncSession,
    query: str,
    mode: RetrievalMode,
    dense_hits: list[tuple[int, float]],
    lexical_hits: list[tuple[int, float]],
    settings: Settings,
    top_k: int,
    excluded: list[int],
) -> RetrievalResult:
    """Fuse, optionally rerank, threshold, and hydrate into RetrievedChunks."""
    ordered = _order_candidates(mode, dense_hits, lexical_hits, settings)
    if not ordered:
        return RetrievalResult(
            mode=mode,
            below_threshold=False,
            top_score=None,
            excluded_by_temporal_filter=excluded,
        )

    candidates = ordered[: settings.retrieve_top_n]
    chunk_map = await _load_chunks(session, [cid for cid, _, _, _ in candidates])

    rerank_scores: dict[int, float] = {}
    if mode is RetrievalMode.HYBRID_RERANK:
        passages = [
            (cid, chunk_map[cid].text) for cid, _, _, _ in candidates if cid in chunk_map
        ]
        # Offloaded: the cross-encoder scores every passage on CPU (tens of
        # seconds here), which must not run inline on the event loop.
        reranked = await asyncio.to_thread(rerank, query, passages)
        rerank_scores = dict(reranked)
        rank_index = {cid: i for i, (cid, _) in enumerate(reranked)}
        candidates.sort(key=lambda row: rank_index.get(row[0], len(reranked)))

    hits = _hydrate(candidates[:top_k], chunk_map, mode, rerank_scores)

    top_score = hits[0].score if hits else None
    # Only the reranked mode has a calibrated score to threshold on; the raw
    # cosine / ts_rank / RRF scales are not comparable to the setting.
    below = (
        mode is RetrievalMode.HYBRID_RERANK
        and top_score is not None
        and top_score < settings.relevance_threshold
    )

    return RetrievalResult(
        hits=[] if below else hits,
        mode=mode,
        below_threshold=below,
        top_score=top_score,
        excluded_by_temporal_filter=excluded,
    )
