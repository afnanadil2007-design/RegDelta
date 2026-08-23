"""Stage 2 schema tests.

The span-integrity test is the one the brief singles out: for every stored
obligation, ``full_text[char_start:char_end]`` must be non-empty and contained
within its source paragraph. It is asserted against the database, using the
slice Postgres itself computes.
"""

from __future__ import annotations

from datetime import date

import pytest
from app.db.models import Base
from app.db.models.corpus import Circular, Obligation, Paragraph
from app.db.models.enums import ExtractionMethod, ImpactType
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.repositories.circulars import CircularRepository, ParagraphRepository
from app.repositories.obligations import ObligationRepository

# A miniature circular whose offsets are known exactly.
FULL_TEXT = (
    "1. Introduction\n"  # 0..16
    "This circular applies to all stock brokers.\n"  # 16..60
    "2. Requirements\n"
    "Every stock broker shall collect upfront margin from clients by T+1.\n"
)


def test_all_fourteen_tables_registered() -> None:
    expected = {
        "circulars",
        "paragraphs",
        "chunks",
        "citations",
        "supersessions",
        "obligations",
        "policy_packs",
        "policy_clauses",
        "assessments",
        "findings",
        "agent_runs",
        "agent_steps",
        "eval_runs",
        "eval_results",
    }
    assert expected == set(Base.metadata.tables)


def test_impact_type_vocabulary_is_fixed() -> None:
    # The UI colour-codes on these and the eval harness aggregates by them.
    assert [e.value for e in ImpactType] == [
        "NEW_REQUIREMENT",
        "MODIFIED",
        "CONFLICT",
        "ALREADY_COVERED",
        "NO_MATCH",
    ]


@pytest.mark.asyncio
async def test_enum_labels_are_values_not_member_names(session) -> None:
    """SQLAlchemy defaults to persisting member *names*; we persist values.

    Regression guard: the API's `mode` parameter, the ingestion contract
    (extraction_method='vision'), and the DB vocabulary must agree.
    """
    rows = (
        await session.execute(
            text(
                "SELECT t.typname, string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder) "
                "FROM pg_type t JOIN pg_enum e ON t.oid = e.enumtypid GROUP BY t.typname"
            )
        )
    ).all()
    labels = {r[0]: r[1].split(",") for r in rows}

    assert labels["extraction_method"] == ["text", "vision"]
    assert labels["retrieval_mode"] == ["dense", "lexical", "hybrid", "hybrid_rerank"]
    assert labels["supersession_type"] == ["supersedes", "rescinds", "amends", "partial"]
    # ImpactType's values are uppercase by spec, so names and values coincide.
    assert labels["impact_type"] == [e.value for e in ImpactType]


@pytest.mark.asyncio
async def test_extraction_method_round_trips_as_value(session) -> None:
    """A vision paragraph is stored as 'vision' and reads back as the enum."""
    circular = await CircularRepository(session).add(
        Circular(
            circular_number="SEBI/HO/TEST/CIR/P/2024/004",
            title="Enum round-trip fixture",
            full_text=FULL_TEXT,
        )
    )
    para = (
        await ParagraphRepository(session).add_all(
            [
                Paragraph(
                    circular_id=circular.id,
                    order_index=0,
                    text="Table extracted from a scanned page.",
                    char_start=0,
                    char_end=36,
                    extraction_method=ExtractionMethod.VISION,
                )
            ]
        )
    )[0]

    raw = (
        await session.execute(
            text("SELECT extraction_method::text FROM paragraphs WHERE id = :i"), {"i": para.id}
        )
    ).scalar_one()
    assert raw == "vision"
    assert para.extraction_method is ExtractionMethod.VISION


