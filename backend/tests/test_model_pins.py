"""The models are pinned to the revisions the evaluation measured.

Without a pin a fresh download (a new container, CI) would load whatever the
upstream repository holds that day: different weights from the measured ones,
or a revision nobody reviewed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import sentence_transformers

from app.ai.retrieval import embeddings, reranker
from app.core.config import Settings

ABLATION = Path(__file__).resolve().parents[2] / "evaluation/results/retrieval/2026-10-15-ablation"


def test_the_pins_are_commits_and_match_the_measured_ablation() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    measured = json.loads((ABLATION / "summary.json").read_text())["provenance"]["models"]
    for pinned, model in (
        (settings.embedding_model_revision, measured["embedding"]),
        (settings.reranker_model_revision, measured["reranker"]),
    ):
        assert re.fullmatch(r"[0-9a-f]{40}", pinned)
        assert pinned == model["revision"]


def test_both_loaders_ask_for_the_pinned_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, dict] = {}

    def recorder(name: str):  # noqa: ANN202
        def construct(model: str, **kwargs: object) -> object:
            calls[name] = {"model": model, **kwargs}
            return object()

        return construct

    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", recorder("embedder"))
    monkeypatch.setattr(sentence_transformers, "CrossEncoder", recorder("reranker"))
    monkeypatch.setattr(embeddings, "_model", None)
    monkeypatch.setattr(reranker, "_reranker", None)

    embeddings.get_model()
    reranker.get_reranker()

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert calls["embedder"]["revision"] == settings.embedding_model_revision
    assert calls["reranker"]["revision"] == settings.reranker_model_revision
