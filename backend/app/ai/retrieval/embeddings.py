"""Embedding model access (BAAI/bge-small-en-v1.5, 384-d, CPU).

The model is loaded once per process and cached: loading costs seconds, and
ingestion and retrieval both need it. Queries and documents are embedded with
the same model, but bge asks for a query-side instruction prefix — omitting it
measurably degrades retrieval, so ``embed_query`` applies it and
``embed_documents`` does not.
"""

from __future__ import annotations

import threading
from functools import lru_cache
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

log = get_logger("app.ai.retrieval.embeddings")

# The instruction prefix bge-v1.5 was trained with on the query side.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def configure_torch_threads() -> int:
    """Let torch use every core.

    Torch defaults to roughly half the available cores, which on a small CPU
    box costs a measured ~35% of reranking throughput. Called once from each
    model loader.
    """
    import os

    import torch

    threads = os.cpu_count() or 1
    torch.set_num_threads(threads)
    log.info("torch.threads_configured", extra={"threads": threads})
    return threads


_model: SentenceTransformer | None = None
_model_lock = threading.Lock()
# Serialises inference: concurrent searches now embed queries in worker threads,
# and the HuggingFace fast tokenizer is not thread-safe ("Already borrowed").
# See reranker._predict_lock for the same reasoning.
_encode_lock = threading.Lock()


def get_model() -> SentenceTransformer:
    """Load and cache the embedding model once, thread-safely.

    Retrieval runs in a worker thread now, so concurrent first-calls are
    possible. Double-checked locking guarantees a single construction — a plain
    ``lru_cache`` would let parallel first-calls build the torch model at once
    and crash. See ``reranker.get_reranker`` for the same pattern and why.
    """
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                configure_torch_threads()
                settings = get_settings()
                log.info("embeddings.loading", extra={"model": settings.embedding_model})
                _model = SentenceTransformer(settings.embedding_model, device="cpu")
    return _model


def embed_documents(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Embed passages for storage. Normalised, so cosine == dot product."""
    if not texts:
        return []
    model = get_model()
    with _encode_lock:
        vectors = model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
    return [v.tolist() for v in vectors]


def embed_query(text: str) -> list[float]:
    """Embed one query, with the bge query instruction prefix applied."""
    model = get_model()
    with _encode_lock:
        vector = model.encode(
            QUERY_PREFIX + text,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
    return vector.tolist()
