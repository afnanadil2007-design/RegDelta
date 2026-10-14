"""Internal policy packs and their numbered clauses.

Clause offsets index the pack's markdown source the same way circular offsets
index ``Circular.full_text``, so evidence on either side resolves identically.
"""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.corpus import EMBEDDING_DIM


class PolicyPack(Base):
    __tablename__ = "policy_packs"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_policy_pack_name_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text)
    source_path: Mapped[str | None] = mapped_column(Text)
    # The shipped pack is fictional; the UI and API must be able to say so.
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PolicyClause(Base):
    __tablename__ = "policy_clauses"
    __table_args__ = (
        CheckConstraint("char_end > char_start", name="ck_clause_span_ordered"),
        UniqueConstraint("policy_pack_id", "clause_number", name="uq_clause_number_per_pack"),
        Index(
            "ix_policy_clauses_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_policy_clauses_tsv", "tsv", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_pack_id: Mapped[int] = mapped_column(
        ForeignKey("policy_packs.id", ondelete="CASCADE"), index=True
    )
    order_index: Mapped[int] = mapped_column(Integer)
    clause_number: Mapped[str] = mapped_column(String(32))
    heading: Mapped[str | None] = mapped_column(Text)
    heading_path: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', text)", persisted=True)
    )
