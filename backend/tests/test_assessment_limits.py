"""A whole run stops at each of its hard limits: calls, tokens and wall-clock time.

These drive the real service and graph over the seeded corpus with the
deterministic provider. That provider reports no tokens and answers at once,
so the token and timeout cases wrap its call to report usage or to take time;
the budget, the timeout and the run's final status are the code under test.
The app's own count of provider calls (its ``assessment.finished`` record,
which the smoke run reads) is checked against each cap.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from app.ai.gateway import LLMGateway
from app.core.config import Settings, get_settings
from app.db.models.enums import AssessmentStatus
from app.db.session import get_sessionmaker
from app.repositories.assessments import AssessmentRepository
from app.services.assessment import create_assessment, run_assessment
from evaluation.provider_smoke import finished_calls
from tests.conftest import SeededCorpus

MARGIN_2024 = "SEBI/HO/MIRSD/MIRSD-PoD/CIR/P/2024/17"


def _run(corpus: SeededCorpus, **limits: Any) -> tuple[Any, list[int]]:
    settings: Settings = get_settings().model_copy(update=limits)

    async def go() -> Any:
        run_id = await create_assessment(
            corpus.id_of(MARGIN_2024), corpus.policy_pack_id, settings=settings
        )
        await run_assessment(run_id, settings)
        async with get_sessionmaker()() as session:
            return await AssessmentRepository(session).get_by_run_id(run_id)

    with finished_calls() as calls:
        assessment = asyncio.run(go())
    return assessment, calls


def _wrap_provider(monkeypatch: pytest.MonkeyPatch, *, tokens: int = 0, delay: float = 0) -> None:
    original = LLMGateway._call_deterministic

    def call(prompt: str, *, image_png: bytes | None) -> Any:
        if delay:
            time.sleep(delay)
        answer = original(prompt, image_png=image_png)
        answer.tokens_in = tokens
        return answer

    monkeypatch.setattr(LLMGateway, "_call_deterministic", staticmethod(call))


def test_a_run_stops_at_the_call_cap(corpus: SeededCorpus) -> None:
    assessment, calls = _run(corpus, max_assessment_calls=1)
    assert assessment.status is AssessmentStatus.CAPPED
    assert assessment.error_reason.startswith("Call budget reached: 1 of 1 provider calls.")
    assert calls == [1]


def test_a_run_stops_at_the_token_cap(
    corpus: SeededCorpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    _wrap_provider(monkeypatch, tokens=600)
    uncapped, (all_calls,) = _run(corpus)
    assert uncapped.status is AssessmentStatus.COMPLETED and all_calls > 2

    capped, (calls,) = _run(corpus, max_assessment_tokens=1000)
    assert capped.status is AssessmentStatus.CAPPED
    assert capped.error_reason.startswith("Token budget reached:")
    # Calls already in flight when the cap is crossed complete (workers run
    # in parallel, so how many varies); every later one is refused.
    assert 2 <= calls < all_calls
    assert capped.total_tokens == 600 * calls >= 1000


def test_a_run_stops_at_the_wall_clock_limit(
    corpus: SeededCorpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    _wrap_provider(monkeypatch, delay=1.5)
    assessment, _ = _run(corpus, assessment_timeout_seconds=1)
    assert assessment.status is AssessmentStatus.CAPPED
    assert assessment.error_reason.startswith("Stopped at the 1s wall-clock limit.")
    # Recorded as finished at the limit. Work already running in worker
    # threads (a provider call, a reranking) still completes afterwards.
    assert (assessment.completed_at - assessment.created_at).total_seconds() < 10
