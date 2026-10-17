"""The live trace protocol: snapshot, upserts of changed steps, one terminal event.

Regression guard: the stream used to advance past a step the first time it saw
it — while it was still RUNNING — so its completion was never sent and the
live timeline stayed stuck. Steps are now re-sent whenever they change.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import delete, update

from app.db.models.assessment import AgentRun, AgentStep, Assessment
from app.db.models.enums import AssessmentStatus, StepStatus
from app.db.session import get_sessionmaker
from app.routers.assessments import step_out
from app.services.assessment import INTERRUPTED_REASON, recover_interrupted_runs
from app.services.assessment_stream import trace_events
from tests.conftest import SeededCorpus


@pytest_asyncio.fixture
async def live_run(corpus: SeededCorpus) -> AsyncIterator[tuple[uuid.UUID, int, int]]:
    """A RUNNING assessment whose first step is still open. Removed afterwards."""
    async with get_sessionmaker()() as session:
        assessment = Assessment(
            circular_id=next(iter(corpus.circular_ids.values())),
            policy_pack_id=corpus.policy_pack_id,
            status=AssessmentStatus.RUNNING,
        )
        session.add(assessment)
        await session.flush()
        run = AgentRun(
            assessment_id=assessment.id, graph_version="test", status=AssessmentStatus.RUNNING
        )
        session.add(run)
        await session.flush()
        session.add(AgentStep(agent_run_id=run.id, seq=1, node="plan_assessment"))
        await session.commit()
        ids = (assessment.run_id, assessment.id, run.id)
    yield ids
    async with get_sessionmaker()() as session:
        await session.execute(delete(Assessment).where(Assessment.id == ids[1]))
        await session.commit()


def _view(step: AgentStep) -> dict:
    return step_out(step).model_dump(mode="json")


async def _next(events: AsyncIterator[dict]) -> tuple[str, dict]:
    event = await anext(events)
    return event["event"], json.loads(event["data"])


@pytest.mark.asyncio
async def test_a_step_is_resent_when_it_completes(live_run) -> None:
    run_id, assessment_pk, run_pk = live_run
    events = trace_events(run_id, step_view=_view, poll_seconds=0.01)

    name, snapshot = await _next(events)
    assert name == "snapshot"
    assert snapshot["status"] == "RUNNING"
    assert [(s["seq"], s["status"]) for s in snapshot["steps"]] == [(1, "RUNNING")]

    async with get_sessionmaker()() as session:
        await session.execute(
            update(AgentStep)
            .where(AgentStep.agent_run_id == run_pk, AgentStep.seq == 1)
            .values(status=StepStatus.OK, summary="Planned 4", finished_at=datetime.now(UTC))
        )
        session.add(AgentStep(agent_run_id=run_pk, seq=2, node="retrieve_clauses"))
        await session.commit()

    changes = {}
    for _ in range(2):
        name, payload = await _next(events)
        assert name == "step"
        changes[payload["seq"]] = payload["status"]
    assert changes == {1: "OK", 2: "RUNNING"}

    async with get_sessionmaker()() as session:
        await session.execute(
            update(Assessment)
            .where(Assessment.id == assessment_pk)
            .values(status=AssessmentStatus.CAPPED, error_reason="Call budget reached.")
        )
        await session.commit()

    name, done = await _next(events)
    assert name == "done"
    assert done == {"status": "CAPPED", "status_detail": "Call budget reached."}
    with pytest.raises(StopAsyncIteration):
        await anext(events)


@pytest.mark.asyncio
async def test_a_reconnect_resynchronises_from_a_full_snapshot(live_run) -> None:
    run_id, _, _ = live_run
    first = trace_events(run_id, step_view=_view, poll_seconds=0.01)
    second = trace_events(run_id, step_view=_view, poll_seconds=0.01)
    assert (await _next(first))[1] == (await _next(second))[1]


@pytest.mark.asyncio
async def test_event_ids_increase_within_a_connection(live_run) -> None:
    run_id, _, _ = live_run
    events = trace_events(run_id, step_view=_view, poll_seconds=0.01, timeout_seconds=0.05)
    ids = []
    async for event in events:
        ids.append(int(event["id"]))
        assert event["retry"] > 0
    assert ids == sorted(ids) and len(ids) == len(set(ids))


@pytest.mark.asyncio
async def test_the_stream_times_out_with_an_explicit_event(live_run) -> None:
    run_id, _, _ = live_run
    names = [
        e["event"]
        async for e in trace_events(
            run_id, step_view=_view, poll_seconds=0.01, timeout_seconds=0.05
        )
    ]
    assert names[0] == "snapshot"
    assert names[-1] == "timeout"


@pytest.mark.asyncio
async def test_a_disconnected_client_ends_the_stream(live_run) -> None:
    run_id, _, _ = live_run

    async def gone() -> bool:
        return True

    events = [e async for e in trace_events(run_id, step_view=_view, is_disconnected=gone)]
    assert events == []


@pytest.mark.asyncio
async def test_runs_left_running_by_a_dead_process_are_failed_on_startup(live_run) -> None:
    run_id, assessment_pk, run_pk = live_run
    assert await recover_interrupted_runs() >= 1

    async with get_sessionmaker()() as session:
        assessment = await session.get(Assessment, assessment_pk)
        run = await session.get(AgentRun, run_pk)
        step = await session.get(AgentStep, (await _step_id(session, run_pk)))
    assert assessment.status is AssessmentStatus.FAILED
    assert assessment.error_reason == INTERRUPTED_REASON
    assert assessment.completed_at is not None
    assert run.status is AssessmentStatus.FAILED
    assert step.status is StepStatus.ERROR


async def _step_id(session, run_pk: int) -> int:  # type: ignore[no-untyped-def]
    from sqlalchemy import select

    return (
        await session.execute(select(AgentStep.id).where(AgentStep.agent_run_id == run_pk))
    ).scalar_one()
