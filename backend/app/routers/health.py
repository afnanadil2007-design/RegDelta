"""Health endpoint.

Reports process liveness, database reachability, the applied schema revision,
and whether the configured assessment provider can run. Unreachable or
unconfigured dependencies are reportable states, not 500s, so the UI can say
what is missing.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.repositories.circulars import CircularRepository
from app.routers.schemas import HealthResponse, ProviderStatus

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    repo = CircularRepository(session)
    reachable = await repo.ping()
    ready, reason = settings.provider_readiness()
    return HealthResponse(
        status="ok",
        env=settings.env,
        database="up" if reachable else "down",
        schema_revision=await repo.schema_revision() if reachable else None,
        provider=ProviderStatus(
            name=settings.llm_provider,
            model=settings.effective_model,
            deterministic=settings.llm_provider == "deterministic",
            ready=ready,
            reason=reason,
        ),
    )
