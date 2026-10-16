"""A small, fixed latency benchmark for the search modes the UI offers.

Not an ablation: eight queries (the first four semantic and the first four
identifier queries of the fixed sample manifest), each run once per variant,
interleaved so load drift on a shared laptop falls on every variant alike.
It answers how long a search takes here and now, what the first reranked
search costs after the models load, and what two candidate changes buy:

* ``hybrid``: the default mode in the UI (no reranking);
* ``rerank-50-arrival``: the measured configuration of the 2026-10-15
  ablation (50 candidates, batches in arrival order);
* ``rerank-50-sorted``: the same 50 candidates, batched by length so each
  batch pads less (the scores are the same up to floating-point noise);
* ``rerank-20-sorted``: RETRIEVE_TOP_N=20, the documented speed knob. Its
  hits on these eight queries are reported, but eight queries cannot show
  what it costs in recall; that needs the full sample.

    POSTGRES_DB=regdelta_demo python -m evaluation.bench_rerank --label 2026-10-16-rerank-bench

Uses ``run_eval.run_query``, the path the evaluation measures. Writes rows,
a summary with provenance and the machine's load, and never overwrites an
earlier label.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any

from app.ai.retrieval import reranker
from app.core.config import get_settings
from app.db.models.enums import RetrievalMode
from app.db.session import get_sessionmaker
from evaluation.build_gold_set import read_gold, read_sample
from evaluation.provenance import code_identity, machine, model_revision
from evaluation.run_eval import _numbers, run_query

RESULTS = Path(__file__).resolve().parent / "results" / "latency"
PER_SUBSET = 4
VARIANTS: dict[str, dict[str, Any]] = {
    "hybrid": {"mode": RetrievalMode.HYBRID, "top_n": 50, "sorted": True},
    "rerank-50-arrival": {"mode": RetrievalMode.HYBRID_RERANK, "top_n": 50, "sorted": False},
    "rerank-50-sorted": {"mode": RetrievalMode.HYBRID_RERANK, "top_n": 50, "sorted": True},
    "rerank-20-sorted": {"mode": RetrievalMode.HYBRID_RERANK, "top_n": 20, "sorted": True},
}
WARM_UP_QUERY = "obligations of stock brokers when collecting margin"


def load_now() -> dict[str, Any]:
    """The machine's state, so a latency is never read without its conditions."""
    meminfo = dict(
        (line.split(":")[0], int(line.split()[1]))
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.split(":")[0] in ("MemAvailable", "SwapTotal", "SwapFree")
    )
    containers = subprocess.run(
        ["docker", "ps", "-q"], capture_output=True, text=True, check=False
    ).stdout.split()
    return {
        "loadavg_1_5_15": os.getloadavg(),
        "mem_available_gib": round(meminfo["MemAvailable"] / 1024 / 1024, 2),
        "swap_used_gib": round((meminfo["SwapTotal"] - meminfo["SwapFree"]) / 1024 / 1024, 2),
        "running_containers": len(containers),
    }


def configure(variant: dict[str, Any]) -> None:
    os.environ["RETRIEVE_TOP_N"] = str(variant["top_n"])
    get_settings.cache_clear()
    reranker.SORT_BY_LENGTH = variant["sorted"]


async def bench(label: str) -> int:
    out_dir = RESULTS / label
    if out_dir.exists():
        print(f"{out_dir} exists; choose a new label")
        return 1
    sample = read_sample()
    gold = {q.query_id: q for q in read_gold()}
    chosen = [qid for qid in sample["query_ids"] if qid.startswith("sem-")][:PER_SUBSET] + [
        qid for qid in sample["query_ids"] if qid.startswith("ident-")
    ][:PER_SUBSET]
    queries = [gold[qid] for qid in chosen]
    before = load_now()
    code = code_identity()

    timings: dict[str, float] = {}
    started = time.perf_counter()
    reranker.get_reranker()
    timings["reranker_load_s"] = round(time.perf_counter() - started, 2)
    from app.ai.retrieval.embeddings import get_model

    started = time.perf_counter()
    get_model()
    timings["embedder_load_s"] = round(time.perf_counter() - started, 2)

    rows: list[dict[str, Any]] = []
    async with get_sessionmaker()() as session:
        numbers = await _numbers(session)
        threshold = get_settings().relevance_threshold
        # The first reranked search after the models load: reported apart.
        configure(VARIANTS["rerank-50-arrival"])
        started = time.perf_counter()
        from app.ai.retrieval.pipeline import retrieve
        from app.repositories.search import SearchFilters

        await retrieve(
            session, WARM_UP_QUERY, mode=RetrievalMode.HYBRID_RERANK, filters=SearchFilters()
        )
        timings["first_rerank_after_load_s"] = round(time.perf_counter() - started, 2)

        for query in queries:
            for name, variant in VARIANTS.items():
                configure(variant)
                outcome = await run_query(session, query, variant["mode"], numbers, threshold)
                rows.append(
                    {
                        "variant": name,
                        "query_id": query.query_id,
                        "subset": query.subset,
                        "latency_ms": outcome.latency_ms,
                        "hit_at_10": bool(set(query.relevant) & set(outcome.retrieved)),
                        "retrieved": outcome.retrieved,
                        "top_score": outcome.top_score,
                        "refused": outcome.refused,
                    }
                )
                print(
                    f"{query.query_id:16s} {name:18s} {outcome.latency_ms / 1000:7.2f} s",
                    flush=True,
                )
    after = load_now()

    reference = {r["query_id"]: r for r in rows if r["variant"] == "rerank-50-arrival"}
    summary: dict[str, Any] = {
        "label": label,
        "queries": chosen,
        "timings": timings,
        "variants": {},
    }
    for name, variant in VARIANTS.items():
        mine = [r for r in rows if r["variant"] == name]
        seconds = [r["latency_ms"] / 1000 for r in mine]
        summary["variants"][name] = {
            "mode": variant["mode"].value,
            "retrieve_top_n": variant["top_n"],
            "length_sorted_batches": variant["sorted"],
            "n": len(mine),
            "median_s": round(statistics.median(seconds), 2),
            "min_s": round(min(seconds), 2),
            "max_s": round(max(seconds), 2),
            "hits_at_10": sum(r["hit_at_10"] for r in mine),
            "same_top10_as_measured_config": sum(
                r["retrieved"] == reference[r["query_id"]]["retrieved"] for r in mine
            ),
            "max_top_score_difference": max(
                abs((r["top_score"] or 0) - (reference[r["query_id"]]["top_score"] or 0))
                for r in mine
            )
            if variant["mode"] is RetrievalMode.HYBRID_RERANK
            else None,
        }
    summary["provenance"] = {
        "code": code,
        "database": get_settings().postgres_db,
        "models": {
            "embedding": [
                get_settings().embedding_model,
                model_revision(
                    get_settings().embedding_model, get_settings().embedding_model_revision
                ),
            ],
            "reranker": [
                get_settings().reranker_model,
                model_revision(
                    get_settings().reranker_model, get_settings().reranker_model_revision
                ),
            ],
        },
        "machine": machine(),
        "load_before": before,
        "load_after": after,
        "timing": "wall clock around run_eval.run_query, one process, models loaded before timing",
    }
    out_dir.mkdir(parents=True)
    with (out_dir / "rows.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("timings", "variants")}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Latency of the search modes on 8 fixed queries.")
    parser.add_argument("--label", required=True)
    args = parser.parse_args(argv)
    return asyncio.run(bench(args.label))


if __name__ == "__main__":
    raise SystemExit(main())
