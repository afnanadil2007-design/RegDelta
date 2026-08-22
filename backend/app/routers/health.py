"""Health endpoint.

Reports process liveness and, best-effort, database reachability. Routers hold
no business logic: this one only shapes a Pydantic response.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.repositories.circulars import CircularRepository

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    env: str
    database: str  # "up" | "down"


@router.get("/health", response_model=HealthResponse)
async def health(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    # A database that is not reachable yet is a reportable state, not a 500.
    reachable = await CircularRepository(session).ping()
    return HealthResponse(
        status="ok", env=settings.env, database="up" if reachable else "down"
    )
