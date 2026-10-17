"""RegDelta FastAPI application factory.

Wires configuration, structured logging, CORS, the error envelope, and routers.
Business logic lives in services/ and ai/; this module only assembles the app.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

# psycopg's async driver cannot run on Windows' default ProactorEventLoop, and
# uvicorn creates its loop *after* importing this module — so the policy must
# be set here, at import time, or every database call fails at runtime with a
# bare "database down".
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.core.config import get_settings
from app.core.errors import (
    ApiError,
    api_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.core.logging import configure_logging, get_logger
from app.routers import assessments, circulars, evaluation, health, policy, search

log = get_logger("app.main")


async def _warm_models() -> None:
    """Load the CPU models once, off the request path.

    The embedding and cross-encoder models take several seconds each to load.
    Doing it here, in a background task at startup, means the first real search
    or assessment does not stall while the model loads — and because it runs in
    a thread, it never blocks the event loop.
    """
    try:
        from app.ai.retrieval.embeddings import get_model
        from app.ai.retrieval.reranker import get_reranker

        await asyncio.to_thread(get_model)
        await asyncio.to_thread(get_reranker)
        log.info("regdelta.models_warmed")
    except Exception:  # noqa: BLE001 - warmup is best-effort; never fail startup
        log.exception("regdelta.model_warmup_failed")


async def _recover_interrupted_runs() -> None:
    """Fail runs a previous process left mid-flight; never block startup."""
    try:
        from app.services.assessment import recover_interrupted_runs

        await recover_interrupted_runs()
    except Exception:  # noqa: BLE001 - e.g. database not reachable yet
        log.exception("regdelta.recovery_failed")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()  # validates env fail-fast before serving traffic
    settings.database_target()  # likewise the database settings (DatabaseConfigError)
    configure_logging(settings.log_level)
    ready, reason = settings.provider_readiness()
    log.info(
        "regdelta.startup",
        extra={
            "env": settings.env,
            "provider": settings.llm_provider,
            "provider_ready": ready,
            "provider_reason": reason,
        },
    )
    await _recover_interrupted_runs()
    warm_task = asyncio.create_task(_warm_models()) if settings.warm_models_on_startup else None
    yield
    if warm_task is not None:
        warm_task.cancel()
    log.info("regdelta.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="RegDelta API",
        version="0.2.0",
        summary="Regulatory change-impact engine for SEBI circulars",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )

    app.add_exception_handler(ApiError, api_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)

    for module in (health, circulars, search, assessments, policy, evaluation):
        app.include_router(module.router, prefix="/api")
    return app


app = create_app()
