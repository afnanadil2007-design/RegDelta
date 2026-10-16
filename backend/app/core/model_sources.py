"""Where the embedding and reranker models may be loaded from: one Hub id each.

sentence-transformers 3.4.1 (CVE-2026-68770) imports custom Python from a
model directory even with ``trust_remote_code=False``: it treats the
configured name as a local path whenever ``os.path.exists(name)`` holds,
relative to the working directory, and loads module code from it. For a
Hugging Face Hub id at a pinned commit its trust gate does hold. So the only
accepted sources are the two Hub repositories the evaluation measured, each
at its pinned commit and in its own role; a name that a local file,
directory or link shadows is refused; and both loaders pass
``trust_remote_code=False`` explicitly. Settings check the pair at start-up,
and the loaders check again immediately before constructing a model.

This is a mitigation, not a patch: the library remains vulnerable until it is
upgraded (5.6.0). Two assumptions remain. The Hugging Face cache (``HF_HOME``,
by default ``~/.cache/huggingface``) is trusted as it stands: whoever can
write to it can change what a pinned revision loads. And a shadowing path
created between the check and the load, in the instant between them, is not
caught.
"""

from __future__ import annotations

import os
from typing import Literal

Role = Literal["embedding", "reranker"]

APPROVED: dict[Role, tuple[str, str]] = {
    "embedding": ("BAAI/bge-small-en-v1.5", "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"),
    "reranker": ("BAAI/bge-reranker-base", "2cfc18c9415c912f9d8155881c133215df768a70"),
}


class ModelSourceError(RuntimeError):
    """The configured model is not the approved Hub repository at its commit."""


def unapproved(role: Role, model: str, revision: str) -> str | None:
    """Why ``model`` at ``revision`` may not be the ``role`` model, or None."""
    approved_model, approved_revision = APPROVED[role]
    if model != approved_model:
        return (
            f"{model!r} is not the approved {role} model: only the Hugging Face repository "
            f"{approved_model} is loaded (no local paths, URLs or other repositories)"
        )
    if revision != approved_revision:
        return f"{model} is approved only at commit {approved_revision}, not {revision!r}"
    return None


def checked_source(role: Role, model: str, revision: str) -> str:
    """The Hub id to load now, or ModelSourceError if anything would replace it."""
    if reason := unapproved(role, model, revision):
        raise ModelSourceError(reason)
    # The loaders' own test (os.path.exists, relative to the working
    # directory); lexists also catches a link whose target is missing.
    if os.path.lexists(model):
        raise ModelSourceError(
            f"{os.path.abspath(model)} exists and would be loaded instead of the Hub "
            f"repository {model}; remove it or run from another directory"
        )
    return model
