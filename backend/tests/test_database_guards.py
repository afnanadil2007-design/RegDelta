"""The host tools refuse databases that are not RegDelta's to write.

``prepare_db`` must not migrate a database that holds another application's
tables, and the seed must not mix the synthetic corpus into a database that
holds other documents (it rebuilds the citation graph and the tracked gold set
from everything it finds). Neither may act on a DATABASE_URL: the database
they check is the one they write. They run as subprocesses, the way ``make``
runs them, each against a scratch database of its own (named ``*_test``) that
the test drops afterwards.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from app.core.config import ADMIN_DATABASE, get_settings, psycopg_args

ROOT = Path(__file__).resolve().parents[2]


def _server(database: str = ADMIN_DATABASE) -> dict[str, object]:
    return psycopg_args(get_settings().database_target(), database)


def _admin(statement: sql.Composable | str) -> None:
    with psycopg.connect(autocommit=True, connect_timeout=3, **_server()) as c:
        c.execute(statement)


def _scratch_name() -> str:
    return f"regdelta_guard_{uuid.uuid4().hex[:8]}_test"


def _exists(database: str) -> bool:
    with psycopg.connect(autocommit=True, **_server()) as c:
        return bool(
            c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,)).fetchone()
        )


def _drop(database: str) -> None:
    _admin(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database)))


@pytest.fixture
def scratch_db() -> Iterator[str]:
    name = _scratch_name()
    try:
        _admin(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    except psycopg.OperationalError:
        pytest.skip("Postgres is not reachable")
    yield name
    _drop(name)


def _sql(database: str, *statements: str) -> list[tuple]:
    with psycopg.connect(autocommit=True, **_server(database)) as c:
        rows: list[tuple] = []
        for statement in statements:
            cursor = c.execute(statement)
            rows = cursor.fetchall() if cursor.description else []
        return rows


def _tables(database: str) -> list[str]:
    rows = _sql(
        database,
        "SELECT schemaname || '.' || tablename FROM pg_tables"
        " WHERE schemaname NOT IN ('pg_catalog', 'information_schema') ORDER BY 1",
    )
    return [row[0].removeprefix("public.") for row in rows]


def _run(module: str, database: str, **env: str) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "POSTGRES_DB": database,
        "PYTHONPATH": os.pathsep.join([str(ROOT / "backend"), str(ROOT)]),
        **env,
    }
    return subprocess.run(
        [sys.executable, "-m", module],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def test_prepare_db_refuses_a_database_holding_another_applications_tables(
    scratch_db: str,
) -> None:
    _sql(scratch_db, "CREATE TABLE orders (id integer)")
    result = _run("ingestion.prepare_db", scratch_db)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "REFUSED" in result.stdout
    assert "no RegDelta migration history" in result.stdout
    assert _tables(scratch_db) == ["orders"]


def test_prepare_db_refuses_tables_in_a_schema_it_does_not_migrate(scratch_db: str) -> None:
    _sql(scratch_db, "CREATE SCHEMA ledger", "CREATE TABLE ledger.entries (id integer)")
    result = _run("ingestion.prepare_db", scratch_db)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "1 tables outside schema public (ledger.entries)" in result.stdout
    assert _tables(scratch_db) == ["ledger.entries"]


def test_prepare_db_refuses_a_schema_revision_it_does_not_know(scratch_db: str) -> None:
    _sql(
        scratch_db,
        "CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY)",
        "INSERT INTO alembic_version VALUES ('f00dfeed')",
    )
    result = _run("ingestion.prepare_db", scratch_db)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "not one of RegDelta's migrations" in result.stdout
    assert _tables(scratch_db) == ["alembic_version"]


def test_prepare_db_migrates_an_empty_existing_database(scratch_db: str) -> None:
    result = _run("ingestion.prepare_db", scratch_db)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"/{scratch_db}: at head" in result.stdout
    # The target is printed as user@host:port/name; there is no password field.
    server = _server()
    printed = f"database {server['user']}@{server['host']}:{server['port']}/{scratch_db}: exists"
    assert printed in result.stdout
    assert {"alembic_version", "circulars", "findings"} <= set(_tables(scratch_db))


def test_migrate_writes_to_the_database_it_checked(
    scratch_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The migration uses the target prepare_db resolved, not a second lookup."""
    from ingestion import prepare_db

    checked = get_settings().database_target().set(database=scratch_db)
    # Settings now name a database that does not exist: a re-resolution would fail.
    monkeypatch.setenv("POSTGRES_DB", "regdelta_guard_absent_test")
    get_settings.cache_clear()
    assert prepare_db.foreign_content(checked) is None
    prepare_db.migrate(checked)
    assert "alembic_version" in _tables(scratch_db)
    assert not _exists("regdelta_guard_absent_test")


