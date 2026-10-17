"""CI gate: fail when fast retrieval regresses on the CI corpus.

The gate runs hybrid retrieval (dense + lexical fused, no cross-encoder, well
under a second per query) over every gold query of the small corpus CI builds,
and compares Recall@10 and MRR@10 with ``evaluation/baseline.json``. The
baseline records the corpus it was measured on; a gate run on a different
corpus is refused rather than compared, because the numbers would not mean
the same thing.

The reranked mode is too slow for a pull-request gate on CPU (tens of seconds
per query); it is measured by the full evaluation instead (``make eval``).

    python -m evaluation.check_baseline                 # compare
    python -m evaluation.check_baseline --write         # new baseline; say why in the commit
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from statistics import mean

from app.core.logging import configure_logging
from app.db.models.enums import RetrievalMode
from evaluation.build_gold_set import GOLD_PATH, read_gold
from evaluation.metrics.retrieval import CUTOFF
from evaluation.provenance import code_identity, file_sha256
from evaluation.run_eval import evaluate

BASELINE_PATH = Path(__file__).resolve().parent / "baseline.json"
# Absolute points (0..1 scale) a change may cost before the gate fails.
DEFAULT_TOLERANCE = 0.03


async def run(tolerance: float, write: bool) -> int:
    configure_logging("WARNING")
    gold = read_gold()
    if not gold:
        print(f"No gold set at {GOLD_PATH}. Run: python -m evaluation.build_gold_set")
        return 1
    outcomes, _ = await evaluate(gold, [RetrievalMode.HYBRID])
    measured = {
        "recall@10": round(mean(o.hit(CUTOFF) for o in outcomes), 4),
        "mrr@10": round(mean(o.reciprocal_rank() for o in outcomes), 4),
    }
    gold_sha = file_sha256(GOLD_PATH)

    if write:
        identity = code_identity()
        BASELINE_PATH.write_text(
            json.dumps(
                {
                    "mode": RetrievalMode.HYBRID.value,
                    "gold_sha256": gold_sha,
                    "queries": len(gold),
                    **measured,
                    "measured_at": identity["git_sha"],
                    "measured_dirty_digest": identity["dirty_digest"],
                    "corpus": "python -m ingestion.generate_corpus --count 60 (CI corpus)",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {BASELINE_PATH}: {measured} over {len(gold)} queries")
        return 0

    if not BASELINE_PATH.is_file():
        print(f"No baseline at {BASELINE_PATH}; record one with --write.")
        return 1
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    if baseline.get("gold_sha256") != gold_sha:
        print(
            "The gold set differs from the one the baseline was measured on; refusing to compare."
        )
        print(f"  baseline gold {baseline.get('gold_sha256')}\n  current gold  {gold_sha}")
        return 1

    failed = False
    for name, value in measured.items():
        expected = float(baseline[name])
        verdict = "ok" if value >= expected - tolerance else "REGRESSED"
        failed |= verdict != "ok"
        print(
            f"  {name:10} {value:.4f}  baseline {expected:.4f}  "
            f"tolerance {tolerance:.2f}  {verdict}"
        )
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Retrieval regression gate (hybrid mode, CI corpus)."
    )
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    parser.add_argument(
        "--write", action="store_true", help="record the measured values as the new baseline"
    )
    args = parser.parse_args(argv)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(run(args.tolerance, args.write))


if __name__ == "__main__":
    raise SystemExit(main())
