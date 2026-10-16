"""Create the configured database if it is missing, then migrate it to head.

The database name comes from the usual settings (``POSTGRES_DB``), so the
same command prepares the demo, test and end-to-end databases:

    python -m ingestion.prepare_db
    POSTGRES_DB=regdelta_test python -m ingestion.prepare_db

It prints the target (user, host, port and name; never the password) and
refuses to migrate a database that already holds tables without RegDelta's
migration history, or with a revision this checkout does not know: those
belong to something else, and migrating them would write RegDelta's schema
into it.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import psycopg
from psycopg import sql

from app.core.config import get_settings

BACKEND = Path(__file__).resolve().parents[1] / "backend"


def target() -> str:
    s = get_settings()
    return f"{s.postgres_user}@{s.postgres_host}:{s.postgres_port}/{s.postgres_db}"


def _connect(dbname: str) -> psycopg.Connection:
    s = get_settings()
    return psycopg.connect(
        host=s.postgres_host,
        port=s.postgres_port,
        user=s.postgres_user,
        password=s.postgres_password,
        dbname=dbname,
        autocommit=True,
    )


def ensure_database() -> bool:
    """Create the database when absent; True if it was created."""
    name = get_settings().postgres_db
    with _connect("postgres") as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (name,)
        ).fetchone()
        if exists:
            return False
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        return True


def known_revisions() -> set[str]:
    from alembic.script import ScriptDirectory

    return {s.revision for s in ScriptDirectory(str(BACKEND / "alembic")).walk_revisions()}


def foreign_content() -> str | None:
    """Why the existing database is not RegDelta's to migrate, or None."""
    with _connect(get_settings().postgres_db) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
            ).fetchall()
        ]
        if not tables:
            return None
        if "alembic_version" not in tables:
            listed = ", ".join(tables[:5]) + (", ..." if len(tables) > 5 else "")
            return f"it holds {len(tables)} tables ({listed}) and no RegDelta migration history"
        versions = {row[0] for row in connection.execute("SELECT version_num FROM alembic_version")}
    unknown = versions - known_revisions()
    if unknown:
        return (
            f"its schema revision {', '.join(sorted(unknown))} is not one of RegDelta's migrations"
        )
    return None


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, "head")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create (if needed) and migrate the database.")
    parser.parse_args(argv)
    created = ensure_database()
    print(f"database {target()}: {'created' if created else 'exists'}")
    if not created and (reason := foreign_content()):
        print(f"REFUSED: not migrating {target()}: {reason}.")
        print("Point POSTGRES_DB (or POSTGRES_HOST/PORT) at a RegDelta or new database.")
        return 1
    migrate()
    print(f"database {target()}: at head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
