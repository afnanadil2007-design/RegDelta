"""Search SQL: dense (pgvector cosine) and lexical (tsvector) over chunks.

All retrieval SQL lives here — the ai/ layer composes and ranks, but never
writes SQL. Both retrievers apply the *same* metadata and temporal filters, so
fusion compares like with like.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import ScalarSelect, Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.corpus import Chunk, Circular, Supersession


@dataclass
class SearchFilters:
    """Metadata and point-in-time filters shared by both retrievers."""

    as_of: date | None = None
    department: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    doc_type: str | None = None


def _superseded_subquery(as_of: date) -> ScalarSelect[int]:
    """Circular ids not in force on ``as_of``.

    A circular is out of force when a *resolved* supersession edge names it and
    that edge took effect on or before the given date.
    """
    return (
        select(Supersession.superseded_circular_id)
        .where(
            Supersession.superseded_circular_id.is_not(None),
            Supersession.resolved.is_(True),
            Supersession.effective_date.is_not(None),
            Supersession.effective_date <= as_of,
        )
        .scalar_subquery()
    )


def apply_filters(stmt: Select, filters: SearchFilters) -> Select:
    """Attach metadata + temporal predicates to a chunk query."""
    conditions = []
    if filters.department:
        conditions.append(Circular.department == filters.department)
    if filters.doc_type:
        conditions.append(Circular.doc_type == filters.doc_type)
    if filters.date_from:
        conditions.append(Circular.issue_date >= filters.date_from)
    if filters.date_to:
        conditions.append(Circular.issue_date <= filters.date_to)
    if filters.as_of:
        # Only documents that existed by as_of, and were not yet superseded.
        conditions.append(Circular.issue_date <= filters.as_of)
        conditions.append(Chunk.circular_id.notin_(_superseded_subquery(filters.as_of)))

    if conditions:
        stmt = stmt.where(and_(*conditions))
    return stmt


class SearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def dense(
        self, embedding: list[float], filters: SearchFilters, limit: int
    ) -> list[tuple[int, float]]:
        """Cosine nearest neighbours. Returns (chunk_id, similarity) best first."""
        distance = Chunk.embedding.cosine_distance(embedding)
        stmt = (
            select(Chunk.id, distance.label("distance"))
            .join(Circular, Circular.id == Chunk.circular_id)
            .where(Chunk.embedding.is_not(None))
        )
        stmt = apply_filters(stmt, filters).order_by(distance).limit(limit)
        rows = (await self.session.execute(stmt)).all()
        # pgvector returns cosine *distance*; similarity is 1 - distance.
        return [(int(r[0]), 1.0 - float(r[1])) for r in rows]

    async def lexical(
        self, query: str, filters: SearchFilters, limit: int
    ) -> list[tuple[int, float]]:
        """Postgres full-text ranking with ts_rank_cd."""
        tsquery = func.websearch_to_tsquery("english", query)
        rank = func.ts_rank_cd(Chunk.tsv, tsquery)
        stmt = (
            select(Chunk.id, rank.label("rank"))
            .join(Circular, Circular.id == Chunk.circular_id)
            .where(Chunk.tsv.op("@@")(tsquery))
        )
        stmt = apply_filters(stmt, filters).order_by(rank.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).all()
        return [(int(r[0]), float(r[1])) for r in rows]

    async def excluded_by_temporal_filter(
        self, chunk_ids: list[int], as_of: date
    ) -> list[int]:
        """Which of these chunks the as_of filter would remove.

        Used to populate the UI banner: results that *would* have ranked but
        were dropped because their circular was superseded by that date.
        """
        if not chunk_ids or as_of is None:
            return []
        stmt = (
            select(Chunk.id)
            .join(Circular, Circular.id == Chunk.circular_id)
            .where(
                Chunk.id.in_(chunk_ids),
                Chunk.circular_id.in_(_superseded_subquery(as_of)),
            )
        )
        return [int(r[0]) for r in (await self.session.execute(stmt)).all()]
