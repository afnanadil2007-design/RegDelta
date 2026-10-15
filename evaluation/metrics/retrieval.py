"""Retrieval metrics over per-query outcomes.

Relevance is binary and at the document level: a query is answered at rank r
when the r-th distinct circular returned is one of its relevant circulars.
Recall@k is therefore the hit rate (any relevant circular in the top k), and
MRR is truncated at 10 (a miss scores 0).

Refusal is reported beside ranking quality, never folded into it silently:
``recall@k`` measures the ranking with the threshold not applied, and
``answered_recall@10`` is what a user of the refusing mode experiences, a
refused query counting as a miss.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import mean

from evaluation.stats import cluster_bootstrap, percentile, wilson

CUTOFF = 10


@dataclass
class QueryOutcome:
    query_id: str
    subset: str  # semantic | identifier | out_of_scope
    cluster: str  # citing circular, or the query id for independent queries
    mode: str
    relevant: list[str]
    retrieved: list[str]  # distinct circular numbers, best first, at most CUTOFF
    top_score: float | None
    refused: bool | None  # None: the mode has no refusal threshold
    latency_ms: float
    excluded: str | None = None  # the citing circular, removed from the ranking

    @property
    def rank(self) -> int | None:
        for position, number in enumerate(self.retrieved, start=1):
            if number in self.relevant:
                return position
        return None

    def hit(self, k: int) -> float:
        rank = self.rank
        return 1.0 if rank is not None and rank <= k else 0.0

    def reciprocal_rank(self) -> float:
        rank = self.rank
        return 1.0 / rank if rank is not None else 0.0

    def answered_hit(self, k: int) -> float:
        return 0.0 if self.refused else self.hit(k)


@dataclass
class Metric:
    name: str
    value: float
    n: int
    subset: str
    k: int | None = None
    ci: tuple[float, float] | None = None
    note: str | None = None
    extra: dict = field(default_factory=dict)


def _interval(outcomes: Sequence[QueryOutcome], fn) -> tuple[float, float] | None:
    return cluster_bootstrap(
        outcomes, cluster_of=lambda o: o.cluster, statistic=lambda s: mean(fn(o) for o in s)
    )


def ranking_metrics(outcomes: Sequence[QueryOutcome], subset: str) -> list[Metric]:
    """Recall@1/5/10 and MRR@10 with cluster-bootstrap intervals."""
    if not outcomes:
        return []
    n = len(outcomes)
    out = []
    for k in (1, 5, 10):
        value = mean(o.hit(k) for o in outcomes)
        out.append(
            Metric(
                f"recall@{k}",
                value,
                n,
                subset,
                k=k,
                ci=_interval(outcomes, lambda o, k=k: o.hit(k)),
            )
        )
    out.append(
        Metric(
            "mrr@10",
            mean(o.reciprocal_rank() for o in outcomes),
            n,
            subset,
            k=CUTOFF,
            ci=_interval(outcomes, lambda o: o.reciprocal_rank()),
        )
    )
    return out


def refusal_metrics(
    in_scope: Sequence[QueryOutcome], out_of_scope: Sequence[QueryOutcome]
) -> list[Metric]:
    """Refusal on in-scope queries (unwanted) and on out-of-scope queries (wanted)."""
    if not in_scope or in_scope[0].refused is None:
        note = "This mode has no refusal threshold: it always returns passages."
        return [
            Metric("refusal_rate", 0.0, len(in_scope), "in_scope", note=note),
            Metric("refusal_rate", 0.0, len(out_of_scope), "out_of_scope", note=note),
        ]
    refused_in = sum(1 for o in in_scope if o.refused)
    refused_out = sum(1 for o in out_of_scope if o.refused)
    return [
        Metric(
            "refusal_rate",
            refused_in / len(in_scope),
            len(in_scope),
            "in_scope",
            ci=_interval(in_scope, lambda o: 1.0 if o.refused else 0.0),
            note="Answerable queries the mode declined (false refusals).",
        ),
        Metric(
            "refusal_rate",
            refused_out / len(out_of_scope) if out_of_scope else 0.0,
            len(out_of_scope),
            "out_of_scope",
            ci=wilson(refused_out, len(out_of_scope)),
            note="Unanswerable queries the mode declined (correct refusals).",
        ),
        Metric(
            "answered_recall@10",
            mean(o.answered_hit(CUTOFF) for o in in_scope),
            len(in_scope),
            "in_scope",
            k=CUTOFF,
            ci=_interval(in_scope, lambda o: o.answered_hit(CUTOFF)),
            note="Recall@10 counting a refused query as a miss.",
        ),
    ]


def latency_metrics(outcomes: Sequence[QueryOutcome]) -> list[Metric]:
    values = [o.latency_ms for o in outcomes]
    if not values:
        return []
    return [
        Metric("latency_p50_ms", percentile(values, 50) or 0.0, len(values), "all"),
        Metric("latency_p95_ms", percentile(values, 95) or 0.0, len(values), "all"),
        Metric("latency_mean_ms", mean(values), len(values), "all"),
    ]
