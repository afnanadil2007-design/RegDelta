"""Retrieval evaluation: the four modes over one fixed query manifest.

Every mode runs through the same ``retrieve()`` the API uses, over the same
query ids (``datasets/synthetic/retrieval_sample.json``), with the threshold
not applied so ranking and refusal are measured from one run. The circular a
query was taken from is removed from its ranking: its own text trivially
contains the query, and it is never the cited (relevant) circular.

Outputs, under ``results/retrieval/<label>/``:

* ``per_query.jsonl``: one row per (mode, query), the raw material;
* ``summary.json``: metrics with intervals, paired comparisons, error
  examples, and the provenance block (code, models, data, machine).

``python -m evaluation.report`` turns a summary into the tables in
docs/evaluation.md; ``--persist`` also stores the metrics for the UI.

    python -m evaluation.build_gold_set --sample 60
    python -m evaluation.run_eval --label 2026-10-15-ablation --persist
    python -m evaluation.run_eval --full-fast --label full-fast   # all queries, fast modes
    python -m evaluation.run_eval --resummarise 2026-10-15-ablation  # recompute from per_query
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.retrieval import embeddings, reranker
from app.ai.retrieval.pipeline import retrieve
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.models.corpus import Circular
from app.db.models.enums import EvalSuite, RetrievalMode
from app.db.models.evaluation import EvalResult, EvalRun
from app.db.session import get_sessionmaker
from app.repositories.evaluation import EvaluationRepository
from app.repositories.search import SearchFilters
from evaluation.build_gold_set import GOLD_PATH, SAMPLE_PATH, GoldQuery, read_gold, read_sample
from evaluation.metrics.retrieval import (
    CUTOFF,
    Metric,
    QueryOutcome,
    latency_metrics,
    ranking_metrics,
    refusal_metrics,
)
from evaluation.provenance import code_identity, file_sha256, machine, model_revision
from evaluation.stats import paired_difference

ROOT = Path(__file__).resolve().parent
RESULTS_DIR = ROOT / "results" / "retrieval"
OUT_OF_SCOPE_PATH = ROOT / "datasets" / "out_of_scope.jsonl"
# The subsets a ranking can be scored on (they carry a relevant circular).
RANKED = ("semantic", "identifier")

MODES = [
    RetrievalMode.DENSE,
    RetrievalMode.LEXICAL,
    RetrievalMode.HYBRID,
    RetrievalMode.HYBRID_RERANK,
]
FAST_MODES = MODES[:3]
# Enough candidates that removing the citing circular still leaves CUTOFF.
_FETCH = CUTOFF + 5

COMPARISONS = [
    (RetrievalMode.HYBRID_RERANK, RetrievalMode.LEXICAL),
    (RetrievalMode.HYBRID_RERANK, RetrievalMode.HYBRID),
    (RetrievalMode.HYBRID, RetrievalMode.LEXICAL),
    (RetrievalMode.HYBRID, RetrievalMode.DENSE),
]


def _refusal_rows() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in OUT_OF_SCOPE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _refusal_queries() -> list[GoldQuery]:
    """The refusal suite: questions to refuse, and answerable controls.

    Controls are on-topic questions with no relevance label. They score no
    ranking, but refusing one is a false refusal.
    """
    return [
        GoldQuery(
            query_id=row["id"],
            subset="out_of_scope" if row["should_refuse"] else "control",
            query=row["query"],
            relevant=[],
            citing_circular="",
            citing_paragraph=-1,
            reference="",
        )
        for row in _refusal_rows()
    ]


async def _numbers(session: AsyncSession) -> dict[int, str]:
    rows = await session.execute(select(Circular.id, Circular.circular_number))
    return {cid: number for cid, number in rows.all()}


async def run_query(
    session: AsyncSession,
    query: GoldQuery,
    mode: RetrievalMode,
    numbers: dict[int, str],
    threshold: float,
) -> QueryOutcome:
    started = time.perf_counter()
    result = await retrieve(
        session,
        query.query,
        mode=mode,
        filters=SearchFilters(),
        top_k=_FETCH,
        apply_threshold=False,
    )
    latency_ms = (time.perf_counter() - started) * 1000

    retrieved: list[str] = []
    top: float | None = None
    for hit in result.hits:
        number = numbers.get(hit.circular_id, f"#{hit.circular_id}")
        if number == query.citing_circular or number in retrieved:
            continue
        if top is None:
            top = hit.score
        retrieved.append(number)
        if len(retrieved) == CUTOFF:
            break
    # The refusal rule of the reranked mode, applied to the ranking as evaluated.
    refused = (top is None or top < threshold) if mode is RetrievalMode.HYBRID_RERANK else None
    return QueryOutcome(
        query_id=query.query_id,
        subset=query.subset,
        cluster=query.citing_circular or query.query_id,
        mode=mode.value,
        relevant=query.relevant,
        retrieved=retrieved,
        top_score=top,
        refused=refused,
        latency_ms=round(latency_ms, 2),
        excluded=query.citing_circular or None,
    )


def _metric_dict(metric: Metric) -> dict[str, Any]:
    out = asdict(metric)
    out["ci"] = list(metric.ci) if metric.ci else None
    return out


def summarise(outcomes: list[QueryOutcome], modes: list[RetrievalMode]) -> dict[str, Any]:
    by_mode: dict[str, Any] = {}
    for mode in modes:
        rows = [o for o in outcomes if o.mode == mode.value]
        in_scope = [o for o in rows if o.subset in RANKED]
        out_scope = [o for o in rows if o.subset == "out_of_scope"]
        controls = [o for o in rows if o.subset == "control"]
        metrics: list[Metric] = []
        metrics += ranking_metrics(in_scope, "all")
        for subset in RANKED:
            metrics += ranking_metrics([o for o in in_scope if o.subset == subset], subset)
        metrics += refusal_metrics(in_scope, out_scope, controls)
        metrics += latency_metrics(rows)
        misses = [o for o in in_scope if o.rank is None]
        by_mode[mode.value] = {
            "n_in_scope": len(in_scope),
            "n_out_of_scope": len(out_scope),
            "n_controls": len(controls),
            "metrics": [_metric_dict(m) for m in metrics],
            "error_examples": [
                {
                    "query_id": o.query_id,
                    "subset": o.subset,
                    "relevant": o.relevant,
                    "top3": o.retrieved[:3],
                }
                for o in sorted(misses, key=lambda o: o.query_id)[:6]
            ],
        }

    comparisons = []
    present = {m.value for m in modes}
    for a, b in COMPARISONS:
        if a.value not in present or b.value not in present:
            continue
        index = {(o.mode, o.query_id): o for o in outcomes if o.subset in RANKED}
        ids = sorted({o.query_id for o in outcomes if o.subset in RANKED})
        for name, fn in (
            ("recall@10", lambda o: o.hit(CUTOFF)),
            ("mrr@10", lambda o: o.reciprocal_rank()),
        ):
            pairs = [
                (fn(index[(a.value, q)]), fn(index[(b.value, q)]), index[(a.value, q)].cluster)
                for q in ids
            ]
            estimate, interval = paired_difference(pairs)
            comparisons.append(
                {
                    "a": a.value,
                    "b": b.value,
                    "metric": name,
                    "difference": estimate,
                    "ci": list(interval) if interval else None,
                    "n": len(pairs),
                }
            )
    return {"modes": by_mode, "paired_differences": comparisons}


async def evaluate(
    queries: list[GoldQuery], modes: list[RetrievalMode]
) -> tuple[list[QueryOutcome], dict[str, float]]:
    settings = get_settings()
    loads: dict[str, float] = {}
    # Load the models before timing anything, so latency is warm per-query cost.
    started = time.perf_counter()
    embeddings.embed_query("warm up")
    loads["embedding_model_load_s"] = round(time.perf_counter() - started, 2)
    if RetrievalMode.HYBRID_RERANK in modes:
        started = time.perf_counter()
        reranker.rerank("warm up", [(0, "warm up")])
        loads["reranker_load_s"] = round(time.perf_counter() - started, 2)

    outcomes: list[QueryOutcome] = []
    async with get_sessionmaker()() as session:
        numbers = await _numbers(session)
        for mode in modes:
            started = time.perf_counter()
            for index, query in enumerate(queries, start=1):
                outcomes.append(
                    await run_query(session, query, mode, numbers, settings.relevance_threshold)
                )
                if index % 25 == 0 or index == len(queries):
                    print(f"  {mode.value:14} {index}/{len(queries)}", flush=True)
            loads[f"{mode.value}_wall_s"] = round(time.perf_counter() - started, 1)
    return outcomes, loads


def _query_counts(subsets: list[str]) -> dict[str, int]:
    return {s: subsets.count(s) for s in (*RANKED, "out_of_scope", "control")}


def provenance(
    queries: list[GoldQuery], sample: dict | None, timings: dict[str, float], code: dict[str, Any]
) -> dict[str, Any]:
    settings = get_settings()
    return {
        "code": {**code, "recorded": "when the run started"},
        "models": {
            "embedding": {
                "id": settings.embedding_model,
                "revision": model_revision(settings.embedding_model),
            },
            "reranker": {
                "id": settings.reranker_model,
                "revision": model_revision(settings.reranker_model),
                "activation": "sigmoid over the single logit (scores in 0..1, uncalibrated)",
            },
        },
        "retrieval_config": {
            "rrf_k": settings.rrf_k,
            "retrieve_top_n": settings.retrieve_top_n,
            "relevance_threshold": settings.relevance_threshold,
            "threshold_origin": (
                "configuration default set before this evaluation; not tuned on this sample"
            ),
            "cutoff": CUTOFF,
        },
        "data": {
            "corpus": "synthetic (ingestion/generate_corpus.py)",
            "database": settings.postgres_db,
            "gold_file": f"evaluation/datasets/synthetic/{GOLD_PATH.name}",
            "gold_sha256": file_sha256(GOLD_PATH),
            "sample_manifest": f"evaluation/datasets/synthetic/{SAMPLE_PATH.name}"
            if sample
            else None,
            "sample_seed": sample["seed"] if sample else None,
            "out_of_scope_file": "evaluation/datasets/out_of_scope.jsonl",
            "out_of_scope_sha256": file_sha256(OUT_OF_SCOPE_PATH),
            "queries": _query_counts([q.subset for q in queries]),
            "relevance": (
                "template-derived citation labels: one relevant circular per query (the cited one)"
            ),
            "exclusions": "the circular a query was taken from is removed from its ranking",
        },
        "machine": machine(),
        "timing": {
            "method": (
                "time.perf_counter around one retrieve() call; models loaded first; "
                "one query at a time"
            ),
            **timings,
        },
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
    }


async def persist(summary: dict[str, Any], label: str) -> None:
    """Store each mode's metrics as an evaluation run, for the evaluation page.

    Runs stored earlier under the same label are replaced, so a corrected
    summary never sits beside the one it corrects.
    """
    prov = summary["provenance"]
    code = prov["code"]
    # git_sha holds the commit only (the column is 40 characters); the dirty
    # state and digest of uncommitted evaluated sources travel in config.
    config = {
        "label": label,
        "dirty": code["dirty"],
        "dirty_digest": code["dirty_digest"],
        "models": prov["models"],
        "retrieval_config": prov["retrieval_config"],
        "machine": prov["machine"],
        "data": prov["data"],
    }
    async with get_sessionmaker()() as session:
        await session.execute(
            delete(EvalRun).where(
                EvalRun.suite == EvalSuite.RETRIEVAL, EvalRun.config["label"].astext == label
            )
        )
        repo = EvaluationRepository(session)
        for mode_name, block in summary["modes"].items():
            run = await repo.add_run(
                EvalRun(
                    suite=EvalSuite.RETRIEVAL,
                    git_sha=code["git_sha"],
                    mode=RetrievalMode(mode_name),
                    dataset=prov["data"]["sample_manifest"] or prov["data"]["gold_file"],
                    config=config,
                    notes=(
                        f"{block['n_in_scope']} labelled in-scope queries, "
                        f"{block['n_out_of_scope']} to refuse and "
                        f"{block.get('n_controls', 0)} unlabelled controls on the synthetic "
                        "corpus; template-derived relevance labels, not human judgements."
                    ),
                )
            )
            rows = [
                EvalResult(
                    eval_run_id=run.id,
                    metric_name=m["name"],
                    metric_value=float(m["value"]),
                    subset=m["subset"],
                    k=m["k"],
                    detail={
                        "n": m["n"],
                        "n_queries": m["n"],
                        "ci_low": m["ci"][0] if m["ci"] else None,
                        "ci_high": m["ci"][1] if m["ci"] else None,
                        "note": m["note"],
                    },
                )
                for m in block["metrics"]
            ]
            await repo.add_results(rows)
            await repo.finish_run(run.id)
        await session.commit()


async def run(label: str, full_fast: bool, persist_results: bool, limit: int | None) -> int:
    gold = read_gold()
    if not gold:
        print(f"No gold set at {GOLD_PATH}. Run: python -m evaluation.build_gold_set --sample 60")
        return 1
    if full_fast:
        queries, sample, modes = gold, None, FAST_MODES
    else:
        if not SAMPLE_PATH.is_file():
            print(
                f"No sample manifest at {SAMPLE_PATH}. "
                "Run: python -m evaluation.build_gold_set --sample 60"
            )
            return 1
        sample = read_sample()
        if sample["gold_sha256"] != file_sha256(GOLD_PATH):
            print(
                "The sample manifest was drawn from a different gold file; rebuild both together."
            )
            return 1
        wanted = set(sample["query_ids"])
        queries, modes = [q for q in gold if q.query_id in wanted], MODES
    refusal = _refusal_queries()
    if limit:
        queries, refusal = queries[:limit], refusal[:limit]
    queries = queries + refusal

    # Identify the code before the run, while it is the code being imported.
    code = code_identity()
    print(f"{len(queries)} queries x {len(modes)} modes", flush=True)
    outcomes, timings = await evaluate(queries, modes)
    summary = summarise(outcomes, modes)
    summary["provenance"] = provenance(queries, sample, timings, code)

    out_dir = RESULTS_DIR / label
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "per_query.jsonl").open("w", encoding="utf-8") as handle:
        for outcome in outcomes:
            handle.write(json.dumps(asdict(outcome), ensure_ascii=False) + "\n")
    _write_summary(summary, out_dir)
    return await _report(summary, label, persist_results)


async def resummarise(label: str, persist_results: bool) -> int:
    """Recompute a stored run's summary from its per-query rows.

    Retrieval is not repeated: a row's outcome does not depend on how its
    subset is labelled, so corrected labelling or metrics apply to the rows as
    measured. The measurement's provenance is kept and the code that
    recomputed the summary is added to it.
    """
    out_dir = RESULTS_DIR / label
    previous = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    prov = previous["provenance"]
    if prov["data"]["out_of_scope_sha256"] != file_sha256(OUT_OF_SCOPE_PATH):
        print("The refusal questions changed since this run; rerun it instead.")
        return 1
    subset_of = {q.query_id: q.subset for q in _refusal_queries()}
    outcomes = []
    for line in (out_dir / "per_query.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["subset"] not in RANKED:
            row["subset"] = subset_of[row["query_id"]]
        outcomes.append(QueryOutcome(**row))
    modes = [m for m in MODES if any(o.mode == m.value for o in outcomes)]
    summary = summarise(outcomes, modes)
    prov["code"].setdefault("recorded", "when the run finished")
    prov["data"]["queries"] = _query_counts(
        [o.subset for o in outcomes if o.mode == modes[0].value]
    )
    prov["resummarised"] = {
        "code": code_identity(),
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "method": "summary recomputed from per_query.jsonl as measured; retrieval not repeated",
    }
    summary["provenance"] = prov

    # Rewrite the rows with their corrected subsets, so the two files agree.
    with (out_dir / "per_query.jsonl").open("w", encoding="utf-8") as handle:
        for outcome in outcomes:
            handle.write(json.dumps(asdict(outcome), ensure_ascii=False) + "\n")
    _write_summary(summary, out_dir)
    return await _report(summary, label, persist_results)


def _write_summary(summary: dict[str, Any], out_dir: Path) -> None:
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_dir}")


async def _report(summary: dict[str, Any], label: str, persist_results: bool) -> int:
    for mode_name, block in summary["modes"].items():
        values = {(m["name"], m["subset"]): m["value"] for m in block["metrics"]}
        print(
            f"  {mode_name:14} R@10={values[('recall@10', 'all')]:.3f} "
            f"MRR={values[('mrr@10', 'all')]:.3f} "
            f"p50={values[('latency_p50_ms', 'all')]:.0f} ms "
            f"p95={values[('latency_p95_ms', 'all')]:.0f} ms"
        )
    if persist_results:
        await persist(summary, label)
        print("Stored in the database for the evaluation page.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Retrieval evaluation over a fixed query manifest."
    )
    parser.add_argument("--label", default=datetime.now(UTC).strftime("%Y-%m-%d-%H%M"))
    parser.add_argument(
        "--full-fast", action="store_true", help="every gold query, fast modes only (no reranking)"
    )
    parser.add_argument(
        "--persist", action="store_true", help="store metrics in the database for the UI"
    )
    parser.add_argument("--limit", type=int, default=None, help="first N queries only (smoke runs)")
    parser.add_argument(
        "--resummarise",
        metavar="LABEL",
        help="recompute a stored run's summary from its per-query rows (no retrieval)",
    )
    args = parser.parse_args(argv)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    configure_logging("WARNING")
    if args.resummarise:
        return asyncio.run(resummarise(args.resummarise, args.persist))
    return asyncio.run(run(args.label, args.full_fast, args.persist, args.limit))


if __name__ == "__main__":
    raise SystemExit(main())
