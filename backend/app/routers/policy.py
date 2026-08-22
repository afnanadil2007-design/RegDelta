"""Policy pack routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.db.session import get_session
from app.repositories.policy import PolicyRepository
from app.routers.schemas import PolicyClauseOut, PolicyPackOut

router = APIRouter(tags=["policy"])


@router.get("/policy-packs", response_model=list[PolicyPackOut])
async def list_packs(session: AsyncSession = Depends(get_session)) -> list[PolicyPackOut]:
    repo = PolicyRepository(session)
    packs = await repo.list_packs()
    return [
        PolicyPackOut(
            id=p.id,
            name=p.name,
            version=p.version,
            description=p.description,
            is_synthetic=p.is_synthetic,
            clause_count=await repo.count_clauses(p.id),
        )
        for p in packs
    ]


@router.get("/policy-packs/{pack_id}/clauses", response_model=list[PolicyClauseOut])
async def list_clauses(
    pack_id: int, session: AsyncSession = Depends(get_session)
) -> list[PolicyClauseOut]:
    repo = PolicyRepository(session)
    if await repo.get_pack(pack_id) is None:
        raise ApiError(404, "policy_pack_not_found", f"No policy pack with id {pack_id}.")
    return [
        PolicyClauseOut(
            id=c.id,
            clause_number=c.clause_number,
            heading=c.heading,
            heading_path=c.heading_path,
            text=c.text,
            char_start=c.char_start,
            char_end=c.char_end,
        )
        for c in await repo.list_clauses(pack_id)
    ]
