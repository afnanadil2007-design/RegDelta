"""Migration 0004's data backfill, on rows shaped the way the old code wrote them.

Runs in a scratch database created for the test (``regdelta_migration_<pid>_test``)
so it can migrate from an older revision without touching the shared test DB.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from tests.conftest import BACKEND


def _sync_url(url: str) -> str:
    # render_as_string: str(URL) masks the password as "***".
    return make_url(url).set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest.fixture
def scratch_database(migrated_database: str) -> Iterator[str]:
    """A fresh, empty database; settings point at it for the test's duration."""
    base_url = make_url(get_settings().sqlalchemy_url)
    name = f"regdelta_migration_{os.getpid()}_test"
    admin = create_engine(
        _sync_url(base_url.render_as_string(hide_password=False)), isolation_level="AUTOCOMMIT"
    )
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))

    scratch_url = base_url.set(database=name).render_as_string(hide_password=False)
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = scratch_url
    get_settings.cache_clear()
    try:
        yield scratch_url
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _alembic() -> Config:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    return config


# Findings: 1 is a verified judgement, 2 a retrieval no-match the old code
# marked verified with an invented 0.4, and 3 an unverified judgement.
LEGACY_ROWS = """
INSERT INTO circulars (id, circular_number, title, doc_type, full_text, page_count,
                       vision_page_count)
    VALUES (1, 'C/1', 't', 'circular', 'Brokers shall report margin by T+1 day.', 1, 0);
INSERT INTO paragraphs (id, circular_id, order_index, text, char_start, char_end,
                        extraction_method)
    VALUES (1, 1, 0, 'Brokers shall report margin by T+1 day.', 0, 39, 'text');
INSERT INTO obligations (id, circular_id, paragraph_id, text, char_start, char_end, confidence)
    VALUES (1, 1, 1, 'Brokers shall report margin by T+1 day.', 0, 39, 0.55);
INSERT INTO policy_packs (id, name, version, is_synthetic) VALUES (1, 'p', '1', true);
INSERT INTO policy_clauses (id, policy_pack_id, order_index, clause_number, text,
                            char_start, char_end)
    VALUES (1, 1, 0, 'C.3', 'Report by T+2 days.', 0, 19);
INSERT INTO assessments (id, run_id, circular_id, policy_pack_id, status, total_tokens,
                         total_cost_usd)
    VALUES (1, gen_random_uuid(), 1, 1, 'COMPLETED', 0, 0);
INSERT INTO findings (id, assessment_id, obligation_id, policy_clause_id, impact_type,
                      rationale, confidence, circular_span_start, circular_span_end,
                      verified, verification_attempts, analyst_decision)
    VALUES (1, 1, 1, 1, 'MODIFIED', 'r', 0.8, 0, 7, true, 1, 'PENDING'),
           (2, 1, 1, NULL, 'NO_MATCH', 'r', 0.4, NULL, NULL, true, 0, 'PENDING'),
           (3, 1, 1, 1, 'CONFLICT', 'r', 0.7, 0, 7, false, 3, 'PENDING');
"""


def test_0004_backfills_quote_status_and_clears_invented_scores(scratch_database: str) -> None:
    command.upgrade(_alembic(), "0003_agent_run_seq")
    engine = create_engine(_sync_url(scratch_database))
    with engine.begin() as conn:
        for statement in LEGACY_ROWS.split(";"):
            if statement.strip():
                conn.execute(text(statement))

    command.upgrade(_alembic(), "head")
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, quote_status::text, confidence FROM findings ORDER BY id")
        ).all()
        extractor = conn.execute(text("SELECT extractor FROM obligations")).scalar_one()
    assert rows == [(1, "VERIFIED", 0.8), (2, "NOT_APPLICABLE", None), (3, "FAILED", 0.7)]
    assert extractor is None, "provenance of pre-0004 obligations is unknown, not guessed"

    command.downgrade(_alembic(), "0003_agent_run_seq")
    with engine.connect() as conn:
        verified = conn.execute(text("SELECT verified FROM findings ORDER BY id")).scalars().all()
    assert verified == [True, True, False]
    engine.dispose()


def test_a_fresh_database_migrates_to_head(scratch_database: str) -> None:
    command.upgrade(_alembic(), "head")
    engine = create_engine(_sync_url(scratch_database))
    with engine.connect() as conn:
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        tables = conn.execute(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
        ).scalar_one()
    engine.dispose()
    assert revision == "0004_evidence_provenance"
    assert tables == 15  # 14 application tables + alembic_version
