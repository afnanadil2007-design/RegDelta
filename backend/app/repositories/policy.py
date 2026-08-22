"""Policy pack and clause persistence."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.policy import PolicyClause, PolicyPack


class PolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_pack(self, pack: PolicyPack) -> PolicyPack:
        self.session.add(pack)
        await self.session.flush()
        return pack

    async def get_pack(self, pack_id: int) -> PolicyPack | None:
        return await self.session.get(PolicyPack, pack_id)

    async def get_pack_by_name(self, name: str, version: str) -> PolicyPack | None:
        stmt = select(PolicyPack).where(PolicyPack.name == name, PolicyPack.version == version)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_packs(self) -> list[PolicyPack]:
        stmt = select(PolicyPack).order_by(PolicyPack.name, PolicyPack.version)
        return list((await self.session.execute(stmt)).scalars())

    async def add_clauses(self, clauses: list[PolicyClause]) -> list[PolicyClause]:
        self.session.add_all(clauses)
        await self.session.flush()
        return clauses

    async def get_clause(self, clause_id: int) -> PolicyClause | None:
        return await self.session.get(PolicyClause, clause_id)

    async def get_many_clauses(self, clause_ids: list[int]) -> list[PolicyClause]:
        if not clause_ids:
            return []
        stmt = select(PolicyClause).where(PolicyClause.id.in_(clause_ids))
        return list((await self.session.execute(stmt)).scalars())

    async def list_clauses(self, pack_id: int) -> list[PolicyClause]:
        stmt = (
            select(PolicyClause)
            .where(PolicyClause.policy_pack_id == pack_id)
            .order_by(PolicyClause.order_index)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def count_clauses(self, pack_id: int) -> int:
        stmt = select(func.count(PolicyClause.id)).where(PolicyClause.policy_pack_id == pack_id)
        return int((await self.session.execute(stmt)).scalar_one())
