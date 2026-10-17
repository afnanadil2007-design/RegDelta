"""Citation and supersession graph persistence.

The citation graph is dual-purpose: it drives the amendment chain in the UI and
supplies the retrieval gold set (Stage 5). The supersession edges drive the
``as_of`` temporal filter.
"""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.corpus import Citation, Supersession


class CitationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_all(self, citations: list[Citation]) -> list[Citation]:
        self.session.add_all(citations)
        await self.session.flush()
        return citations

    async def delete_all(self) -> None:
        """Remove every citation edge; the graph builder rebuilds from scratch."""
        await self.session.execute(delete(Citation))

    async def list_resolved(self, limit: int | None = None) -> list[Citation]:
        """Resolved citations only — the gold-set builder's input."""
        stmt = select(Citation).where(Citation.resolved.is_(True)).order_by(Citation.id)
        if limit:
            stmt = stmt.limit(limit)
        return list((await self.session.execute(stmt)).scalars())

    async def list_for_circular(self, circular_id: int) -> list[Citation]:
        """Outbound edges, in the order they appear in the circular."""
        stmt = (
            select(Citation)
            .where(Citation.citing_circular_id == circular_id)
            .order_by(Citation.char_start, Citation.id)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def list_citing(self, cited_circular_id: int) -> list[Citation]:
        """Inbound edges — which other circulars reference this one."""
        stmt = (
            select(Citation)
            .where(Citation.cited_circular_id == cited_circular_id)
            .order_by(Citation.citing_circular_id, Citation.id)
        )
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

    async def delete_all(self) -> None:
        await self.session.execute(delete(Supersession))

    async def list_for_circular(self, circular_id: int) -> list[Supersession]:
        """Both directions, for the amendment chain view."""
        stmt = (
            select(Supersession)
            .where(
                (Supersession.superseding_circular_id == circular_id)
                | (Supersession.superseded_circular_id == circular_id)
            )
            .order_by(Supersession.effective_date.nullslast(), Supersession.id)
        )
        return list((await self.session.execute(stmt)).scalars())
