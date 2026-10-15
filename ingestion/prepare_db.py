"""Create the configured database if it is missing, then migrate it to head.

The database name comes from the usual settings (``POSTGRES_DB``), so the
same command prepares the demo, test and end-to-end databases:

    python -m ingestion.prepare_db
    POSTGRES_DB=regdelta_test python -m ingestion.prepare_db
"""

from __future__ import annotations

import argparse
from pathlib import Path

import psycopg
from psycopg import sql

from app.core.config import get_settings

BACKEND = Path(__file__).resolve().parents[1] / "backend"


def ensure_database() -> bool:
    """Create the database when absent; True if it was created."""
    settings = get_settings()
    with psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        dbname="postgres",
        autocommit=True,
    ) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (settings.postgres_db,)
        ).fetchone()
        if exists:
            return False
        connection.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(settings.postgres_db))
        )
        return True


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, "head")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create (if needed) and migrate the database.")
    parser.parse_args(argv)
    name = get_settings().postgres_db
    print(f"database {name}: {'created' if ensure_database() else 'exists'}")
    migrate()
    print(f"database {name}: at head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
