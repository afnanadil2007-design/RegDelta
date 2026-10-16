"""Only the approved Hub repositories, at their commits, ever reach a model constructor.

sentence-transformers 3.4.1 runs custom code from a local model directory
(app.core.model_sources). These tests stand in for the constructors: a refused
source must fail before any constructor is called, and an approved one must
reach it as the bare Hub id with ``trust_remote_code=False``. The real models
load from the approved source in the retrieval and refusal tests.
"""

from __future__ import annotations

import inspect
import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest
import sentence_transformers
from pydantic import ValidationError

from app.ai.retrieval import embeddings, reranker
from app.core.config import Settings
from app.core.model_sources import APPROVED, ModelSourceError, checked_source

EMBEDDER, EMBEDDER_REVISION = APPROVED["embedding"]
RERANKER, RERANKER_REVISION = APPROVED["reranker"]


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "model",
    [
        "./models/bge-small-en-v1.5",
        "/opt/models/bge-small-en-v1.5",
        "~/bge",
        f"{EMBEDDER}/",
        f"./{EMBEDDER}",
        f"https://huggingface.co/{EMBEDDER}",
        f"hf://{EMBEDDER}",
        EMBEDDER.lower(),
        "sentence-transformers/all-MiniLM-L6-v2",
        RERANKER,  # approved, but not for this role
        "",
    ],
)
def test_settings_refuse_any_other_embedding_source(model: str) -> None:
    with pytest.raises(ValidationError, match="not the approved embedding model"):
        _settings(embedding_model=model)


@pytest.mark.parametrize(
    "revision",
    ["main", "v1.5", EMBEDDER_REVISION[:7], "0" * 40, RERANKER_REVISION, f"{EMBEDDER_REVISION} "],
)
def test_settings_refuse_any_other_revision(revision: str) -> None:
    with pytest.raises(ValidationError, match="approved only at commit"):
        _settings(embedding_model_revision=revision)


def test_settings_refuse_another_reranker(monkeypatch: pytest.MonkeyPatch) -> None:
    """The same check through the environment, the way the app reads it."""
    monkeypatch.setenv("RERANKER_MODEL", "./BAAI/bge-reranker-base")
    with pytest.raises(ValidationError, match="not the approved reranker model"):
        Settings()
    monkeypatch.setenv("RERANKER_MODEL", RERANKER)
    monkeypatch.setenv("RERANKER_MODEL_REVISION", "main")
    with pytest.raises(ValidationError, match="approved only at commit"):
        Settings()


@pytest.fixture
def constructors(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict]:
    """Record what each loader passes to its constructor; load nothing."""
    calls: dict[str, dict] = {}

    def recorder(name: str) -> Callable[..., object]:
        def construct(model: str, **kwargs: object) -> object:
            calls[name] = {"model": model, **kwargs}
            return object()

        return construct

    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", recorder("embedder"))
    monkeypatch.setattr(sentence_transformers, "CrossEncoder", recorder("reranker"))
    monkeypatch.setattr(embeddings, "_model", None)
    monkeypatch.setattr(reranker, "_reranker", None)
    return calls


def test_both_loaders_pass_the_hub_id_pinned_and_without_remote_code(
    constructors: dict[str, dict],
) -> None:
    embeddings.get_model()
    reranker.get_reranker()
    assert constructors["embedder"]["model"] == EMBEDDER
    assert constructors["embedder"]["revision"] == EMBEDDER_REVISION
    assert constructors["reranker"]["model"] == RERANKER
    assert constructors["reranker"]["revision"] == RERANKER_REVISION
    assert constructors["embedder"]["trust_remote_code"] is False
    assert constructors["reranker"]["trust_remote_code"] is False


def test_the_installed_constructors_accept_trust_remote_code() -> None:
    """Passing it explicitly relies on these signatures (sentence-transformers 3.4.1)."""
    for cls in (sentence_transformers.SentenceTransformer, sentence_transformers.CrossEncoder):
        parameter = inspect.signature(cls.__init__).parameters["trust_remote_code"]
        assert parameter.default is False


def _plant_model(root: Path, name: str) -> Path:
    """A model directory under ``name`` that would run code if it were loaded."""
    marker = root / "custom-code-ran"
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "modules.json").write_text(
        json.dumps([{"idx": 0, "name": "0", "path": "", "type": "payload.Hostile"}])
    )
    (directory / "payload.py").write_text(f"open({str(marker)!r}, 'w').write('ran')\n")
    return marker


@pytest.mark.parametrize("loader", ["embedder", "reranker"])
def test_a_local_directory_shadowing_the_hub_name_is_refused(
    constructors: dict[str, dict],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader: str,
) -> None:
    marker = _plant_model(tmp_path, EMBEDDER if loader == "embedder" else RERANKER)
    monkeypatch.chdir(tmp_path)
    load = embeddings.get_model if loader == "embedder" else reranker.get_reranker
    with pytest.raises(ModelSourceError, match="would be loaded instead of the Hub"):
        load()
    assert constructors == {} and not marker.exists()


@pytest.mark.parametrize("kind", ["file", "dangling link"])
def test_any_path_at_the_hub_name_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    shadow = tmp_path / EMBEDDER
    shadow.parent.mkdir(parents=True)
    if kind == "file":
        shadow.write_text("")
    else:
        os.symlink(tmp_path / "missing", shadow)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ModelSourceError, match=str(shadow)):
        checked_source("embedding", EMBEDDER, EMBEDDER_REVISION)


def test_the_loaders_check_again_at_load_time(
    constructors: dict[str, dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Settings that skipped validation still cannot reach a constructor."""
    unvalidated = Settings.model_construct(
        embedding_model="./local-bge",
        embedding_model_revision=EMBEDDER_REVISION,
        reranker_model=RERANKER,
        reranker_model_revision="main",
    )
    monkeypatch.setattr(embeddings, "get_settings", lambda: unvalidated)
    monkeypatch.setattr(reranker, "get_settings", lambda: unvalidated)
    with pytest.raises(ModelSourceError, match="not the approved embedding model"):
        embeddings.get_model()
    with pytest.raises(ModelSourceError, match="approved only at commit"):
        reranker.get_reranker()
    assert constructors == {}


def test_the_hub_name_is_free_where_the_tests_and_tools_run() -> None:
    """The repository and backend/ (the two working directories) shadow nothing."""
    root = Path(__file__).resolve().parents[2]
    for directory in (root, root / "backend"):
        for model, _ in APPROVED.values():
            assert not os.path.lexists(directory / model)
