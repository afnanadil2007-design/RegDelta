"""Cross-encoder reranking (BAAI/bge-reranker-base, CPU).

A cross-encoder reads the query and the passage *together*, so it can judge
relevance that a bi-encoder's independent embeddings cannot. It is far too
slow to run over the corpus, which is why it only ever sees the fused top-N.

``CrossEncoder.predict`` already applies the model's own activation — for this
single-label model that is a sigmoid — so it returns calibrated 0..1 relevance
probabilities. ``RELEVANCE_THRESHOLD`` is expressed on that scale directly.

Do not add a second sigmoid here. Doing so is monotonic, so ranking (and every
ablation number) looks unaffected, but it compresses the whole range into
(0.5, 0.731) and no score can ever fall below the threshold — which silently
disables refusal entirely. That bug shipped once and was caught only because
the refusal suite measured a 0.000 correct-refusal rate.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

log = get_logger("app.ai.retrieval.reranker")


# Chunks target ~400 tokens, so 512 covers a passage without truncating it.
# Setting it explicitly bounds the worst case: a long passage would otherwise
# quadratically inflate attention cost on CPU.
_MAX_LENGTH = 512
_BATCH_SIZE = 16

_reranker: CrossEncoder | None = None
_reranker_lock = threading.Lock()
# Serialises inference. The graph reranks concurrently and retrieval now runs in
# worker threads, but the model's HuggingFace fast tokenizer is not thread-safe
# — concurrent scoring raises "Already borrowed" from its Rust core. The lock is
# held inside the worker thread, so the event loop stays free either way.
_predict_lock = threading.Lock()


def get_reranker() -> CrossEncoder:
    """Load and cache the cross-encoder once, thread-safely.

    The graph reranks under concurrent fan-out, and retrieval now runs in a
    worker thread, so the first calls can land on several threads at once. A
    plain ``lru_cache`` does not serialise the wrapped body, so concurrent
    first-calls would construct the torch model in parallel and crash with a
    ``NotImplementedError`` from ``.to()``. Double-checked locking guarantees a
    single construction; every later call is a cheap ``is None`` check.
    """
    global _reranker
    if _reranker is None:
        with _reranker_lock:
            if _reranker is None:
                from sentence_transformers import CrossEncoder

                from app.ai.retrieval.embeddings import configure_torch_threads

                configure_torch_threads()
                settings = get_settings()
                log.info("reranker.loading", extra={"model": settings.reranker_model})
                _reranker = CrossEncoder(
                    settings.reranker_model, device="cpu", max_length=_MAX_LENGTH
                )
    return _reranker


def rerank(query: str, passages: list[tuple[int, str]]) -> list[tuple[int, float]]:
    """Score (chunk_id, text) pairs against the query, best first.

    Returns (chunk_id, score) where score is the model's own 0..1 relevance
    probability, directly comparable to ``RELEVANCE_THRESHOLD``.
    """
    if not passages:
        return []

    model = get_reranker()
    pairs = [[query, text] for _, text in passages]
    with _predict_lock:
        scores = model.predict(pairs, batch_size=_BATCH_SIZE, show_progress_bar=False)

    scored = [
        (chunk_id, float(score))
        for (chunk_id, _), score in zip(passages, scores, strict=True)
    ]
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    return scored
