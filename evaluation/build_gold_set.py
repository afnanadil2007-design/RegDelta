"""Mine a retrieval gold set from the corpus's own citation graph.

THE IDEA
--------
A resolved citation is a human-authored relevance judgement: the author of
circular A, writing paragraph P, decided circular B was relevant enough to
cite. That gives labelled (query, relevant-document) pairs for free, at corpus
scale, with no annotation budget and no LLM in the loop.

Two subsets, because they stress different retrieval behaviour:

* **semantic** — the query is the *citing paragraph's prose*, with the
  reference string stripped out. Answering it requires understanding what the
  paragraph is about. This is what dense retrieval should win.
* **identifier** — the query is the *raw reference string* alone. Answering it
  requires exact-token matching. This is what lexical retrieval should win.

Reporting them separately is the point: a single blended number would hide the
fact that either retriever alone fails half the workload.

    python -m evaluation.build_gold_set
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import select

from app.db.models.corpus import Chunk, Citation, Paragraph
from app.db.session import get_sessionmaker

DATASET_DIR = Path(__file__).resolve().parent / "datasets"
GOLD_PATH = DATASET_DIR / "gold_retrieval.jsonl"

# A paragraph shorter than this carries too little signal to be a fair query.
_MIN_QUERY_CHARS = 80


@dataclass
class GoldPair:
    query_id: str
    query: str
    subset: str  # "semantic" | "identifier"
    relevant_circular_id: int
    relevant_chunk_ids: list[int]
    citing_circular_id: int
    citing_paragraph_id: int


def strip_reference(text: str, reference: str) -> str:
    """Remove the reference string so the semantic query cannot cheat.

    Without this the 'semantic' subset would be solvable by exact match on the
    identifier, and dense-vs-lexical comparison would be meaningless.
    """
    cleaned = text.replace(reference, " ")
    return re.sub(r"\s+", " ", cleaned).strip()


async def build(limit: int | None = None) -> list[GoldPair]:
    pairs: list[GoldPair] = []

    async with get_sessionmaker()() as session:
        stmt = (
            select(Citation, Paragraph)
            .join(Paragraph, Paragraph.id == Citation.citing_paragraph_id)
            .where(Citation.resolved.is_(True), Citation.cited_circular_id.is_not(None))
            .order_by(Citation.id)
        )
        rows = (await session.execute(stmt)).all()

        # Chunks of the cited circular are the relevant set for that citation.
        chunk_stmt = select(Chunk.id, Chunk.circular_id)
        chunks_by_circular: dict[int, list[int]] = {}
        for chunk_id, circular_id in (await session.execute(chunk_stmt)).all():
            chunks_by_circular.setdefault(circular_id, []).append(chunk_id)

        for citation, paragraph in rows:
            target = citation.cited_circular_id
            relevant = chunks_by_circular.get(target, [])
            if not relevant:
                continue

            semantic_query = strip_reference(paragraph.text, citation.raw_reference)
            if len(semantic_query) >= _MIN_QUERY_CHARS:
                pairs.append(
                    GoldPair(
                        query_id=f"sem-{citation.id}",
                        query=semantic_query,
                        subset="semantic",
                        relevant_circular_id=target,
                        relevant_chunk_ids=relevant,
                        citing_circular_id=citation.citing_circular_id,
                        citing_paragraph_id=paragraph.id,
                    )
                )

            pairs.append(
                GoldPair(
                    query_id=f"ident-{citation.id}",
                    query=citation.raw_reference,
                    subset="identifier",
                    relevant_circular_id=target,
                    relevant_chunk_ids=relevant,
                    citing_circular_id=citation.citing_circular_id,
                    citing_paragraph_id=paragraph.id,
                )
            )

    return pairs[:limit] if limit else pairs


def write_gold(pairs: list[GoldPair], path: Path = GOLD_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for pair in pairs:
            handle.write(json.dumps(asdict(pair), ensure_ascii=False) + "\n")


def read_gold(path: Path = GOLD_PATH) -> list[GoldPair]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as handle:
        return [GoldPair(**json.loads(line)) for line in handle if line.strip()]


async def _run(limit: int | None) -> int:
    pairs = await build(limit)
    write_gold(pairs)

    semantic = sum(1 for p in pairs if p.subset == "semantic")
    identifier = sum(1 for p in pairs if p.subset == "identifier")
    print(f"Gold set written to {GOLD_PATH}")
    print(f"  total      {len(pairs)}")
    print(f"  semantic   {semantic}")
    print(f"  identifier {identifier}")
    if len(pairs) < 300:
        print(f"  WARNING: fewer than the 300 pairs the brief targets ({len(pairs)}).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the retrieval gold set.")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(_run(args.limit))


if __name__ == "__main__":
    raise SystemExit(main())
