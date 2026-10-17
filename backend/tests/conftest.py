"""Shared test fixtures.

Integration tests run against a disposable database whose name ends in
``_test`` (default ``regdelta_test``); they refuse any other database so a
developer's seeded data is never written to. Once per session the schema is
brought to ``alembic upgrade head`` and every table is emptied, and the
``corpus`` fixture ingests a small synthetic corpus through the real pipeline.
When Postgres is unreachable the integration tests skip, so the unit suite
runs anywhere.

The provider defaults to ``deterministic``: no test needs, or may use, a real
provider key. Gateway tests that exercise Groq/Anthropic request translation
inject fake clients.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
import pytest_asyncio

BACKEND = Path(__file__).resolve().parents[1]
TEST_DATABASE_SUFFIX = "_test"

# Environment variables outrank .env, so these keep tests off the dev database
# and off any real provider even when a developer's .env says otherwise.
os.environ.setdefault("POSTGRES_DB", "regdelta_test")
os.environ["LLM_PROVIDER"] = "deterministic"
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


@pytest.fixture(autouse=True)
def _forget_shared_searches() -> None:
    """Reranked results are shared and reused for minutes; never across tests."""
    from app.services import search

    search._running.clear()
    search._finished.clear()


@pytest.fixture(autouse=True)
def _reset_sse_exit_event() -> None:
    """sse-starlette keeps one process-wide exit event bound to the first loop.

    A server runs one loop for its lifetime, but TestClient starts a new loop
    per request, so a second streaming request would find the event bound to a
    dead loop. Clearing it lets each test's stream create its own.
    """
    from sse_starlette.sse import AppStatus

    AppStatus.should_exit_event = None


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
    from app.core.config import get_settings

    return get_settings().database_target().database or ""


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
    asyncio.run(_empty_all_tables())
    return name


async def _empty_all_tables() -> None:
    from sqlalchemy import text

    from app.db.models import Base
    from app.db.session import get_engine

    tables = ", ".join(sorted(Base.metadata.tables))
    async with get_engine().begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@dataclass(frozen=True)
class SeededCorpus:
    """Ids of what the ``corpus`` fixture created, keyed by circular number."""

    circular_ids: dict[str, int]
    policy_pack_id: int

    def id_of(self, circular_number: str) -> int:
        return self.circular_ids[circular_number]


@pytest.fixture(scope="session")
def corpus(migrated_database: str, tmp_path_factory: pytest.TempPathFactory) -> SeededCorpus:
    """Five synthetic fixture circulars and the policy pack, committed once.

    Built with the production code path — PDF ingestion, the citation graph,
    the policy-pack indexer, the rules extractor, and real embeddings — so API
    and assessment tests exercise what the demo runs. Tests must not mutate it;
    anything they write goes through ``session`` (rolled back) or is cleaned up.
    """
    return asyncio.run(_seed_corpus(tmp_path_factory.mktemp("corpus")))


async def _seed_corpus(directory: Path) -> SeededCorpus:
    from sqlalchemy import select

    from app.ai.extraction.rules import EXTRACTOR_NAME, extract_obligations_by_rule
    from app.ai.retrieval.embeddings import embed_documents
    from app.db.models.corpus import Chunk, Obligation
    from app.db.models.policy import PolicyClause
    from app.db.session import get_sessionmaker
    from app.repositories.circulars import CircularRepository, ParagraphRepository
    from app.services.citation_graph import build_graph
    from app.services.ingestion import CircularMeta, ingest_batch
    from app.services.policy_pack import index_pack
    from tests.fixtures import CORPUS_FIXTURES, write_fixture_pdf

    items = [
        (
            write_fixture_pdf(fixture, directory / str(i)),
            CircularMeta(
                circular_number=fixture.circular_number,
                title=fixture.title,
                issue_date=date.fromisoformat(issued),
                department=fixture.circular_number.split("/")[2],
                source_url=f"synthetic://tests/{i}.pdf",
            ),
        )
        for i, (fixture, issued) in enumerate(CORPUS_FIXTURES)
    ]
    async with get_sessionmaker()() as session:
        report = await ingest_batch(session, items)
        assert not report.failed, report.failed
        await build_graph(session)
        pack = await index_pack(
            session,
            BACKEND.parent / "data" / "policy_packs" / "internal_compliance_manual_v1.md",
            name="Test pack",
            version="1",
        )
        circulars = await CircularRepository(session).list_circulars(limit=100)
        for circular in circulars:
            for paragraph in await ParagraphRepository(session).list_for_circular(circular.id):
                for item in extract_obligations_by_rule(paragraph.text):
                    session.add(
                        Obligation(
                            circular_id=circular.id,
                            paragraph_id=paragraph.id,
                            text=item.text,
                            actor=item.actor,
                            action=item.action,
                            modality=item.modality,
                            char_start=paragraph.char_start + item.char_start,
                            char_end=paragraph.char_start + item.char_end,
                            extractor=EXTRACTOR_NAME,
                        )
                    )
        for model in (Chunk, PolicyClause):
            rows = list((await session.execute(select(model))).scalars())
            for row, vector in zip(rows, embed_documents([r.text for r in rows]), strict=True):
                row.embedding = vector
        await session.commit()
        return SeededCorpus(
            circular_ids={c.circular_number: c.id for c in circulars}, policy_pack_id=pack.id
        )


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
