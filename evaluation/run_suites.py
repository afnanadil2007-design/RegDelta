"""Run the non-retrieval evaluation suites.

    python -m evaluation.run_suites                # every suite that can run offline
    python -m evaluation.run_suites --suite refusal

Suites that need a provider key (the layer-2 groundedness judge) are skipped
with a stated reason rather than failing the run, so this is usable on a
machine with no key.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from app.ai.extraction.spans import resolve_span
from app.ai.retrieval.pipeline import retrieve
from app.core.config import get_settings
from app.core.logging import bind_run_id, configure_logging
from app.db.models.enums import EvalSuite, RetrievalMode
from app.db.models.evaluation import EvalResult, EvalRun
from app.db.session import get_sessionmaker
from app.repositories.evaluation import EvaluationRepository
from app.repositories.search import SearchFilters
from evaluation.metrics import extraction as extraction_metrics
from evaluation.metrics import groundedness as grounding_metrics
from evaluation.metrics import performance as perf_metrics
from evaluation.metrics import refusal as refusal_metrics
from evaluation.run_eval import REPORT_DIR, git_sha

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.assessment import Finding

# ---------------------------------------------------------------- refusal


async def run_refusal() -> tuple[refusal_metrics.RefusalMetrics | None, str]:
    cases = refusal_metrics.load_cases()
    if not cases:
        return None, "no out_of_scope.jsonl dataset"

    outcomes: list[refusal_metrics.RefusalOutcome] = []
    async with get_sessionmaker()() as session:
        for case in cases:
            result = await retrieve(
                session,
                case.query,
                mode=RetrievalMode.HYBRID_RERANK,
                filters=SearchFilters(),
            )
            outcomes.append(
                refusal_metrics.RefusalOutcome(
                    case=case,
                    refused=result.below_threshold or not result.hits,
                    top_score=result.top_score,
                )
            )
    return refusal_metrics.compute(outcomes), ""


# ------------------------------------------------------------- extraction


async def run_extraction() -> tuple[extraction_metrics.ExtractionMetrics | None, str]:
    labels = extraction_metrics.load_labels()
    if not labels:
        return None, "no obligations_labeled.jsonl (run evaluation.build_extraction_labels)"

    wanted = {label.circular_number for label in labels}

    from sqlalchemy import select

    from app.db.models.corpus import Circular, Obligation

    async with get_sessionmaker()() as session:
        stmt = (
            select(Obligation, Circular.circular_number)
            .join(Circular, Circular.id == Obligation.circular_id)
            .where(Circular.circular_number.in_(wanted))
        )
        rows = (await session.execute(stmt)).all()

    predicted = [
        extraction_metrics.PredictedObligation(
            circular_number=number,
            text=obligation.text,
            actor=obligation.actor,
            char_start=obligation.char_start,
            char_end=obligation.char_end,
        )
        for obligation, number in rows
    ]
    if not predicted:
        return None, "no obligations extracted (run `make obligations`)"

    return extraction_metrics.compute(predicted, labels), ""


# ----------------------------------------------------------- groundedness


async def run_groundedness() -> tuple[grounding_metrics.Layer1Metrics | None, str]:
    """Layer 1 over every stored finding.

    Re-resolves each finding's spans against the source text. The graph already
    enforces this live, so a failure here means a finding reached the database
    without passing verification.
    """
    from sqlalchemy import select

    from app.db.models.assessment import Finding

    async with get_sessionmaker()() as session:
        findings = list((await session.execute(select(Finding))).scalars())
        if not findings:
            return None, "no findings stored (run an assessment first)"

        results = [await _check_finding(session, f) for f in findings]

    return grounding_metrics.compute_layer1(results), ""


async def _check_finding(
    session: AsyncSession, finding: Finding
) -> grounding_metrics.Layer1Result:
    """Re-resolve one finding's spans against the source text."""
    from app.db.models.corpus import Circular, Obligation
    from app.db.models.policy import PolicyClause

    obligation = await session.get(Obligation, finding.obligation_id)
    circular = await session.get(Circular, obligation.circular_id) if obligation else None
    clause = (
        await session.get(PolicyClause, finding.policy_clause_id)
        if finding.policy_clause_id
        else None
    )

    problems: list[str] = []

    circular_ok = True
    if finding.circular_span_start is not None and circular is not None:
        sliced = circular.full_text[
            finding.circular_span_start : finding.circular_span_end or 0
        ]
        circular_ok = bool(sliced.strip())
        if not circular_ok:
            problems.append("circular span does not resolve")

    clause_ok = True
    if finding.clause_span_start is not None and clause is not None:
        # Clause offsets index the pack source; the clause text starts at
        # clause.char_start, so shift into clause-local coordinates.
        local_start = finding.clause_span_start - clause.char_start
        local_end = (finding.clause_span_end or 0) - clause.char_start
        sliced = clause.text[max(local_start, 0) : max(local_end, 0)]
        clause_ok = bool(sliced.strip())
        if not clause_ok:
            problems.append("clause span does not resolve")

    in_context = True
    if obligation and finding.circular_span_start is not None:
        span = resolve_span(
            (circular.full_text if circular else "")[
                finding.circular_span_start : finding.circular_span_end or 0
            ],
            obligation.text,
        )
        in_context = span is not None
        if not in_context:
            problems.append("span is outside the retrieved obligation")

    return grounding_metrics.Layer1Result(
        finding_id=finding.id,
        circular_span_resolves=circular_ok,
        clause_span_resolves=clause_ok,
        span_in_retrieved_context=in_context,
        problems=problems,
    )


