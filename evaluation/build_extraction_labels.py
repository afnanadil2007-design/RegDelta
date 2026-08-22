"""Build the obligation label set for 30 circulars.

HOW THESE LABELS ARE PRODUCED, AND WHAT THAT MEANS
--------------------------------------------------
The brief calls for 30 *hand-labelled* circulars. On a real corpus that is a
person reading PDFs. On this synthetic corpus there is a better source of
truth available: the generator knows exactly which sentences it emitted as
obligations, because it composed them from a fixed template list, and which
sentences are recitals, citations, or supersession language.

So the labels here are **derived from the generator's own ground truth** — the
obligation templates it planted — rather than from a human reading the output.
That is genuinely correct for this corpus and requires no annotation budget,
but it has one honest limitation worth stating plainly:

    These labels test whether extraction finds the obligations that were
    deliberately planted. They cannot test judgement on genuinely ambiguous
    sentences, because the generator does not produce any.

On a real corpus this script must be replaced by human annotation. The
metric (`evaluation/metrics/extraction.py`) is unchanged either way; only the
label source differs.

    python -m evaluation.build_extraction_labels
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

from app.db.session import get_sessionmaker
from app.repositories.circulars import CircularRepository
from evaluation.metrics.extraction import DATASET, LabelledObligation
from ingestion.generate_corpus import TOPICS

# The templates the generator plants as obligations, with their placeholders
# turned into a match pattern. Anything not matching one of these is not an
# obligation, by construction.
_OBLIGATION_PATTERNS = [
    re.compile(re.escape(template).replace(r"\{n\}", r"\d+"))
    for topic in TOPICS
    for template in topic.obligations
]

# The actor is the sentence's leading noun phrase, before the modality.
_ACTOR = re.compile(r"^(?P<actor>.{3,60}?)\s+(?:shall|must|may|should)\b")


def _actor_of(sentence: str) -> str:
    match = _ACTOR.match(sentence)
    return match.group("actor").strip() if match else ""


def label_circular(circular_number: str, full_text: str) -> list[LabelledObligation]:
    """Find every planted obligation sentence and record its true span."""
    labels: list[LabelledObligation] = []
    for pattern in _OBLIGATION_PATTERNS:
        for match in pattern.finditer(full_text):
            sentence = match.group(0)
            actor = _actor_of(sentence)
            if not actor:
                continue
            labels.append(
                LabelledObligation(
                    circular_number=circular_number,
                    text=sentence,
                    actor=actor,
                    char_start=match.start(),
                    char_end=match.end(),
                )
            )
    return sorted(labels, key=lambda label: label.char_start)


async def build(count: int) -> list[LabelledObligation]:
    async with get_sessionmaker()() as session:
        circulars = await CircularRepository(session).list_circulars(limit=count)
        labels: list[LabelledObligation] = []
        for circular in circulars:
            labels.extend(label_circular(circular.circular_number, circular.full_text))
        return labels


async def _run(count: int, path: Path) -> int:
    labels = await build(count)
    if not labels:
        print("No labels produced — is the corpus ingested? Run `make seed`.")
        return 1

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for label in labels:
            handle.write(json.dumps(asdict(label), ensure_ascii=False) + "\n")

    circulars = len({label.circular_number for label in labels})
    print(f"Wrote {len(labels)} labels across {circulars} circulars to {path}")
    print("Labels are derived from the generator's ground truth — see the module docstring.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build obligation labels.")
    parser.add_argument("--count", type=int, default=30, help="circulars to label")
    parser.add_argument("--out", type=Path, default=DATASET)
    args = parser.parse_args(argv)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(_run(args.count, args.out))


if __name__ == "__main__":
    raise SystemExit(main())
