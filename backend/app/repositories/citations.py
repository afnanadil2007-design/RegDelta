"""Citation and supersession graph persistence.

The citation graph is dual-purpose: it drives the amendment chain in the UI and
supplies the retrieval gold set (Stage 5). The supersession edges drive the
``as_of`` temporal filter.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.corpus import Citation, Supersession


class CitationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_all(self, citations: list[Citation]) -> list[Citation]:
        self.session.add_all(citations)
        await self.session.flush()
        return citations

    async def list_resolved(self, limit: int | None = None) -> list[Citation]:
        """Resolved citations only — the gold-set builder's input."""
        stmt = select(Citation).where(Citation.resolved.is_(True)).order_by(Citation.id)
        if limit:
            stmt = stmt.limit(limit)
        return list((await self.session.execute(stmt)).scalars())

    async def list_for_circular(self, circular_id: int) -> list[Citation]:
        stmt = select(Citation).where(Citation.citing_circular_id == circular_id)
        return list((await self.session.execute(stmt)).scalars())

    async def list_citing(self, cited_circular_id: int) -> list[Citation]:
        """Inbound edges — which later circulars reference this one."""
        stmt = select(Citation).where(Citation.cited_circular_id == cited_circular_id)
        return list((await self.session.execute(stmt)).scalars())

    async def resolution_stats(self) -> tuple[int, int]:
        """(resolved, total) — reported by the gold-set builder as coverage."""
        total = (await self.session.execute(select(func.count(Citation.id)))).scalar_one()
        resolved = (
            await self.session.execute(
                select(func.count(Citation.id)).where(Citation.resolved.is_(True))
            )
        ).scalar_one()
        return int(resolved), int(total)


class SupersessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_all(self, edges: list[Supersession]) -> list[Supersession]:
        self.session.add_all(edges)
        await self.session.flush()
        return edges

    async def list_for_circular(self, circular_id: int) -> list[Supersession]:
        """Both directions, for the amendment chain view."""
        stmt = select(Supersession).where(
            (Supersession.superseding_circular_id == circular_id)
            | (Supersession.superseded_circular_id == circular_id)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def superseded_circular_ids(self, as_of: date) -> list[int]:
        """Circulars no longer in force on ``as_of``.

        A circular is excluded when a resolved supersession edge names it and
        that edge took effect on or before the given date. Edges with no
        effective date fall back to the superseding circular's issue date,
        which is set by the caller at extraction time.
        """
        stmt = (
            select(Supersession.superseded_circular_id)
            .where(
                Supersession.superseded_circular_id.is_not(None),
                Supersession.resolved.is_(True),
                Supersession.effective_date.is_not(None),
                Supersession.effective_date <= as_of,
            )
            .distinct()
        )
        return [cid for cid in (await self.session.execute(stmt)).scalars() if cid is not None]
