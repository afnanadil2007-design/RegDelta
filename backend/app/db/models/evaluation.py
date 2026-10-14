"""Evaluation runs and their metric values."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import UUID, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import EvalSuite, RetrievalMode, db_enum


class EvalRun(Base):
    __tablename__ = "eval_runs"
    __table_args__ = (Index("ix_eval_runs_suite_started", "suite", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, index=True, default=uuid.uuid4)
    suite: Mapped[EvalSuite] = mapped_column(db_enum(EvalSuite, "eval_suite"), index=True)
    git_sha: Mapped[str] = mapped_column(String(40), index=True)
    mode: Mapped[RetrievalMode | None] = mapped_column(db_enum(RetrievalMode, "retrieval_mode"))
    dataset: Mapped[str | None] = mapped_column(String(255))
    config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvalResult(Base):
    __tablename__ = "eval_results"
    __table_args__ = (Index("ix_eval_results_metric", "eval_run_id", "metric_name", "subset"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    eval_run_id: Mapped[int] = mapped_column(
        ForeignKey("eval_runs.id", ondelete="CASCADE"), index=True
    )
    metric_name: Mapped[str] = mapped_column(String(64))
    metric_value: Mapped[float] = mapped_column(Float)
    subset: Mapped[str | None] = mapped_column(String(32))
    k: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
