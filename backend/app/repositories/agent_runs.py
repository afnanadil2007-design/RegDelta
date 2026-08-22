"""Agent run and step persistence.

Steps are written as the graph executes and read back by the SSE stream, so
``list_steps_after`` supports incremental polling by sequence number.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.assessment import AgentRun, AgentStep
from app.db.models.enums import AssessmentStatus, StepStatus


class AgentRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, run: AgentRun) -> AgentRun:
        self.session.add(run)
        await self.session.flush()
        return run

    async def get(self, run_pk: int) -> AgentRun | None:
        return await self.session.get(AgentRun, run_pk)

    async def get_by_run_id(self, run_id: uuid.UUID) -> AgentRun | None:
        stmt = select(AgentRun).where(AgentRun.run_id == run_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_for_assessment(self, assessment_id: int) -> AgentRun | None:
        stmt = (
            select(AgentRun)
            .where(AgentRun.assessment_id == assessment_id)
            .order_by(AgentRun.started_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def finish(
        self, run_pk: int, status: AssessmentStatus, *, error: str | None = None
    ) -> None:
        run = await self.session.get(AgentRun, run_pk)
        if run is None:
            return
        run.status = status
        run.error = error
        run.finished_at = datetime.now(UTC)
        await self.session.flush()

    # --- steps -------------------------------------------------------------

    async def allocate_seq(self, run_pk: int) -> int:
        """Atomically claim the next step sequence for a run.

        ``UPDATE agent_runs SET next_step_seq = next_step_seq + 1 ... RETURNING``
        runs under a row lock, so concurrent fan-out workers each receive a
        distinct, monotonically increasing value. This replaces the old
        ``MAX(seq)+1`` read, which let concurrent callers observe the same max
        and collide on ``uq_agent_step_seq``. The first allocation returns 1.

        The caller must commit so the increment persists and the row lock is
        released for the next allocator.
        """
        stmt = (
            update(AgentRun)
            .where(AgentRun.id == run_pk)
            .values(next_step_seq=AgentRun.next_step_seq + 1)
            .returning(AgentRun.next_step_seq)
        )
        seq = (await self.session.execute(stmt)).scalar_one()
        return int(seq)

    async def add_step(self, step: AgentStep) -> AgentStep:
        self.session.add(step)
        await self.session.flush()
        return step

    async def complete_step(
        self,
        step_id: int,
        *,
        status: StepStatus,
        summary: str | None = None,
        outputs: dict | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
        latency_ms: int | None = None,
        error: str | None = None,
    ) -> AgentStep | None:
        step = await self.session.get(AgentStep, step_id)
        if step is None:
            return None
        step.status = status
        step.summary = summary
        step.outputs = outputs
        step.tokens_in = tokens_in
        step.tokens_out = tokens_out
        step.cost_usd = cost_usd
        step.latency_ms = latency_ms
        step.error = error
        step.finished_at = datetime.now(UTC)
        await self.session.flush()
        return step

    async def list_steps(self, run_pk: int) -> list[AgentStep]:
        stmt = select(AgentStep).where(AgentStep.agent_run_id == run_pk).order_by(AgentStep.seq)
        return list((await self.session.execute(stmt)).scalars())

    async def list_steps_after(self, run_pk: int, after_seq: int) -> list[AgentStep]:
        """Incremental read for the SSE stream."""
        stmt = (
            select(AgentStep)
            .where(AgentStep.agent_run_id == run_pk, AgentStep.seq > after_seq)
            .order_by(AgentStep.seq)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def node_latency_breakdown(self, run_pk: int) -> dict[str, tuple[int, float]]:
        """(count, mean latency_ms) per node — feeds the cost/latency report."""
        stmt = (
            select(AgentStep.node, func.count(AgentStep.id), func.avg(AgentStep.latency_ms))
            .where(AgentStep.agent_run_id == run_pk)
            .group_by(AgentStep.node)
        )
        rows = (await self.session.execute(stmt)).all()
        return {r[0]: (int(r[1]), float(r[2] or 0.0)) for r in rows}
