"""Uncertainty for small evaluation samples.

Queries mined from the same citing circular share its wording and its
template, so they are not independent observations. Intervals for retrieval
metrics therefore resample whole clusters (all queries of one citing circular
together) rather than single queries. Proportions over independent items,
such as the hand-written out-of-scope queries, use the Wilson interval.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from statistics import mean
from typing import TypeVar

T = TypeVar("T")

BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20261015


def cluster_bootstrap(
    items: Sequence[T],
    cluster_of: Callable[[T], str],
    statistic: Callable[[Sequence[T]], float],
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    level: float = 0.95,
) -> tuple[float, float] | None:
    """Percentile interval of ``statistic`` under resampling of clusters.

    Returns None when there are fewer than five clusters: an interval from so
    few groups would look precise without being so.
    """
    clusters: dict[str, list[T]] = {}
    for item in items:
        clusters.setdefault(cluster_of(item), []).append(item)
    keys = sorted(clusters)
    if len(keys) < 5:
        return None
    rng = random.Random(seed)
    values = []
    for _ in range(resamples):
        sample: list[T] = []
        for key in rng.choices(keys, k=len(keys)):
            sample.extend(clusters[key])
        values.append(statistic(sample))
    values.sort()
    tail = (1 - level) / 2
    low = values[int(math.floor(tail * (resamples - 1)))]
    high = values[int(math.ceil((1 - tail) * (resamples - 1)))]
    return low, high


def paired_difference(
    pairs: Sequence[tuple[float, float, str]],
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, tuple[float, float] | None]:
    """Mean of (a - b) over paired per-query values, with a cluster interval.

    Each element is (value under system A, value under system B, cluster).
    Pairing on the same queries removes query difficulty from the comparison.
    """
    diffs = [(a - b, cluster) for a, b, cluster in pairs]
    estimate = mean(d for d, _ in diffs) if diffs else 0.0
    interval = cluster_bootstrap(
        diffs,
        cluster_of=lambda d: d[1],
        statistic=lambda sample: mean(d for d, _ in sample),
        resamples=resamples,
        seed=seed,
    )
    return estimate, interval


def wilson(successes: int, n: int, z: float = 1.959964) -> tuple[float, float] | None:
    """Wilson score interval for a binomial proportion (95% by default)."""
    if n == 0:
        return None
    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def percentile(values: Sequence[float], q: float) -> float | None:
    """Linear-interpolated percentile, q in [0, 100]."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
