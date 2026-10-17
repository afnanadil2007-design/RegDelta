"""The ORM models and the migration history must describe the same schema.

The models were once lost to an unanchored ``models/`` ignore rule and had to
be reconstructed from the migrations (see app/db/models/__init__.py). These
tests make both failure modes loud: the package dropping out of git again, and
models drifting from what ``alembic upgrade head`` builds.

Alembic's autogenerate comparison covers tables, columns, types, nullability,
server defaults, indexes, unique constraints, and foreign keys. It does not
compare CHECK constraints, enum labels, index access methods/opclasses, or
generated-column expressions, so those are asserted against the catalog here.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import CheckConstraint, Computed, Enum, text

from app.db.models import Base

BACKEND = Path(__file__).resolve().parents[1]
MODELS_DIR = BACKEND / "app" / "db" / "models"


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=BACKEND, capture_output=True, text=True, check=False)


def test_model_sources_are_not_git_ignored() -> None:
    """Regression guard for the rule that kept this package out of the repo."""
    if shutil.which("git") is None or _git("rev-parse", "--is-inside-work-tree").returncode:
        pytest.skip("not a git checkout (e.g. a source export)")
    sources = sorted(str(p.relative_to(BACKEND)) for p in MODELS_DIR.glob("*.py"))
    assert sources, "no model sources found"
    ignored = _git("check-ignore", "--no-index", *sources).stdout.split()
    assert not ignored, f"model sources are git-ignored: {ignored}"


def test_metadata_registers_the_fourteen_tables() -> None:
    assert len(Base.metadata.tables) == 14


@pytest.mark.asyncio
async def test_autogenerate_finds_no_difference(session) -> None:
    def diff(sync_connection):  # type: ignore[no-untyped-def]
        context = MigrationContext.configure(
            sync_connection,
            opts={"compare_type": True, "compare_server_default": True},
        )
        return compare_metadata(context, Base.metadata)

    connection = await session.connection()
    differences = await connection.run_sync(diff)
    assert differences == [], f"models and migrations disagree: {differences}"


@pytest.mark.asyncio
async def test_enum_labels_match_the_python_enums(session) -> None:
    rows = (
        await session.execute(
            text(
                "SELECT t.typname, array_agg(e.enumlabel ORDER BY e.enumsortorder) "
                "FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid GROUP BY t.typname"
            )
        )
    ).all()
    in_db = {name: list(labels) for name, labels in rows}

    declared: dict[str, list[str]] = {}
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, Enum) and column.type.name:
                declared[column.type.name] = list(column.type.enums)

    assert declared, "no enum columns found in metadata"
    for name, labels in declared.items():
        assert in_db.get(name) == labels, f"enum {name}: db={in_db.get(name)} model={labels}"


@pytest.mark.asyncio
async def test_check_constraints_match(session) -> None:
    rows = (
        await session.execute(
            text(
                "SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) "
                "FROM pg_constraint WHERE contype = 'c' AND connamespace = 'public'::regnamespace"
            )
        )
    ).all()
    in_db = {(table, name): definition for table, name, definition in rows}

    declared = {
        (table.name, constraint.name): str(constraint.sqltext)
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert set(declared) == set(in_db)
    for key, expression in declared.items():
        assert _squash(expression) in _squash(in_db[key])


@pytest.mark.asyncio
async def test_retrieval_index_methods_match(session) -> None:
    rows = (
        await session.execute(
            text("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'")
        )
    ).all()
    in_db = dict(rows)
    for table in Base.metadata.tables.values():
        for index in table.indexes:
            using = index.dialect_options["postgresql"]["using"]
            if not using:
                continue
            definition = in_db[index.name].lower()
            assert f"using {using}" in definition, index.name
            for opclass in (index.dialect_options["postgresql"]["ops"] or {}).values():
                assert opclass in definition, index.name


@pytest.mark.asyncio
async def test_generated_columns_match(session) -> None:
    rows = (
        await session.execute(
            text(
                "SELECT table_name, column_name, generation_expression "
                "FROM information_schema.columns WHERE is_generated = 'ALWAYS'"
            )
        )
    ).all()
    in_db = {(t, c): expr for t, c, expr in rows}
    declared = {
        (table.name, column.name): str(column.computed.sqltext)
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.computed, Computed)
    }
    assert set(declared) == set(in_db)
    for key, expression in declared.items():
        # Postgres reports the text-search config with an explicit cast.
        assert _squash(in_db[key].replace("::regconfig", "")) == _squash(expression)


def _squash(sql: str) -> str:
    return re.sub(r"[\s()]+", "", sql).lower()
