"""Identical reranked searches share one computation.

The real retriever is replaced by a counting stand-in, so these tests run in
milliseconds and need no database; the API tests exercise the real path.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest

from app.ai.retrieval.pipeline import RetrievalResult
from app.db.models.enums import RetrievalMode
from app.repositories.search import SearchFilters
from app.services import search as service

RERANK = RetrievalMode.HYBRID_RERANK


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    seen: list[str] = []

    async def fake_retrieve(session, query, *, mode, filters, top_k):  # noqa: ANN001
        seen.append(query)
        await asyncio.sleep(0.05)
        if query == "fails":
            raise RuntimeError("model unavailable")
        return RetrievalResult(mode=mode, below_threshold=False, top_score=0.9, threshold=0.35)

    monkeypatch.setattr(service, "retrieve", fake_retrieve)
    service._running.clear()
    service._finished.clear()
    yield seen
    service._running.clear()
    service._finished.clear()


def test_concurrent_identical_searches_compute_once(calls: list[str]) -> None:
    async def scenario() -> list[tuple[RetrievalResult, str]]:
        return await asyncio.gather(
            service.shared_rerank("margin rules", RERANK, SearchFilters(), 8),
            service.shared_rerank("margin rules", RERANK, SearchFilters(), 8),
        )

    (first, how_a), (second, how_b) = asyncio.run(scenario())
    assert calls == ["margin rules"]
    assert first is second
    assert {how_a, how_b} == {"computed", "joined"}


def test_a_recent_identical_search_is_reused(calls: list[str]) -> None:
    async def scenario() -> list[str]:
        _, first = await service.shared_rerank("margin rules", RERANK, SearchFilters(), 8)
        _, again = await service.shared_rerank("margin rules", RERANK, SearchFilters(), 8)
        return [first, again]

    assert asyncio.run(scenario()) == ["computed", "reused"]
    assert calls == ["margin rules"]


def test_different_filters_or_cutoffs_are_separate_searches(calls: list[str]) -> None:
    async def scenario() -> None:
        await service.shared_rerank("q", RERANK, SearchFilters(), 8)
        await service.shared_rerank("q", RERANK, SearchFilters(department="CFD"), 8)
        await service.shared_rerank("q", RERANK, SearchFilters(), 20)

    asyncio.run(scenario())
    assert calls == ["q", "q", "q"]


def test_a_waiter_that_goes_away_does_not_cancel_the_shared_work(calls: list[str]) -> None:
    async def scenario() -> str:
        leaving = asyncio.create_task(service.shared_rerank("q", RERANK, SearchFilters(), 8))
        staying = asyncio.create_task(service.shared_rerank("q", RERANK, SearchFilters(), 8))
        await asyncio.sleep(0.01)
        leaving.cancel()
        _, how = await staying
        return how

    assert asyncio.run(scenario()) == "joined"
    assert calls == ["q"]


def test_a_failure_is_not_reused(calls: list[str]) -> None:
    async def scenario() -> None:
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await service.shared_rerank("fails", RERANK, SearchFilters(), 8)

    asyncio.run(scenario())
    assert calls == ["fails", "fails"]


def test_finished_results_are_bounded(calls: list[str]) -> None:
    async def scenario() -> None:
        for i in range(service.SHARED_MAX_ENTRIES + 5):
            await service.shared_rerank(f"q{i}", RERANK, SearchFilters(), 8)

    asyncio.run(scenario())
    assert len(service._finished) == service.SHARED_MAX_ENTRIES
