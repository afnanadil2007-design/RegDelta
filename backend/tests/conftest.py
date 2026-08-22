"""Shared test fixtures.

Provides a minimally-valid environment so ``get_settings`` passes validation
without a real provider key, and a live-database session fixture for
integration tests. Integration tests skip cleanly when no database is
reachable, so the unit suite runs anywhere.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-dummy")
os.environ.setdefault("LLM_PROVIDER", "anthropic")
os.environ.setdefault("POSTGRES_HOST", "localhost")
# Never spend the multi-second model load inside the test app's startup.
os.environ.setdefault("WARM_MODELS_ON_STARTUP", "false")

# psycopg's async mode cannot run on Windows' default ProactorEventLoop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    from app.core.config import get_settings

    get_settings.cache_clear()


async def _database_available() -> bool:
    from sqlalchemy import text

    from app.db.session import get_engine

    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest_asyncio.fixture
async def session() -> AsyncIterator:
    """A session whose writes are always discarded, even across ``commit()``.

    The session is bound to an outer transaction and joins it as a savepoint,
    so code under test can call ``session.commit()`` — as the ingestion service
    does per document — while the outer rollback still leaves the database
    untouched. A plain session + rollback would leak committed rows between
    tests and collide on unique constraints.

    Skips when Postgres is not running, so `pytest` is usable anywhere.
    """
    if not await _database_available():
        pytest.skip("PostgreSQL not reachable — integration test skipped")

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.session import get_engine

    async with get_engine().connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as s:
            yield s
        await transaction.rollback()
