"""Shared test fixtures.

Integration tests run against a disposable database whose name ends in
``_test`` (default ``regdelta_test``); they refuse any other database so a
developer's seeded data is never written to. The schema is brought to
``alembic upgrade head`` once per session. When Postgres is unreachable the
integration tests skip, so the unit suite runs anywhere.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

BACKEND = Path(__file__).resolve().parents[1]
TEST_DATABASE_SUFFIX = "_test"

# Environment variables outrank .env, so these keep tests off the dev database
# and off any real provider even when a developer's .env says otherwise.
os.environ.setdefault("POSTGRES_DB", "regdelta_test")
os.environ.setdefault("LLM_PROVIDER", "anthropic")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-dummy")
os.environ.setdefault("POSTGRES_HOST", "localhost")
# Never spend the multi-second model load inside the test app's startup.
os.environ.setdefault("WARM_MODELS_ON_STARTUP", "false")
# pytest-asyncio and Starlette's TestClient each run their own event loops; a
# pooled connection must never be reused across loops.
os.environ.setdefault("DATABASE_POOL", "null")

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


def _database_name() -> str:
    from sqlalchemy.engine import make_url

    from app.core.config import get_settings

    return make_url(get_settings().sqlalchemy_url).database or ""


@pytest.fixture(scope="session")
def migrated_database() -> str:
    """Bring the test database to ``head`` once, or skip every DB test."""
    from alembic import command
    from alembic.config import Config

    name = _database_name()
    if not name.endswith(TEST_DATABASE_SUFFIX):
        pytest.skip(
            f"refusing to run integration tests against database {name!r}; "
            f"use a database whose name ends in {TEST_DATABASE_SUFFIX!r}"
        )
    if not asyncio.run(_database_available()):
        pytest.skip("PostgreSQL not reachable — integration test skipped")

    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, "head")
    return name


@pytest_asyncio.fixture
async def session(migrated_database: str) -> AsyncIterator:
    """A session whose writes are always discarded, even across ``commit()``.

    The session is bound to an outer transaction and joins it as a savepoint,
    so code under test can call ``session.commit()`` — as the ingestion service
    does per document — while the outer rollback still leaves the database
    untouched.
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.session import get_engine

    async with get_engine().connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as s:
            yield s
        await transaction.rollback()