@pytest.mark.parametrize("module", ["ingestion.prepare_db", "ingestion.seed"])
def test_an_inherited_database_url_is_refused_before_any_write(
    scratch_db: str, module: str
) -> None:
    """A test or e2e override (POSTGRES_DB) beside a DATABASE_URL from the shell.

    The URL names a real, empty database with a password; the override names a
    new one. Neither may be created, migrated or seeded, and the URL's
    credentials are not printed.
    """
    server = _server()
    password = "url-only-Secret"
    url = (
        f"postgresql+psycopg://{server['user']}:{password}@{server['host']}:{server['port']}"
        f"/{scratch_db}"
    )
    override = _scratch_name()
    result = _run(module, override, DATABASE_URL=url)
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "REFUSED: DATABASE_URL is set (value not shown)" in result.stdout
    assert password not in output and scratch_db not in output
    assert not _exists(override)
    assert _tables(scratch_db) == []


@pytest.fixture
def reserved_role(scratch_db: str) -> Iterator[tuple[str, str, str]]:
    """A login role whose name and password need percent-encoding in a URL.

    It owns a scratch database that already has the vector extension (creating
    it needs a superuser), so the role itself creates every table.
    """
    role = f"regdelta guard@{uuid.uuid4().hex[:6]}"
    password = "p@ss:w/rd%41?#&=+ é%%"
    try:
        _admin(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(password)
            )
        )
    except psycopg.errors.InsufficientPrivilege:
        pytest.skip("the test user cannot create roles")
    _admin(
        sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
            sql.Identifier(scratch_db), sql.Identifier(role)
        )
    )
    _sql(scratch_db, "CREATE EXTENSION IF NOT EXISTS vector")
    yield role, password, scratch_db
    _drop(scratch_db)
    _admin(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))


def test_reserved_characters_in_credentials_reach_the_server_unchanged(
    reserved_role: tuple[str, str, str],
) -> None:
    """psycopg (the check) and Alembic's async engine (the migration) both log in."""
    role, password, database = reserved_role
    result = _run("ingestion.prepare_db", database, POSTGRES_USER=role, POSTGRES_PASSWORD=password)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert f"database {role}@" in result.stdout and f"/{database}: at head" in result.stdout
    assert password not in output
    owners = _sql(
        database,
        "SELECT DISTINCT tableowner FROM pg_tables WHERE schemaname = 'public'",
    )
    assert owners == [(role,)]
    assert "alembic_version" in _tables(database)


def test_seed_refuses_a_database_holding_other_documents(scratch_db: str) -> None:
    assert _run("ingestion.prepare_db", scratch_db).returncode == 0
    _sql(
        scratch_db,
        "INSERT INTO circulars (circular_number, title, doc_type, source_url, full_text,"
        " page_count, vision_page_count) VALUES ('SEBI/HO/REAL/1', 'An official document',"
        " 'circular', 'https://www.sebi.gov.in/legal/circulars/1.html', 'Text.', 1, 0)",
    )
    result = _run("ingestion.seed", scratch_db)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "REFUSED" in result.stdout
    assert "1 circular(s) that are not from the synthetic corpus" in result.stdout
    # It stopped before the first step: no corpus was generated or ingested.
    assert "=== ingestion." not in result.stdout
    assert _sql(scratch_db, "SELECT count(*) FROM circulars") == [(1,)]
