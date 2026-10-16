"""Create the configured database if it is missing, then migrate it to head.

The database is the one ``Settings.database_target()`` names (the POSTGRES_*
settings; a DATABASE_URL is refused), so the same command prepares the demo,
test and end-to-end databases:

    python -m ingestion.prepare_db
    POSTGRES_DB=regdelta_test python -m ingestion.prepare_db

It resolves that target once and uses it for every step: creating the
database (over an administrative connection to the server's ``postgres``
database), the safety check, and the migration. It prints the target (user,
host, port and name; never the password) and refuses to migrate a database
that already holds tables without RegDelta's migration history, tables in a
schema other than the one migrations write to, or a revision this checkout
does not know: those belong to something else, and migrating them would write
RegDelta's schema into it.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy.engine import URL

from app.core.config import (
    ADMIN_DATABASE,
    DatabaseConfigError,
    describe_database,
    get_settings,
    psycopg_args,
)

BACKEND = Path(__file__).resolve().parents[1] / "backend"


def target() -> str:
    return describe_database(get_settings().database_target())


def _connect(url: URL, database: str | None = None) -> psycopg.Connection:
    return psycopg.connect(**psycopg_args(url, database), autocommit=True)


def ensure_database(url: URL) -> bool:
    """Create the database when absent; True if it was created."""
    with _connect(url, ADMIN_DATABASE) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (url.database,)
        ).fetchone()
        if exists:
            return False
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(url.database)))
        return True


def known_revisions() -> set[str]:
    from alembic.script import ScriptDirectory

    return {s.revision for s in ScriptDirectory(str(BACKEND / "alembic")).walk_revisions()}


def foreign_content(url: URL) -> str | None:
    """Why the existing database is not RegDelta's to migrate, or None."""
    with _connect(url) as connection:
        # Migrations write to the first schema on the search path.
        schema = connection.execute("SELECT current_schema()").fetchone()[0]
        rows = connection.execute(
            "SELECT schemaname, tablename FROM pg_tables WHERE schemaname <> 'information_schema'"
            " AND schemaname NOT LIKE 'pg\\_%' ORDER BY 1, 2"
        ).fetchall()
        elsewhere = [f"{s}.{t}" for s, t in rows if s != schema]
        tables = [t for s, t in rows if s == schema]
        if elsewhere:
            listed = ", ".join(elsewhere[:5]) + (", ..." if len(elsewhere) > 5 else "")
            return f"it holds {len(elsewhere)} tables outside schema {schema} ({listed})"
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


def migrate(url: URL) -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    # The database just checked, not a second resolution of the settings.
    config.attributes["database_target"] = url
    command.upgrade(config, "head")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create (if needed) and migrate the database.")
    parser.parse_args(argv)
    try:
        url = get_settings().database_target()
    except DatabaseConfigError as exc:
        print(f"REFUSED: {exc}")
        return 1
    name = describe_database(url)
    created = ensure_database(url)
    print(f"database {name}: {'created' if created else 'exists'}")
    if not created and (reason := foreign_content(url)):
        print(f"REFUSED: not migrating {name}: {reason}.")
        print("Point POSTGRES_DB (or POSTGRES_HOST/PORT) at a RegDelta or new database.")
        return 1
    migrate(url)
    print(f"database {name}: at head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
