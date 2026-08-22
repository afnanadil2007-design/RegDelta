"""Run the retrieval evaluation, optionally as a four-mode ablation.

The ablation calls the *same* ``retrieve()`` the API and the agent call, with
only ``mode`` varied. Measuring a parallel implementation would tell you about
the harness, not the product.

    python -m evaluation.run_eval --ablation
    python -m evaluation.run_eval --mode hybrid_rerank --limit 100
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from app.ai.retrieval.pipeline import retrieve
from app.core.config import get_settings
from app.core.logging import bind_run_id, configure_logging
from app.db.models.enums import EvalSuite, RetrievalMode
from app.db.models.evaluation import EvalResult, EvalRun
from app.db.session import get_sessionmaker
from app.repositories.evaluation import EvaluationRepository
from app.repositories.search import SearchFilters
from evaluation.build_gold_set import GOLD_PATH, read_gold
from evaluation.metrics.retrieval import MetricSet, QueryResult, compute_by_subset

REPORT_DIR = Path(__file__).resolve().parent / "reports"
BASELINE_PATH = Path(__file__).resolve().parent / "baseline.json"


def git_sha() -> str:
    """The commit this measurement belongs to.

    Metric trends are only reconstructable if every number is tied to code.
    Falls back to a marker rather than crashing outside a git checkout.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def stratified_sample(pairs: list, per_subset: int, seed: int = 7) -> list:
    """Take ``per_subset`` queries from each subset, deterministically.

    The cross-encoder costs ~0.4s per candidate pair on CPU, so scoring all
    1,300+ gold queries in every mode takes hours. A fixed-seed stratified
    sample keeps both subsets equally represented and keeps the ablation
    reproducible; the sample size is reported alongside every number.
    """
    import random

    rng = random.Random(seed)
    out: list = []
    for subset in sorted({p.subset for p in pairs}):
        bucket = [p for p in pairs if p.subset == subset]
        rng.shuffle(bucket)
        out.extend(bucket[:per_subset])
    return out


async def evaluate_mode(
    mode: RetrievalMode, limit: int | None, sample: int | None = None
) -> tuple[dict[str, MetricSet], float]:
    """Run every gold query through one retrieval mode."""
    pairs = read_gold()
    if not pairs:
        raise SystemExit(f"No gold set at {GOLD_PATH}. Run: python -m evaluation.build_gold_set")
    if sample:
        pairs = stratified_sample(pairs, sample)
    if limit:
        pairs = pairs[:limit]

    results: list[QueryResult] = []
    started = time.perf_counter()

    async with get_sessionmaker()() as session:
        for i, pair in enumerate(pairs, start=1):
            outcome = await retrieve(
                session, pair.query, mode=mode, filters=SearchFilters(), top_k=10
            )
            results.append(
                QueryResult(
                    query_id=pair.query_id,
                    subset=pair.subset,
                    retrieved_chunk_ids=[h.chunk_id for h in outcome.hits],
                    relevant_chunk_ids=set(pair.relevant_chunk_ids),
                )
            )
            if i % 50 == 0:
                print(f"    {mode.value}: {i}/{len(pairs)}", flush=True)

    elapsed = time.perf_counter() - started
    return compute_by_subset(results), elapsed


async def persist(
    mode: RetrievalMode, metrics: dict[str, MetricSet], elapsed: float, sha: str
) -> None:
    """Store the run and its metrics, stamped with the git SHA."""
    settings = get_settings()
    async with get_sessionmaker()() as session:
        repo = EvaluationRepository(session)
        run = await repo.add_run(
            EvalRun(
                suite=EvalSuite.RETRIEVAL,
                git_sha=sha,
                mode=mode,
                dataset=GOLD_PATH.name,
                config={
                    "embedding_model": settings.embedding_model,
                    "reranker_model": settings.reranker_model,
                    "rrf_k": settings.rrf_k,
                    "retrieve_top_n": settings.retrieve_top_n,
                    "rerank_top_k": settings.rerank_top_k,
                    "relevance_threshold": settings.relevance_threshold,
                    "elapsed_seconds": round(elapsed, 2),
                },
            )
        )
        rows = []
        for subset, metric in metrics.items():
            for name, value in (
                ("recall@5", metric.recall_at_5),
                ("recall@10", metric.recall_at_10),
                ("mrr", metric.mrr),
            ):
                k = 5 if name.endswith("5") else 10 if name.endswith("10") else None
                rows.append(
                    EvalResult(
                        eval_run_id=run.id,
                        metric_name=name,
                        metric_value=value,
                        subset=subset,
                        k=k,
                        detail={"n_queries": metric.n_queries},
                    )
                )
        await repo.add_results(rows)
        await repo.finish_run(run.id)
        await session.commit()


