"""CI gate: fail the build when retrieval regresses against the baseline.

Runs the production retrieval mode over the gold set and compares Recall@10
with ``evaluation/baseline.json``. A drop of more than ``--tolerance`` points
fails the build.

The gate is one-sided on purpose: an *improvement* never fails, and the
baseline is only updated deliberately (``run_eval --write-baseline``), so a
regression cannot be silently absorbed by a rerun.

    python -m evaluation.check_baseline --sample 15
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.core.logging import configure_logging
from app.db.models.enums import RetrievalMode
from evaluation.run_eval import BASELINE_PATH, evaluate_mode

# Recall points (absolute, on a 0..1 scale) a build may drop before failing.
DEFAULT_TOLERANCE = 0.03


async def run(sample: int | None, tolerance: float) -> int:
    configure_logging("WARNING")

    if not BASELINE_PATH.is_file():
        print(f"No baseline at {BASELINE_PATH}.")
        print("Create one with: python -m evaluation.run_eval --ablation --write-baseline")
        return 1

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    expected = float(baseline["recall@10"])

    metrics, elapsed = await evaluate_mode(RetrievalMode.HYBRID_RERANK, None, sample)
    actual = metrics["all"].recall_at_10
    delta = actual - expected

    print(f"baseline recall@10 : {expected:.4f}  (commit {baseline.get('git_sha', '?')[:8]})")
    print(
        f"current  recall@10 : {actual:.4f}  ({metrics['all'].n_queries} queries, {elapsed:.0f}s)"
    )
    print(f"delta              : {delta:+.4f}  (tolerance {tolerance:.3f})")

    for subset in ("semantic", "identifier"):
        if subset in metrics:
            print(f"  {subset:11}: recall@10 {metrics[subset].recall_at_10:.4f}")

    if delta < -tolerance:
        print(
            f"\nFAIL: recall@10 dropped {abs(delta):.4f} below the baseline, "
            f"more than the {tolerance:.3f} tolerance."
        )
        return 1

    print("\nPASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retrieval regression gate.")
    parser.add_argument("--sample", type=int, default=None, help="queries per subset")
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    args = parser.parse_args(argv)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(run(args.sample, args.tolerance))


if __name__ == "__main__":
    raise SystemExit(main())
