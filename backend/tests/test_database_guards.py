"""The host tools refuse databases that are not RegDelta's to write.

``prepare_db`` must not migrate a database that holds another application's
tables, and the seed must not mix the synthetic corpus into a database that
holds other documents (it rebuilds the citation graph and the tracked gold set
from everything it finds). Both run as subprocesses, the way ``make`` runs
them, each against a scratch database of its own (named ``*_test``) that the
test drops afterwards.
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

ROOT = Path(__file__).resolve().parents[2]


def _server() -> dict[str, object]:
    from app.core.config import get_settings

    s = get_settings()
    return {
        "host": s.postgres_host,
        "port": s.postgres_port,
        "user": s.postgres_user,
        "password": s.postgres_password,
    }


@pytest.fixture
def scratch_db() -> Iterator[str]:
    name = f"regdelta_guard_{uuid.uuid4().hex[:8]}_test"
    try:
        with psycopg.connect(
            dbname="postgres", autocommit=True, connect_timeout=3, **_server()
        ) as c:
            c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    except psycopg.OperationalError:
        pytest.skip("Postgres is not reachable")
    yield name
    with psycopg.connect(dbname="postgres", autocommit=True, **_server()) as c:
        c.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


def _sql(database: str, *statements: str) -> list[tuple]:
    with psycopg.connect(dbname=database, autocommit=True, **_server()) as c:
        rows: list[tuple] = []
        for statement in statements:
            cursor = c.execute(statement)
            rows = cursor.fetchall() if cursor.description else []
        return rows


def _tables(database: str) -> list[str]:
    rows = _sql(database, "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1")
    return [row[0] for row in rows]


def _run(module: str, database: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "POSTGRES_DB": database,
        "PYTHONPATH": os.pathsep.join([str(ROOT / "backend"), str(ROOT)]),
    }
    return subprocess.run(
        [sys.executable, "-m", module],
        cwd=ROOT,
        env=env,
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