# ------------------------------------------------------------ performance


async def run_performance() -> tuple[perf_metrics.RunStats | None, str]:
    from sqlalchemy import select

    from app.db.models.assessment import AgentStep, Assessment

    async with get_sessionmaker()() as session:
        steps = list((await session.execute(select(AgentStep))).scalars())
        assessments = list((await session.execute(select(Assessment))).scalars())

    if not steps:
        return None, "no agent steps recorded (run an assessment first)"

    samples = [
        perf_metrics.StepSample(
            node=step.node,
            latency_ms=float(step.latency_ms or 0),
            tokens=step.tokens_in + step.tokens_out,
            cost_usd=step.cost_usd,
        )
        for step in steps
    ]
    latencies = [
        (a.completed_at - a.created_at).total_seconds() * 1000
        for a in assessments
        if a.completed_at and a.created_at
    ]
    return (
        perf_metrics.run_stats(
            latencies,
            [a.total_tokens for a in assessments],
            [a.total_cost_usd for a in assessments],
            samples,
        ),
        "",
    )


# ------------------------------------------------------------- persistence


async def persist(suite: EvalSuite, values: dict[str, float], sha: str) -> None:
    async with get_sessionmaker()() as session:
        repo = EvaluationRepository(session)
        run = await repo.add_run(EvalRun(suite=suite, git_sha=sha))
        await repo.add_results(
            [
                EvalResult(eval_run_id=run.id, metric_name=name, metric_value=float(value))
                for name, value in values.items()
            ]
        )
        await repo.finish_run(run.id)
        await session.commit()


