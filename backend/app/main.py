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
from fastapi.middleware.cors import CORSMiddleware

# psycopg's async driver cannot run on Windows' default ProactorEventLoop, and
# uvicorn creates its loop *after* importing this module — so the policy must
# be set here, at import time, or every database call fails at runtime with a
# bare "database down".
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.core.config import get_settings
from app.core.errors import ApiError, api_error_handler, unhandled_error_handler
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


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()  # validates env fail-fast before serving traffic
    configure_logging(settings.log_level)
    log.info("regdelta.startup", extra={"env": settings.env, "provider": settings.llm_provider})
    warm_task = (
        asyncio.create_task(_warm_models()) if settings.warm_models_on_startup else None
    )
    yield
    if warm_task is not None:
        warm_task.cancel()
    log.info("regdelta.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="RegDelta API",
        version="0.1.0",
        summary="Regulatory change-impact engine for SEBI circulars",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(ApiError, api_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)

    for module in (health, circulars, search, assessments, policy, evaluation):
        app.include_router(module.router, prefix="/api")
    return app


app = create_app()