def render_markdown(all_metrics: dict[str, dict[str, MetricSet]], sha: str, n_queries: int) -> str:
    """The ablation table that goes in the README."""
    lines = [
        "# Retrieval ablation",
        "",
        f"- Commit: `{sha}`",
        f"- Generated: {datetime.now(UTC).isoformat(timespec='seconds')}",
        f"- Queries per mode: {n_queries} (stratified sample of the gold set)",
        "- Corpus: **synthetic** (see `ingestion/generate_corpus.py`) — these are",
        "  real measurements of the real pipeline, on a corpus that is not real SEBI text.",
        "",
        "Relevance comes from the corpus's own citation graph: a chunk is relevant",
        "if it belongs to the circular the querying paragraph cited.",
        "",
        "| Mode | Subset | N | Recall@5 | Recall@10 | MRR |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for mode_name, metrics in all_metrics.items():
        for subset in ("semantic", "identifier", "all"):
            metric = metrics.get(subset)
            if metric is None:
                continue
            lines.append(
                f"| `{mode_name}` | {subset} | {metric.n_queries} | "
                f"{metric.recall_at_5:.3f} | {metric.recall_at_10:.3f} | {metric.mrr:.3f} |"
            )
    lines.append("")
    return "\n".join(lines)


async def run(
    modes: list[RetrievalMode], limit: int | None, write_baseline: bool, sample: int | None
) -> int:
    settings = get_settings()
    configure_logging("WARNING")  # keep the table readable
    bind_run_id("eval-retrieval")
    sha = git_sha()

    all_metrics: dict[str, dict[str, MetricSet]] = {}
    for mode in modes:
        print(f"  running {mode.value} ...", flush=True)
        metrics, elapsed = await evaluate_mode(mode, limit, sample)
        all_metrics[mode.value] = metrics
        await persist(mode, metrics, elapsed, sha)
        row = metrics["all"].as_row()
        print(
            f"  {mode.value:15} R@5={row['recall@5']:.3f} "
            f"R@10={row['recall@10']:.3f} MRR={row['mrr']:.3f}  ({elapsed:.1f}s)"
        )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = REPORT_DIR / "retrieval_ablation.md"
    n_queries = next(iter(all_metrics.values()))["all"].n_queries
    report.write_text(render_markdown(all_metrics, sha, n_queries), encoding="utf-8")
    print(f"\nWrote {report}")

    if write_baseline:
        best = all_metrics.get(RetrievalMode.HYBRID_RERANK.value) or next(
            iter(all_metrics.values())
        )
        BASELINE_PATH.write_text(
            json.dumps(
                {
                    "git_sha": sha,
                    "mode": RetrievalMode.HYBRID_RERANK.value,
                    "recall@10": round(best["all"].recall_at_10, 4),
                    "recall@5": round(best["all"].recall_at_5, 4),
                    "mrr": round(best["all"].mrr, 4),
                    "n_queries": best["all"].n_queries,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {BASELINE_PATH}")

    _ = settings
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retrieval evaluation.")
    parser.add_argument("--ablation", action="store_true", help="run all four modes")
    parser.add_argument("--mode", default="hybrid_rerank", choices=[m.value for m in RetrievalMode])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--write-baseline", action="store_true", help="update baseline.json")
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="queries per subset (stratified, fixed seed). Omit to use the full gold set.",
    )
    args = parser.parse_args(argv)

    modes = list(RetrievalMode) if args.ablation else [RetrievalMode(args.mode)]

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(run(modes, args.limit, args.write_baseline, args.sample))


if __name__ == "__main__":
    raise SystemExit(main())
