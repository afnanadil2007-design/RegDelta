"""Assessments, their findings, and the persisted agent trace.

An assessment pairs one circular with one policy pack. Its agent run records
every graph-node execution as an ``AgentStep``; the SSE stream and the
evaluation's latency report both read those rows.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    UUID,
    Boolean,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import (
    AnalystDecision,
    AssessmentStatus,
    ImpactType,
    StepStatus,
    db_enum,
)

# Version of the assessment graph topology. Recorded on every run so a trace
# stays interpretable after the graph changes.
DEFAULT_GRAPH_VERSION = "v1"


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Public identifier used in URLs and the SSE stream.
    run_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, index=True, default=uuid.uuid4)
    circular_id: Mapped[int] = mapped_column(
        ForeignKey("circulars.id", ondelete="CASCADE"), index=True
    )
    policy_pack_id: Mapped[int] = mapped_column(
        ForeignKey("policy_packs.id", ondelete="CASCADE"), index=True
    )
    as_of_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[AssessmentStatus] = mapped_column(
        db_enum(AssessmentStatus, "assessment_status"),
        index=True,
        default=AssessmentStatus.PENDING,
    )
    error_reason: Mapped[str | None] = mapped_column(Text)
    memo: Mapped[str | None] = mapped_column(Text)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Finding(Base):
    """One obligation judged against one policy clause (or against none)."""

    __tablename__ = "findings"
    __table_args__ = (Index("ix_findings_assessment_impact", "assessment_id", "impact_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), index=True
    )
    obligation_id: Mapped[int] = mapped_column(
        ForeignKey("obligations.id", ondelete="CASCADE"), index=True
    )
    policy_clause_id: Mapped[int | None] = mapped_column(
        ForeignKey("policy_clauses.id", ondelete="SET NULL"), index=True
    )
    impact_type: Mapped[ImpactType] = mapped_column(db_enum(ImpactType, "impact_type"), index=True)
    rationale: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    # Offsets into Circular.full_text and into the policy pack source.
    circular_span_start: Mapped[int | None] = mapped_column(Integer)
    circular_span_end: Mapped[int | None] = mapped_column(Integer)
    clause_span_start: Mapped[int | None] = mapped_column(Integer)
    clause_span_end: Mapped[int | None] = mapped_column(Integer)
    verified: Mapped[bool] = mapped_column(Boolean, index=True, default=False)
    verification_attempts: Mapped[int] = mapped_column(Integer, default=0)
    analyst_decision: Mapped[AnalystDecision] = mapped_column(
        db_enum(AnalystDecision, "analyst_decision"),
        index=True,
        default=AnalystDecision.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, index=True, default=uuid.uuid4)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), index=True
    )
    graph_version: Mapped[str] = mapped_column(String(32), default=DEFAULT_GRAPH_VERSION)
    status: Mapped[AssessmentStatus] = mapped_column(
        db_enum(AssessmentStatus, "assessment_status"), default=AssessmentStatus.PENDING
    )
    error: Mapped[str | None] = mapped_column(Text)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Last step sequence handed out; claimed atomically with UPDATE … RETURNING
    # (migration 0003) so concurrent workers never collide on uq_agent_step_seq.
    next_step_seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class AgentStep(Base):
    __tablename__ = "agent_steps"
    __table_args__ = (
        UniqueConstraint("agent_run_id", "seq", name="uq_agent_step_seq"),
        Index("ix_agent_steps_run_seq", "agent_run_id", "seq"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    node: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[StepStatus] = mapped_column(
        db_enum(StepStatus, "step_status"), default=StepStatus.RUNNING
    )
    summary: Mapped[str | None] = mapped_column(Text)
    inputs: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    outputs: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
