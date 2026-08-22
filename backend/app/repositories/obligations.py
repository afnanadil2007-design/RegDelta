"""Obligation persistence and the span-provenance query.

``list_with_source_text`` returns each obligation alongside the exact substring
its offsets resolve to in the circular's full text. This is what the span
integrity test and the groundedness layer-1 check consume.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.corpus import Circular, Obligation, Paragraph


class ObligationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_all(self, obligations: list[Obligation]) -> list[Obligation]:
        self.session.add_all(obligations)
        await self.session.flush()
        return obligations

    async def get(self, obligation_id: int) -> Obligation | None:
        return await self.session.get(Obligation, obligation_id)

    async def get_many(self, obligation_ids: list[int]) -> list[Obligation]:
        if not obligation_ids:
            return []
        stmt = select(Obligation).where(Obligation.id.in_(obligation_ids))
        return list((await self.session.execute(stmt)).scalars())

    async def list_for_circular(self, circular_id: int) -> list[Obligation]:
        stmt = (
            select(Obligation)
            .where(Obligation.circular_id == circular_id)
            .order_by(Obligation.char_start)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def count(self) -> int:
        return int((await self.session.execute(select(func.count(Obligation.id)))).scalar_one())

    async def list_with_source_text(
        self, circular_id: int | None = None
    ) -> list[tuple[Obligation, str, int, int]]:
        """Every obligation with the text its span resolves to, plus the source
        paragraph's bounds.

        Returns ``(obligation, resolved_span_text, para_start, para_end)``.
        The slice is computed in Postgres so the assertion tests exactly what
        is stored, not a Python-side reconstruction.
        """
        # substr() is 1-indexed and length-based; char_start is a 0-indexed
        # half-open offset, hence the +1 and the (end - start) length.
        span_text = func.substr(
            Circular.full_text,
            Obligation.char_start + 1,
            Obligation.char_end - Obligation.char_start,
        )
        stmt = (
            select(Obligation, span_text, Paragraph.char_start, Paragraph.char_end)
            .join(Circular, Circular.id == Obligation.circular_id)
            .join(Paragraph, Paragraph.id == Obligation.paragraph_id)
            .order_by(Obligation.id)
        )
        if circular_id is not None:
            stmt = stmt.where(Obligation.circular_id == circular_id)
        rows = (await self.session.execute(stmt)).all()
        return [(r[0], r[1], r[2], r[3]) for r in rows]
