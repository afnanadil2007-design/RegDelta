"""agent-run atomic step-sequence allocator

Adds ``agent_runs.next_step_seq`` so step numbers can be claimed with an atomic
``UPDATE ... RETURNING`` instead of ``MAX(agent_steps.seq)+1``. Under the
graph's concurrent obligation fan-out, the old read let multiple workers observe
the same max and collide on ``uq_agent_step_seq``; the counter serialises
allocation on the run row instead.

Existing runs are backfilled to their current highest step number so any steps
added to an old run continue past what is already stored rather than colliding.
The ``uq_agent_step_seq`` constraint is deliberately left in place as the
database-level safety net.

Revision ID: 0003_agent_run_seq
Revises: 0002_core_schema
Create Date: 2026-08-16
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_agent_run_seq"
down_revision: Union[str, None] = "0002_core_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("next_step_seq", sa.Integer(), nullable=False, server_default="0"),
    )
    # Backfill so a resumed/old run's next step continues past its stored steps.
    op.execute(
        """
        UPDATE agent_runs AS r
        SET next_step_seq = COALESCE(
            (SELECT MAX(s.seq) FROM agent_steps AS s WHERE s.agent_run_id = r.id),
            0
        )
        """
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "next_step_seq")
