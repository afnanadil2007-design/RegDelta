"""Regression tests for the atomic agent-step sequence allocator.

The assessment graph fans obligations out concurrently, so step numbers cannot
be derived from ``MAX(agent_steps.seq)+1`` — concurrent workers would read the
same max and collide on ``uq_agent_step_seq``. These tests reproduce that
fan-out against a live database and prove the allocator hands every concurrent
caller a distinct, monotonically increasing value.

They need PostgreSQL (the atomicity is a property of the row lock, not
reproducible in memory) and skip cleanly when it is unreachable, matching the
rest of the integration suite.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.ai.graph.tracing import Tracer
from app.db.models.assessment import AgentRun, AgentStep, Assessment
from app.db.models.corpus import Circular
from app.db.models.enums import AssessmentStatus
from app.db.models.policy import PolicyPack
from app.db.session import get_sessionmaker
from app.repositories.agent_runs import AgentRunRepository


@pytest_asyncio.fixture
async def agent_run_id(migrated_database: str) -> int:
    """A throwaway circular, pack, assessment and agent run, torn down afterwards.

    Uses its own committed sessions (not the transactional fixture) because the
    whole point is cross-session concurrency: each worker commits independently.
    It creates its own parent rows so the test never depends on a seeded corpus.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        circular = Circular(
            circular_number=f"TEST/CONCURRENCY/{uuid.uuid4().hex[:12]}",
            title="Concurrency fixture",
            full_text="Fixture text.",
        )
        pack = PolicyPack(name=f"concurrency-{uuid.uuid4().hex[:12]}", version="1")
        session.add_all([circular, pack])
        await session.flush()
        assessment = Assessment(
            circular_id=circular.id,
            policy_pack_id=pack.id,
            status=AssessmentStatus.PENDING,
        )
        session.add(assessment)
        await session.flush()
        run = AgentRun(
            assessment_id=assessment.id, graph_version="test", status=AssessmentStatus.RUNNING
        )
        session.add(run)
        await session.flush()
        run_pk = run.id
        circular_pk, pack_pk = circular.id, pack.id
        await session.commit()

    yield run_pk

    async with sessionmaker() as session:
        # Deleting the parents cascades to the assessment, run, and steps.
        await session.execute(delete(Circular).where(Circular.id == circular_pk))
        await session.execute(delete(PolicyPack).where(PolicyPack.id == pack_pk))
        await session.commit()


_CONCURRENCY = 25


async def _allocate_once(run_pk: int) -> int:
    async with get_sessionmaker()() as session:
        seq = await AgentRunRepository(session).allocate_seq(run_pk)
        await session.commit()
        return seq


@pytest.mark.asyncio
async def test_concurrent_allocation_yields_unique_sequences(agent_run_id: int) -> None:
    seqs = await asyncio.gather(*(_allocate_once(agent_run_id) for _ in range(_CONCURRENCY)))

    # No duplicates: the core property the old MAX(seq)+1 read violated.
    assert len(set(seqs)) == _CONCURRENCY, f"duplicate sequences allocated: {sorted(seqs)}"
    # First allocation is 1 and the set is exactly 1..N — dense, unique, ordered.
    assert sorted(seqs) == list(range(1, _CONCURRENCY + 1))
    assert min(seqs) == 1
    assert max(seqs) == _CONCURRENCY


@pytest.mark.asyncio
async def test_concurrent_step_persistence_has_no_collisions(agent_run_id: int) -> None:
    """Reproduce the real fan-out: many workers open a step on the same run."""

    async def open_step(node: str) -> None:
        tracer = Tracer(agent_run_id)
        async with tracer.step(node, {"n": node}) as record:
            record.summary = f"did {node}"

    # Concurrent step opens/closes must not raise UniqueViolation on
    # uq_agent_step_seq — the constraint stays intact as the final safety net.
    await asyncio.gather(*(open_step(f"node_{i}") for i in range(_CONCURRENCY)))

    async with get_sessionmaker()() as session:
        rows = (
            (
                await session.execute(
                    select(AgentStep.seq).where(AgentStep.agent_run_id == agent_run_id)
                )
            )
            .scalars()
            .all()
        )

    assert len(rows) == _CONCURRENCY
    # Every persisted step belongs to this run and carries a unique sequence.
    assert len(set(rows)) == _CONCURRENCY
    assert sorted(rows) == list(range(1, _CONCURRENCY + 1))


@pytest.mark.asyncio
async def test_unique_constraint_still_enforced(agent_run_id: int) -> None:
    """The DB-level guard must remain: two steps at the same seq must fail."""
    from sqlalchemy.exc import IntegrityError

    async with get_sessionmaker()() as session:
        session.add(AgentStep(agent_run_id=agent_run_id, seq=1, node="a"))
        session.add(AgentStep(agent_run_id=agent_run_id, seq=1, node="b"))
        with pytest.raises(IntegrityError):
            await session.commit()
