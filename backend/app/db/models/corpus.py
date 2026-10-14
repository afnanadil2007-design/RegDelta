"""The regulatory corpus: circulars, their paragraphs and chunks, the citation
and supersession graph, and extracted obligations.

Every ``char_start``/``char_end`` pair is a half-open offset into
``Circular.full_text`` measured in Unicode code points (Python ``str`` indices,
which Postgres ``substr`` on a UTF-8 database agrees with). The ingestion
pipeline guarantees ``full_text[char_start:char_end] == text`` for paragraphs
and chunks; obligations sit inside their paragraph's span.
"""

from __future__ import annotations

from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import ExtractionMethod, ResolutionMethod, SupersessionType, db_enum

# Must equal Settings.embedding_dim and the VECTOR(384) columns in migration
# 0002; changing the embedding model's dimension needs a new migration.
EMBEDDING_DIM = 384

# Generated, so lexical search can never drift from the stored text.
_TSV_EXPRESSION = "to_tsvector('english', text)"


class Circular(Base):
    __tablename__ = "circulars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    circular_number: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    issue_date: Mapped[date | None] = mapped_column(Date, index=True)
    department: Mapped[str | None] = mapped_column(String(64), index=True)
    doc_type: Mapped[str] = mapped_column(String(32), index=True, default="circular")
    source_url: Mapped[str | None] = mapped_column(Text)
    pdf_path: Mapped[str | None] = mapped_column(Text)
    full_text: Mapped[str] = mapped_column(Text)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    vision_page_count: Mapped[int] = mapped_column(Integer, default=0)
    # SHA-256 of the source PDF bytes; makes re-ingestion of a file a no-op.
    checksum: Mapped[str | None] = mapped_column(String(64), index=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Paragraph(Base):
    __tablename__ = "paragraphs"
    __table_args__ = (
        CheckConstraint("char_end > char_start", name="ck_paragraph_span_ordered"),
        Index("ix_paragraphs_circular_order", "circular_id", "order_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    circular_id: Mapped[int] = mapped_column(
        ForeignKey("circulars.id", ondelete="CASCADE"), index=True
    )
    order_index: Mapped[int] = mapped_column(Integer)
    para_number: Mapped[str | None] = mapped_column(String(32))
    heading_path: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer)
    extraction_method: Mapped[ExtractionMethod] = mapped_column(
        db_enum(ExtractionMethod, "extraction_method"), default=ExtractionMethod.TEXT
    )
    text_quality_score: Mapped[float | None] = mapped_column(Float)


class Chunk(Base):
    """A retrieval unit of one or more whole, contiguous paragraphs."""

    __tablename__ = "chunks"
    __table_args__ = (
        CheckConstraint("char_end > char_start", name="ck_chunk_span_ordered"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    circular_id: Mapped[int] = mapped_column(
        ForeignKey("circulars.id", ondelete="CASCADE"), index=True
    )
    order_index: Mapped[int] = mapped_column(Integer)
    paragraph_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    heading_path: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    # Estimated from a characters-per-token ratio, not a tokenizer.
    token_count: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    tsv: Mapped[str | None] = mapped_column(TSVECTOR, Computed(_TSV_EXPRESSION, persisted=True))


class Citation(Base):
    """One reference string found in a paragraph, resolved to a circular or not."""

    __tablename__ = "citations"
    __table_args__ = (Index("ix_citations_cited", "cited_circular_id", "resolved"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    citing_circular_id: Mapped[int] = mapped_column(
        ForeignKey("circulars.id", ondelete="CASCADE"), index=True
    )
    citing_paragraph_id: Mapped[int] = mapped_column(
        ForeignKey("paragraphs.id", ondelete="CASCADE"), index=True
    )
    raw_reference: Mapped[str] = mapped_column(Text)
    normalised_reference: Mapped[str | None] = mapped_column(String(255), index=True)
    cited_circular_id: Mapped[int | None] = mapped_column(
        ForeignKey("circulars.id", ondelete="SET NULL")
    )
    resolved: Mapped[bool] = mapped_column(Boolean, index=True, default=False)
    resolution_method: Mapped[ResolutionMethod] = mapped_column(
        db_enum(ResolutionMethod, "resolution_method"), default=ResolutionMethod.UNRESOLVED
    )
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)


class Supersession(Base):
    """An edge asserting that a later circular displaces or modifies an earlier one."""

    __tablename__ = "supersessions"
    __table_args__ = (
        Index("ix_supersessions_superseded", "superseded_circular_id", "effective_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    superseding_circular_id: Mapped[int] = mapped_column(
        ForeignKey("circulars.id", ondelete="CASCADE"), index=True
    )
    # Null when the reference could not be bound to a circular in the corpus.
    superseded_circular_id: Mapped[int | None] = mapped_column(
        ForeignKey("circulars.id", ondelete="SET NULL"), index=True
    )
    raw_reference: Mapped[str] = mapped_column(Text)
    evidence_paragraph_id: Mapped[int | None] = mapped_column(
        ForeignKey("paragraphs.id", ondelete="SET NULL")
    )
    supersession_type: Mapped[SupersessionType] = mapped_column(
        db_enum(SupersessionType, "supersession_type")
    )
    effective_date: Mapped[date | None] = mapped_column(Date, index=True)
    resolved: Mapped[bool] = mapped_column(Boolean, index=True, default=False)


class Obligation(Base):
    __tablename__ = "obligations"
    __table_args__ = (
        CheckConstraint("char_end > char_start", name="ck_obligation_span_ordered"),
        UniqueConstraint("circular_id", "char_start", "char_end", name="uq_obligation_span"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    circular_id: Mapped[int] = mapped_column(
        ForeignKey("circulars.id", ondelete="CASCADE"), index=True
    )
    paragraph_id: Mapped[int] = mapped_column(
        ForeignKey("paragraphs.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    actor: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str | None] = mapped_column(Text)
    deadline: Mapped[str | None] = mapped_column(String(255))
    condition: Mapped[str | None] = mapped_column(Text)
    modality: Mapped[str | None] = mapped_column(String(32))
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    # The LLM extractor's self-reported score, or the rules extractor's fixed
    # 0.55. Neither is calibrated.
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