def _report(lines: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {path}")


def _report_path(selected: str) -> Path:
    """Where this run's report goes.

    A single-suite run writes its own file rather than overwriting the combined
    report — otherwise `--suite extraction` would silently erase the refusal and
    groundedness sections written by the last full run.
    """
    if selected == "all":
        return REPORT_DIR / "evaluation_suites.md"
    return REPORT_DIR / f"evaluation_{selected}.md"


def _skipped(title: str, reason: str) -> list[str]:
    print(f"  skipped: {reason}")
    return [f"## {title}", "", f"Skipped: {reason}", ""]


async def _section_refusal(sha: str) -> list[str]:
    metrics, skip = await run_refusal()
    print("\n=== refusal ===")
    if metrics is None:
        return _skipped("Refusal", skip)

    print(
        f"  correct-refusal rate : {metrics.correct_refusal_rate:.3f} "
        f"({metrics.n_should_refuse} cases)"
    )
    print(
        f"  false-refusal rate   : {metrics.false_refusal_rate:.3f} "
        f"({metrics.n_should_answer} cases)"
    )
    if metrics.missed_refusals:
        print(f"  answered but should not have: {metrics.missed_refusals}")
    if metrics.false_refusals:
        print(f"  refused but should not have: {metrics.false_refusals}")

    await persist(
        EvalSuite.REFUSAL,
        {
            "correct_refusal_rate": metrics.correct_refusal_rate,
            "false_refusal_rate": metrics.false_refusal_rate,
            "overall_accuracy": metrics.overall_accuracy,
        },
        sha,
    )
    return [
        "## Refusal",
        "",
        "| Metric | Value | Cases |",
        "|---|---:|---:|",
        f"| Correct-refusal rate | {metrics.correct_refusal_rate:.3f} | "
        f"{metrics.n_should_refuse} |",
        f"| False-refusal rate | {metrics.false_refusal_rate:.3f} | "
        f"{metrics.n_should_answer} |",
        "",
    ]


async def _section_extraction(sha: str) -> list[str]:
    metrics, skip = await run_extraction()
    print("\n=== extraction ===")
    if metrics is None:
        return _skipped("Extraction", skip)

    print(
        f"  precision {metrics.precision:.3f}  recall {metrics.recall:.3f}  "
        f"F1 {metrics.f1:.3f}"
    )
    print(
        f"  {metrics.n_predicted} predicted vs {metrics.n_labelled} labelled "
        f"across {metrics.n_circulars} circulars"
    )
    await persist(
        EvalSuite.EXTRACTION,
        {"precision": metrics.precision, "recall": metrics.recall, "f1": metrics.f1},
        sha,
    )
    return [
        "## Extraction",
        "",
        "Match rule: overlapping span AND matching actor.",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Precision | {metrics.precision:.3f} |",
        f"| Recall | {metrics.recall:.3f} |",
        f"| F1 | {metrics.f1:.3f} |",
        f"| Labelled / predicted | {metrics.n_labelled} / {metrics.n_predicted} |",
        "",
    ]


async def _section_groundedness(sha: str) -> list[str]:
    metrics, skip = await run_groundedness()
    print("\n=== groundedness (layer 1) ===")
    if metrics is None:
        return _skipped("Groundedness (layer 1)", skip)

    print(
        f"  grounded {metrics.n_grounded}/{metrics.n_findings} "
        f"({metrics.grounded_rate:.3f})"
    )
    await persist(
        EvalSuite.GROUNDEDNESS, {"layer1_grounded_rate": metrics.grounded_rate}, sha
    )
    return [
        "## Groundedness (layer 1)",
        "",
        f"- Grounded: {metrics.n_grounded}/{metrics.n_findings} "
        f"({metrics.grounded_rate:.3f})",
        "",
    ]


async def _section_performance() -> list[str]:
    stats, skip = await run_performance()
    print("\n=== performance ===")
    if stats is None:
        return _skipped("Latency and cost", skip)

    print(
        f"  p50 {stats.p50_latency_ms:.0f}ms  p95 {stats.p95_latency_ms:.0f}ms  "
        f"mean ${stats.mean_cost_usd:.4f}/assessment"
    )
    lines = [
        "## Latency and cost",
        "",
        f"- Assessments: {stats.n_assessments}",
        f"- p50 {stats.p50_latency_ms:.0f}ms, p95 {stats.p95_latency_ms:.0f}ms",
        f"- Mean {stats.mean_tokens:.0f} tokens, ${stats.mean_cost_usd:.4f}",
        "",
        "| Node | Calls | p50 ms | p95 ms | Tokens | Cost |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    lines += [
        f"| `{n.node}` | {n.calls} | {n.p50_ms:.0f} | {n.p95_ms:.0f} | "
        f"{n.total_tokens} | ${n.total_cost_usd:.4f} |"
        for n in stats.by_node
    ]
    lines.append("")
    return lines


async def run(selected: str) -> int:
    configure_logging("WARNING")
    bind_run_id("eval-suites")
    sha = git_sha()
    lines = ["# Evaluation suites", "", f"- Commit: `{sha}`", ""]

    if selected in ("all", "refusal"):
        lines += await _section_refusal(sha)
    if selected in ("all", "extraction"):
        lines += await _section_extraction(sha)
    if selected in ("all", "groundedness"):
        lines += await _section_groundedness(sha)
    if selected in ("all", "performance"):
        lines += await _section_performance()

    _report(lines, _report_path(selected))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the non-retrieval eval suites.")
    parser.add_argument(
        "--suite",
        default="all",
        choices=["all", "refusal", "extraction", "groundedness", "performance"],
    )
    args = parser.parse_args(argv)

    _ = get_settings()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(run(args.suite))


if __name__ == "__main__":
    raise SystemExit(main())
