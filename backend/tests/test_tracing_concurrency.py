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

import pytest
import pytest_asyncio
from app.db.models.assessment import AgentRun, AgentStep, Assessment
from app.db.models.enums import AssessmentStatus
from sqlalchemy import select, text

from app.ai.graph.tracing import Tracer
from app.db.session import get_engine, get_sessionmaker
from app.repositories.agent_runs import AgentRunRepository


@pytest.fixture(autouse=True)
def _fresh_engine() -> None:
    """Rebuild the async engine on each test's event loop.

    pytest-asyncio gives every test its own loop, but the process-global engine
    binds its connection pool to whichever loop first touches it. Concurrent
    cross-session work here would then hit "bound to a different event loop", so
    we reset the globals and let ``get_engine`` rebuild on the current loop.
    """
    import app.db.session as db_session

    db_session._engine = None
    db_session._sessionmaker = None
    yield
    db_session._engine = None
    db_session._sessionmaker = None


async def _database_available() -> bool:
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest_asyncio.fixture
async def agent_run_id() -> int:
    """A throwaway assessment + agent run, torn down afterwards.

    Uses its own committed sessions (not the transactional fixture) because the
    whole point is cross-session concurrency: each worker commits independently.
    """
    if not await _database_available():
        pytest.skip("PostgreSQL not reachable — concurrency test skipped")

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        # Reuse whatever circular/policy pack the seeded corpus provides; the FK
        # targets just need to exist. Fall back to skipping if the corpus is empty.
        circular_id = (
            await session.execute(text("SELECT id FROM circulars ORDER BY id LIMIT 1"))
        ).scalar_one_or_none()
        pack_id = (
            await session.execute(text("SELECT id FROM policy_packs ORDER BY id LIMIT 1"))
        ).scalar_one_or_none()
        if circular_id is None or pack_id is None:
            pytest.skip("corpus not seeded — concurrency test skipped")

        assessment = Assessment(
            circular_id=circular_id,
            policy_pack_id=pack_id,
            status=AssessmentStatus.PENDING,
        )
        session.add(assessment)
        await session.flush()
        run = AgentRun(assessment_id=assessment.id, status=AssessmentStatus.RUNNING)
        session.add(run)
        await session.flush()
        run_pk = run.id
        assessment_pk = assessment.id
        await session.commit()

    yield run_pk

    async with sessionmaker() as session:
        # Cascade deletes the run and its steps.
        obj = await session.get(Assessment, assessment_pk)
        if obj is not None:
            await session.delete(obj)
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
            await session.execute(
                select(AgentStep.seq).where(AgentStep.agent_run_id == agent_run_id)
            )
        ).scalars().all()

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
