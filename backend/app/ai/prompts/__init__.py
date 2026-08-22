"""Prompt loading.

Prompts live as markdown files beside this module and are read from disk, never
inlined in Python — so they can be diffed, reviewed, and edited without
touching code.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PROMPT_DIR = Path(__file__).parent


@lru_cache
def load_prompt(name: str) -> str:
    """Load ``<name>.md`` from the prompt directory.

    Raises a clear error naming the file rather than failing deep in a model
    call with an empty prompt.
    """
    path = _PROMPT_DIR / f"{name}.md"
    if not path.is_file():
        available = sorted(p.stem for p in _PROMPT_DIR.glob("*.md"))
        raise FileNotFoundError(
            f"prompt {name!r} not found at {path}. Available prompts: {available}"
        )
    return path.read_text(encoding="utf-8").strip()
