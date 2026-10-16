"""The models are pinned to the revisions the evaluation measured.

Without a pin a fresh download (a new container, CI) would load whatever the
upstream repository holds that day: different weights from the measured ones,
or a revision nobody reviewed. What the loaders pass to their constructors is
tested in ``test_model_sources``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

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
