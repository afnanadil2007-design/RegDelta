"""Latency and cost, broken down by graph node.

Percentiles rather than means: an assessment's cost is dominated by its slow
tail, and a mean latency hides the node that occasionally takes thirty
seconds. p50 and p95 are computed with linear interpolation so small samples
do not snap to a single observation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def percentile(values: list[float], q: float) -> float:
    """Linear-interpolated percentile. ``q`` in 0..1."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


@dataclass
class NodeStats:
    node: str
    calls: int
    p50_ms: float
    p95_ms: float
    total_ms: float
    total_tokens: int
    total_cost_usd: float

    @property
    def mean_cost_per_call(self) -> float:
        return self.total_cost_usd / self.calls if self.calls else 0.0


@dataclass
class RunStats:
    """Per-assessment totals, plus the per-node breakdown."""

    n_assessments: int
    p50_latency_ms: float
    p95_latency_ms: float
    mean_tokens: float
    mean_cost_usd: float
    by_node: list[NodeStats] = field(default_factory=list)


@dataclass
class StepSample:
    node: str
    latency_ms: float
    tokens: int
    cost_usd: float


def node_breakdown(steps: list[StepSample]) -> list[NodeStats]:
    grouped: dict[str, list[StepSample]] = {}
    for step in steps:
        grouped.setdefault(step.node, []).append(step)

    stats = [
        NodeStats(
            node=node,
            calls=len(samples),
            p50_ms=percentile([s.latency_ms for s in samples], 0.50),
            p95_ms=percentile([s.latency_ms for s in samples], 0.95),
            total_ms=sum(s.latency_ms for s in samples),
            total_tokens=sum(s.tokens for s in samples),
            total_cost_usd=sum(s.cost_usd for s in samples),
        )
        for node, samples in grouped.items()
    ]
    # Most expensive first — that is the row a reader is looking for.
    stats.sort(key=lambda s: -s.total_ms)
    return stats


def run_stats(
    assessment_latencies_ms: list[float],
    assessment_tokens: list[int],
    assessment_costs: list[float],
    steps: list[StepSample],
) -> RunStats:
    n = len(assessment_latencies_ms)
    return RunStats(
        n_assessments=n,
        p50_latency_ms=percentile(assessment_latencies_ms, 0.50),
        p95_latency_ms=percentile(assessment_latencies_ms, 0.95),
        mean_tokens=sum(assessment_tokens) / n if n else 0.0,
        mean_cost_usd=sum(assessment_costs) / n if n else 0.0,
        by_node=node_breakdown(steps),
    )
