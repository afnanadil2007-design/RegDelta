"""Persist every graph node execution to ``agent_steps``.

This is a product feature, not debug logging: the table drives the live agent
timeline in the UI and the per-node latency/cost breakdown in the evaluation
report. Each node opens a step on entry and closes it on exit — including on
failure, so an errored node is visible in the timeline rather than absent.

The tracer owns its own session. Nodes run concurrently under LangGraph's
fan-out, and sharing one ``AsyncSession`` across concurrent tasks corrupts its
state; a short-lived session per write is the safe shape.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger
from app.db.models.assessment import AgentStep
from app.db.models.enums import StepStatus
from app.db.session import get_sessionmaker
from app.repositories.agent_runs import AgentRunRepository

log = get_logger("app.ai.graph.tracing")

# JSONB payloads are for humans reading a timeline; long text is truncated so
# a step row stays readable and the table stays small.
_MAX_FIELD = 2000


def _trim(value: Any) -> Any:
    if isinstance(value, str) and len(value) > _MAX_FIELD:
        return value[:_MAX_FIELD] + f"… (+{len(value) - _MAX_FIELD} chars)"
    if isinstance(value, dict):
        return {k: _trim(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_trim(v) for v in value[:20]]
    return value


@dataclass
class StepRecord:
    """Mutable handle a node uses to report what it did."""

    step_id: int
    summary: str | None = None
    outputs: dict[str, Any] = field(default_factory=dict)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


class Tracer:
    """Writes agent steps for one agent run."""

    def __init__(self, agent_run_id: int) -> None:
        self.agent_run_id = agent_run_id

    async def _next_seq(self) -> int:
        # Atomic per-run allocation: commit immediately so the increment
        # persists and the row lock is released before the next concurrent
        # worker allocates. See AgentRunRepository.allocate_seq.
        async with get_sessionmaker()() as session:
            seq = await AgentRunRepository(session).allocate_seq(self.agent_run_id)
            await session.commit()
            return seq

    @asynccontextmanager
    async def step(
        self, node: str, inputs: dict[str, Any] | None = None
    ) -> AsyncIterator[StepRecord]:
        """Open a step, yield a handle, and close it on exit or error."""
        seq = await self._next_seq()
        started = time.perf_counter()

        async with get_sessionmaker()() as session:
            step = await AgentRunRepository(session).add_step(
                AgentStep(
                    agent_run_id=self.agent_run_id,
                    seq=seq,
                    node=node,
                    status=StepStatus.RUNNING,
                    inputs=_trim(inputs or {}),
                )
            )
            await session.commit()
            record = StepRecord(step_id=step.id)

        status = StepStatus.OK
        error: str | None = None
        try:
            yield record
        except Exception as exc:  # noqa: BLE001 - the trace must record failures
            status = StepStatus.ERROR
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            latency_ms = int((time.perf_counter() - started) * 1000)
            async with get_sessionmaker()() as session:
                await AgentRunRepository(session).complete_step(
                    record.step_id,
                    status=status,
                    summary=record.summary,
                    outputs=_trim(record.outputs),
                    tokens_in=record.tokens_in,
                    tokens_out=record.tokens_out,
                    cost_usd=record.cost_usd,
                    latency_ms=latency_ms,
                    error=error,
                )
                await session.commit()
            log.info(
                "graph.step",
                extra={
                    "node": node,
                    "seq": seq,
                    "status": status.value,
                    "latency_ms": latency_ms,
                    "tokens": record.tokens_in + record.tokens_out,
                },
            )
