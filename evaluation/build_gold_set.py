"""Mine the synthetic retrieval gold set from the corpus's citation graph.

Each resolved citation gives a (query, relevant circular) pair: the circular
the citing paragraph names is taken as relevant to that paragraph. In this
corpus the citations are written by the generator's templates
(``ingestion/generate_corpus.py``), so these are *template-derived* labels,
not independent human relevance judgements, and every query has exactly one
relevant circular even where a sibling circular of the same topic would also
answer it.

Two subsets stress different behaviour:

* ``semantic``: the citing paragraph's prose with the reference removed.
* ``identifier``: the reference string alone (exact-token matching).

Labels name circulars by number, not by database id, so the file stays valid
for any database built from the same corpus. ``--sample`` additionally writes
a fixed query manifest: every mode of an ablation must read the same one.

    python -m evaluation.build_gold_set
    python -m evaluation.build_gold_set --sample 60
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.db.models.corpus import Circular, Citation, Paragraph
from app.db.session import get_sessionmaker
from evaluation.provenance import file_sha256

DATASET_DIR = Path(__file__).resolve().parent / "datasets" / "synthetic"
GOLD_PATH = DATASET_DIR / "retrieval_gold.jsonl"
SAMPLE_PATH = DATASET_DIR / "retrieval_sample.json"
SAMPLE_SEED = 20261015

# A paragraph shorter than this carries too little signal to be a fair query.
_MIN_QUERY_CHARS = 80


@dataclass(frozen=True)
class GoldQuery:
    query_id: str
    subset: str  # "semantic" | "identifier"
    query: str
    relevant: list[str]  # circular numbers
    citing_circular: str
    citing_paragraph: int  # order_index within the citing circular
    reference: str

    @property
    def citation_key(self) -> str:
        """Both subsets of one citation share this key."""
        return self.query_id.split("-", 1)[1]


def strip_reference(text: str, reference: str) -> str:
    """Remove the reference so the semantic query cannot be solved by exact match."""
    return re.sub(r"\s+", " ", text.replace(reference, " ")).strip()


def _key(citing: str, paragraph: int, reference: str) -> str:
    return hashlib.sha256(f"{citing}|{paragraph}|{reference}".encode()).hexdigest()[:10]


async def build() -> list[GoldQuery]:
    cited = aliased(Circular)
    citing = aliased(Circular)
    stmt = (
        select(
            Citation.raw_reference,
            Paragraph.text,
            Paragraph.order_index,
            citing.circular_number,
            cited.circular_number,
        )
        .join(Paragraph, Paragraph.id == Citation.citing_paragraph_id)
        .join(citing, citing.id == Citation.citing_circular_id)
        .join(cited, cited.id == Citation.cited_circular_id)
        .where(Citation.resolved.is_(True))
        .order_by(citing.circular_number, Paragraph.order_index, Citation.raw_reference)
    )
    queries: list[GoldQuery] = []
    async with get_sessionmaker()() as session:
        for reference, text, order, citing_number, cited_number in (
            await session.execute(stmt)
        ).all():
            key = _key(citing_number, order, reference)
            common = {
                "relevant": [cited_number],
                "citing_circular": citing_number,
                "citing_paragraph": order,
                "reference": reference,
            }
            semantic = strip_reference(text, reference)
            if len(semantic) >= _MIN_QUERY_CHARS:
                queries.append(
                    GoldQuery(query_id=f"sem-{key}", subset="semantic", query=semantic, **common)
                )
            queries.append(
                GoldQuery(query_id=f"ident-{key}", subset="identifier", query=reference, **common)
            )
    return queries


def write_gold(queries: list[GoldQuery], path: Path = GOLD_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for query in queries:
            handle.write(json.dumps(asdict(query), ensure_ascii=False) + "\n")


def read_gold(path: Path = GOLD_PATH) -> list[GoldQuery]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as handle:
        return [GoldQuery(**json.loads(line)) for line in handle if line.strip()]


def write_sample(queries: list[GoldQuery], citations: int, seed: int = SAMPLE_SEED) -> dict:
    """Sample citations (not queries), keeping both subsets of each one."""
    keys = sorted({q.citation_key for q in queries})
    chosen = set(random.Random(seed).sample(keys, min(citations, len(keys))))
    ids = [q.query_id for q in queries if q.citation_key in chosen]
    manifest = {
        "gold_file": GOLD_PATH.name,
        "gold_sha256": file_sha256(GOLD_PATH),
        "seed": seed,
        "selection": (
            "citations drawn uniformly without replacement; both the semantic and the "
            "identifier query of each drawn citation are included"
        ),
        "citations": len(chosen),
        "query_ids": ids,
    }
    SAMPLE_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def read_sample(path: Path = SAMPLE_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


async def _run(sample: int | None) -> int:
    queries = await build()
    if not queries:
        print("No resolved citations: build the corpus and the citation graph first.")
        return 1
    write_gold(queries)
    by_subset = {s: sum(q.subset == s for q in queries) for s in ("semantic", "identifier")}
    print(f"Gold set: {GOLD_PATH} ({len(queries)} queries: {by_subset})")
    if sample:
        manifest = write_sample(queries, sample)
        print(
            f"Sample:   {SAMPLE_PATH} ({manifest['citations']} citations, "
            f"{len(manifest['query_ids'])} queries)"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the synthetic retrieval gold set.")
    parser.add_argument(
        "--sample", type=int, default=None, help="also write a manifest of N sampled citations"
    )
    args = parser.parse_args(argv)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(_run(args.sample))


if __name__ == "__main__":
    raise SystemExit(main())
