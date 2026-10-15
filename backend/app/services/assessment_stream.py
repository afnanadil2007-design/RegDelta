"""The live trace of one assessment, as a sequence of Server-Sent Events.

Protocol (each event's ``data`` is JSON):

* ``snapshot`` — first event on every connection: run status and all steps
  recorded so far. A reconnect therefore resynchronises completely; nothing
  depends on the client's Last-Event-ID.
* ``step`` — a step that is new, or whose status/summary/latency changed since
  it was last sent. Steps are opened RUNNING and closed later, so the same
  ``seq`` is sent again when it finishes; clients upsert by ``seq``.
* ``done`` — the run reached a terminal status; the stream then ends.
* ``error`` — the run does not exist; the stream ends.
* ``timeout`` — the stream's own time limit passed before a terminal status;
  clients should fall back to polling the assessment.

The stream polls ``agent_steps`` instead of holding a session open: the graph
writes steps from concurrent tasks with their own sessions, so polling is
both simpler and safer than a shared listener.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from app.db.models.assessment import AgentStep
from app.db.models.enums import TERMINAL_STATUSES
from app.db.session import get_sessionmaker
from app.repositories.agent_runs import AgentRunRepository
from app.repositories.assessments import AssessmentRepository

# Milliseconds a browser EventSource waits before reconnecting.
RECONNECT_MS = 2000

StepView = Callable[[AgentStep], dict[str, Any]]


def _fingerprint(step: AgentStep) -> tuple[object, ...]:
    return (step.status, step.summary, step.latency_ms, step.error, step.finished_at)


async def trace_events(
    run_id: uuid.UUID,
    *,
    step_view: StepView,
    poll_seconds: float = 0.5,
    timeout_seconds: float = 900.0,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield SSE event dicts (``event``, ``id``, ``data``, ``retry``) for one run."""
    sent: dict[int, tuple[object, ...]] = {}
    event_id = 0
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds

    def event(name: str, payload: Any) -> dict[str, Any]:
        nonlocal event_id
        event_id += 1
        return {
            "event": name,
            "id": str(event_id),
            "retry": RECONNECT_MS,
            "data": json.dumps(payload, default=str),
        }

    while True:
        if is_disconnected is not None and await is_disconnected():
            return

        async with get_sessionmaker()() as session:
            assessment = await AssessmentRepository(session).get_by_run_id(run_id)
            if assessment is None:
                yield event("error", {"message": f"No assessment with run_id {run_id}."})
                return
            runs = AgentRunRepository(session)
            agent_run = await runs.get_for_assessment(assessment.id)
            steps = await runs.list_steps(agent_run.id) if agent_run else []
            status = assessment.status
            detail = assessment.error_reason

        if event_id == 0:
            yield event(
                "snapshot",
                {"status": status.value, "steps": [step_view(s) for s in steps]},
            )
            sent = {s.seq: _fingerprint(s) for s in steps}
        else:
            for step in steps:
                fingerprint = _fingerprint(step)
                if sent.get(step.seq) != fingerprint:
                    sent[step.seq] = fingerprint
                    yield event("step", step_view(step))

        if status in TERMINAL_STATUSES:
            yield event("done", {"status": status.value, "status_detail": detail})
            return
        if loop.time() >= deadline:
            yield event(
                "timeout",
                {"message": "The live trace stopped updating; reload to see the latest state."},
            )
            return
        await asyncio.sleep(poll_seconds)
