"""Alembic environment.

Runs migrations against the async engine. The database is the one
``Settings.database_target()`` names, or the one a caller already checked and
passed in ``config.attributes["database_target"]`` (``ingestion.prepare_db``
does), so the database checked is the database migrated. The URL is used as
an object, never written into the ini configuration, whose ``%`` interpolation
would corrupt a percent-encoded password. ``target_metadata`` is
``Base.metadata``; importing ``app.db.models`` registers every table so
autogenerate sees them.
"""

from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import URL, Connection
from sqlalchemy.ext.asyncio import create_async_engine

# Side-effect import: registers all 14 tables on Base.metadata for autogenerate.
import app.db.models  # noqa: F401
from app.core.config import get_settings
from app.db.base import Base

config = context.config
if config.config_file_name is not None:
    # Run in-process (prepare_db, the tests), keep the app's loggers working.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

database: URL = config.attributes.get("database_target") or get_settings().database_target()
target_metadata = Base.metadata


def _run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=database,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(database, poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    # psycopg's async mode cannot run on Windows' default ProactorEventLoop.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_migrations_online())