@pytest.mark.asyncio
async def test_retrieval_indexes_exist(session) -> None:
    """HNSW (vector_cosine_ops) and GIN indexes must actually be in the DB."""
    rows = (
        await session.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE schemaname='public' AND (indexdef ILIKE '%hnsw%' OR indexdef ILIKE '%gin%')"
            )
        )
    ).all()
    defs = {r[0]: r[1] for r in rows}

    assert "vector_cosine_ops" in defs["ix_chunks_embedding_hnsw"]
    assert "hnsw" in defs["ix_chunks_embedding_hnsw"].lower()
    assert "vector_cosine_ops" in defs["ix_policy_clauses_embedding_hnsw"]
    assert "gin" in defs["ix_chunks_tsv"].lower()
    assert "gin" in defs["ix_policy_clauses_tsv"].lower()


@pytest.mark.asyncio
async def test_obligation_spans_resolve_and_sit_inside_their_paragraph(session) -> None:
    """The provenance invariant, asserted end-to-end through the database."""
    circular = await CircularRepository(session).add(
        Circular(
            circular_number="SEBI/HO/TEST/CIR/P/2024/001",
            title="Span integrity fixture",
            issue_date=date(2024, 1, 1),
            department="MIRSD",
            full_text=FULL_TEXT,
        )
    )

    para_text = "Every stock broker shall collect upfront margin from clients by T+1."
    para_start = FULL_TEXT.index(para_text)
    paragraph = (
        await ParagraphRepository(session).add_all(
            [
                Paragraph(
                    circular_id=circular.id,
                    order_index=0,
                    para_number="2.1",
                    text=para_text,
                    char_start=para_start,
                    char_end=para_start + len(para_text),
                    page_number=1,
                    extraction_method=ExtractionMethod.TEXT,
                )
            ]
        )
    )[0]

    # The obligation span is a strict subspan of the paragraph.
    ob_text = "shall collect upfront margin from clients by T+1"
    ob_start = FULL_TEXT.index(ob_text)
    await ObligationRepository(session).add_all(
        [
            Obligation(
                circular_id=circular.id,
                paragraph_id=paragraph.id,
                text=ob_text,
                actor="stock broker",
                modality="shall",
                char_start=ob_start,
                char_end=ob_start + len(ob_text),
                confidence=0.9,
            )
        ]
    )

    rows = await ObligationRepository(session).list_with_source_text(circular.id)
    assert rows, "expected at least one obligation"

    for obligation, span_text, para_lo, para_hi in rows:
        # Non-empty and exactly what was stored.
        assert span_text, f"obligation {obligation.id} resolved to an empty span"
        assert span_text == obligation.text
        # Contained within the source paragraph's bounds.
        assert para_lo <= obligation.char_start < obligation.char_end <= para_hi


@pytest.mark.asyncio
async def test_span_check_constraint_rejects_inverted_spans(session) -> None:
    """char_end must exceed char_start; the DB enforces it, not just Python."""
    circular = await CircularRepository(session).add(
        Circular(
            circular_number="SEBI/HO/TEST/CIR/P/2024/002",
            title="Constraint fixture",
            full_text=FULL_TEXT,
        )
    )
    with pytest.raises(IntegrityError):
        await ParagraphRepository(session).add_all(
            [
                Paragraph(
                    circular_id=circular.id,
                    order_index=0,
                    text="x",
                    char_start=50,
                    char_end=10,  # inverted
                )
            ]
        )


@pytest.mark.asyncio
async def test_tsv_is_generated_from_text(session) -> None:
    """chunks.tsv is a generated column — populated without an explicit write."""
    from app.db.models.corpus import Chunk

    from app.repositories.circulars import ChunkRepository

    circular = await CircularRepository(session).add(
        Circular(
            circular_number="SEBI/HO/TEST/CIR/P/2024/003",
            title="tsv fixture",
            full_text=FULL_TEXT,
        )
    )
    chunk = (
        await ChunkRepository(session).add_all(
            [
                Chunk(
                    circular_id=circular.id,
                    order_index=0,
                    paragraph_ids=[],
                    text="Stock brokers shall collect upfront margin.",
                    char_start=0,
                    char_end=42,
                    token_count=8,
                )
            ]
        )
    )[0]

    tsv = (
        await session.execute(text("SELECT tsv::text FROM chunks WHERE id = :i"), {"i": chunk.id})
    ).scalar_one()
    assert "margin" in tsv and "broker" in tsv
