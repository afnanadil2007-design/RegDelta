"""Circular, paragraph, and chunk persistence.

All SQL touching the corpus lives here. Callers pass plain values; repositories
own statement construction and are the only place raw SQL may appear.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.corpus import Chunk, Circular, Paragraph
from app.db.models.enums import ExtractionMethod


class CircularRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, circular: Circular) -> Circular:
        self.session.add(circular)
        await self.session.flush()
        return circular

    async def get(self, circular_id: int) -> Circular | None:
        return await self.session.get(Circular, circular_id)

    async def get_by_number(self, circular_number: str) -> Circular | None:
        stmt = select(Circular).where(Circular.circular_number == circular_number)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_checksum(self, checksum: str) -> Circular | None:
        """Used to make re-ingestion idempotent."""
        stmt = select(Circular).where(Circular.checksum == checksum)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    # Named `list_circulars`, not `list`: a method named `list` shadows the
    # builtin inside the class body and breaks later `list[...]` annotations.
    async def list_circulars(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        department: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[Circular]:
        stmt = select(Circular).order_by(Circular.issue_date.desc().nullslast(), Circular.id.desc())
        if department:
            stmt = stmt.where(Circular.department == department)
        if date_from:
            stmt = stmt.where(Circular.issue_date >= date_from)
        if date_to:
            stmt = stmt.where(Circular.issue_date <= date_to)
        stmt = stmt.limit(limit).offset(offset)
        return list((await self.session.execute(stmt)).scalars())

    async def count(self) -> int:
        return int((await self.session.execute(select(func.count(Circular.id)))).scalar_one())

    async def departments(self) -> list[str]:
        """Distinct departments, for the metadata filter dropdown."""
        stmt = (
            select(Circular.department)
            .where(Circular.department.is_not(None))
            .distinct()
            .order_by(Circular.department)
        )
        return [d for d in (await self.session.execute(stmt)).scalars() if d]

    async def summaries(self, ids: list[int]) -> dict[int, tuple[str, str, date | None]]:
        """Number, title, and issue date per id — one query, for hydrating hits."""
        if not ids:
            return {}
        stmt = select(
            Circular.id, Circular.circular_number, Circular.title, Circular.issue_date
        ).where(Circular.id.in_(ids))
        rows = (await self.session.execute(stmt)).all()
        return {int(r[0]): (r[1], r[2], r[3]) for r in rows}

    async def ping(self) -> bool:
        """Cheapest possible round-trip, for the health endpoint."""
        try:
            await self.session.execute(select(1))
        except SQLAlchemyError:
            return False
        return True


class ParagraphRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_all(self, paragraphs: list[Paragraph]) -> list[Paragraph]:
        self.session.add_all(paragraphs)
        await self.session.flush()
        return paragraphs

    async def get(self, paragraph_id: int) -> Paragraph | None:
        return await self.session.get(Paragraph, paragraph_id)

    async def list_for_circular(self, circular_id: int) -> list[Paragraph]:
        stmt = (
            select(Paragraph)
            .where(Paragraph.circular_id == circular_id)
            .order_by(Paragraph.order_index)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def vision_page_fraction(self) -> float:
        """Fraction of paragraphs that took the vision path — an ingestion KPI."""
        total = (await self.session.execute(select(func.count(Paragraph.id)))).scalar_one()
        if not total:
            return 0.0
        vision = (
            await self.session.execute(
                select(func.count(Paragraph.id)).where(
                    Paragraph.extraction_method == ExtractionMethod.VISION
                )
            )
        ).scalar_one()
        return float(vision) / float(total)


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_all(self, chunks: list[Chunk]) -> list[Chunk]:
        self.session.add_all(chunks)
        await self.session.flush()
        return chunks

    async def get(self, chunk_id: int) -> Chunk | None:
        return await self.session.get(Chunk, chunk_id)

    async def get_many(self, chunk_ids: list[int]) -> list[Chunk]:
        if not chunk_ids:
            return []
        stmt = select(Chunk).where(Chunk.id.in_(chunk_ids))
        return list((await self.session.execute(stmt)).scalars())

    async def list_for_circular(self, circular_id: int) -> list[Chunk]:
        stmt = select(Chunk).where(Chunk.circular_id == circular_id).order_by(Chunk.order_index)
        return list((await self.session.execute(stmt)).scalars())

    async def count(self) -> int:
        return int((await self.session.execute(select(func.count(Chunk.id)))).scalar_one())
