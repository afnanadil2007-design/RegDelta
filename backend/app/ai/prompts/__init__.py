"""Prompt loading.

Prompts live as markdown files beside this module and are read from disk, never
inlined in Python — so they can be diffed, reviewed, and edited without
touching code.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_PROMPT_DIR = Path(__file__).parent
_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
# The wrapper tags the templates put around untrusted text.
_DATA_TAGS = ("obligation", "policy_clause", "paragraph", "findings", "circular")


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


def render_prompt(name: str, **values: str) -> str:
    """Fill a prompt template's ``{placeholders}`` in a single pass.

    Inserted text is never re-scanned, so a circular that happens to contain
    ``{clause}`` cannot pull other material into the prompt. Circular and
    policy text is untrusted data: a closing wrapper tag inside it (an attempt
    to end the data block early and issue instructions) is broken up so the
    block boundaries stay where the template put them. Such text cannot be
    quoted verbatim, so a judgement relying on it fails verification.
    """
    template = load_prompt(name)

    def fill(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(f"prompt {name!r} needs a value for {{{key}}}")
        return _neutralise_tags(values[key])

    return _PLACEHOLDER.sub(fill, template)


def _neutralise_tags(text: str) -> str:
    for tag in _DATA_TAGS:
        text = re.sub(rf"</\s*{tag}\s*>", f"</ {tag}>", text, flags=re.I)
    return text
