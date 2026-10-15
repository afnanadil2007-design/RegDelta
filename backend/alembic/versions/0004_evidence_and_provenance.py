"""evidence status and provenance

Separates three things the original schema blurred:

* ``findings.verified`` (one boolean) becomes ``findings.quote_status``:
  VERIFIED (every required quote was located in its source), FAILED (a quote
  could not be located within the retry budget; stored so an analyst can see
  the unverified interpretation instead of it vanishing), or NOT_APPLICABLE
  (no model judgement to verify: retrieval found no candidate clause).
* ``findings.confidence`` becomes nullable. Retrieval no-match rows used to
  carry an invented 0.4; no model produced that number, so it is cleared.
* Cost accounting gains ``assessments.unpriced_calls`` and a nullable
  ``agent_steps.cost_usd`` so a model without a list price is reported as
  unknown cost rather than as free.

It also records which provider/model produced an agent run, which extractor
produced an obligation (left NULL — unknown — for existing rows), how many
assessment tasks failed outright, and when an analyst decision was made.

Revision ID: 0004_evidence_provenance
Revises: 0003_agent_run_seq
Create Date: 2026-10-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_evidence_provenance"
down_revision: Union[str, None] = "0003_agent_run_seq"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_QUOTE_STATUS = ("VERIFIED", "FAILED", "NOT_APPLICABLE")


def upgrade() -> None:
    quote_status = postgresql.ENUM(*_QUOTE_STATUS, name="quote_status")
    quote_status.create(op.get_bind())

    op.add_column(
        "findings",
        sa.Column(
            "quote_status",
            postgresql.ENUM(*_QUOTE_STATUS, name="quote_status", create_type=False),
            nullable=True,
        ),
    )
    # A legacy "verified" row with no clause and no quote was a retrieval
    # no-match: nothing was ever quoted, so nothing was verified.
    op.execute(
        """
        UPDATE findings SET quote_status = (CASE
            WHEN verified AND policy_clause_id IS NULL AND circular_span_start IS NULL
                THEN 'NOT_APPLICABLE'
            WHEN verified THEN 'VERIFIED'
            ELSE 'FAILED'
        END)::quote_status
        """
    )
    op.alter_column("findings", "quote_status", nullable=False)
    op.create_index(op.f("ix_findings_quote_status"), "findings", ["quote_status"], unique=False)
    op.drop_index(op.f("ix_findings_verified"), table_name="findings")
    op.drop_column("findings", "verified")

    op.alter_column("findings", "confidence", existing_type=sa.Float(), nullable=True)
    op.execute("UPDATE findings SET confidence = NULL WHERE quote_status = 'NOT_APPLICABLE'")
    op.add_column("findings", sa.Column("verification_note", sa.Text(), nullable=True))
    op.add_column("findings", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("agent_runs", sa.Column("provider", sa.String(length=32), nullable=True))
    op.add_column("agent_runs", sa.Column("model", sa.String(length=128), nullable=True))

    op.add_column(
        "assessments",
        sa.Column("unpriced_calls", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "assessments",
        sa.Column("failed_tasks", sa.Integer(), nullable=False, server_default="0"),
    )

    op.alter_column("agent_steps", "cost_usd", existing_type=sa.Float(), nullable=True)

    op.add_column("obligations", sa.Column("extractor", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("obligations", "extractor")

    op.execute("UPDATE agent_steps SET cost_usd = 0 WHERE cost_usd IS NULL")
    op.alter_column("agent_steps", "cost_usd", existing_type=sa.Float(), nullable=False)

    op.drop_column("assessments", "failed_tasks")
    op.drop_column("assessments", "unpriced_calls")

    op.drop_column("agent_runs", "model")
    op.drop_column("agent_runs", "provider")

    op.drop_column("findings", "decided_at")
    op.drop_column("findings", "verification_note")
    op.execute("UPDATE findings SET confidence = 0 WHERE confidence IS NULL")
    op.alter_column("findings", "confidence", existing_type=sa.Float(), nullable=False)

    op.add_column("findings", sa.Column("verified", sa.Boolean(), nullable=True))
    op.execute("UPDATE findings SET verified = (quote_status <> 'FAILED')")
    op.alter_column("findings", "verified", nullable=False)
    op.create_index(op.f("ix_findings_verified"), "findings", ["verified"], unique=False)
    op.drop_index(op.f("ix_findings_quote_status"), table_name="findings")
    op.drop_column("findings", "quote_status")
    op.execute("DROP TYPE IF EXISTS quote_status")
