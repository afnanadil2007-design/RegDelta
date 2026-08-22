"""Retrieval metrics: Recall@k and MRR, reported per subset.

Relevance is binary and comes from the citation graph: a retrieved chunk is
relevant iff it belongs to the cited circular. Because a cited circular
usually has several chunks, Recall@k here is *hit rate* — did any relevant
chunk appear in the top k — which is the meaningful question when the unit of
relevance is the document, not the passage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean


@dataclass
class QueryResult:
    """One query's outcome: the ranked chunk ids and the relevant set."""

    query_id: str
    subset: str
    retrieved_chunk_ids: list[int]
    relevant_chunk_ids: set[int]

    def first_relevant_rank(self) -> int | None:
        """1-indexed rank of the first relevant chunk, or None if absent."""
        for rank, chunk_id in enumerate(self.retrieved_chunk_ids, start=1):
            if chunk_id in self.relevant_chunk_ids:
                return rank
        return None

    def hit_at(self, k: int) -> bool:
        return any(c in self.relevant_chunk_ids for c in self.retrieved_chunk_ids[:k])


@dataclass
class MetricSet:
    """Metrics for one subset (or for everything, when subset is 'all')."""

    subset: str
    n_queries: int
    recall_at_5: float
    recall_at_10: float
    mrr: float
    detail: dict = field(default_factory=dict)

    def as_row(self) -> dict:
        return {
            "subset": self.subset,
            "n": self.n_queries,
            "recall@5": round(self.recall_at_5, 4),
            "recall@10": round(self.recall_at_10, 4),
            "mrr": round(self.mrr, 4),
        }


def compute(results: list[QueryResult], subset: str = "all") -> MetricSet:
    """Recall@5, Recall@10 and MRR over a list of query results."""
    if not results:
        return MetricSet(subset, 0, 0.0, 0.0, 0.0)

    recall_5 = mean(1.0 if r.hit_at(5) else 0.0 for r in results)
    recall_10 = mean(1.0 if r.hit_at(10) else 0.0 for r in results)

    reciprocal_ranks = []
    for result in results:
        rank = result.first_relevant_rank()
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)

    return MetricSet(
        subset=subset,
        n_queries=len(results),
        recall_at_5=recall_5,
        recall_at_10=recall_10,
        mrr=mean(reciprocal_ranks),
    )


def compute_by_subset(results: list[QueryResult]) -> dict[str, MetricSet]:
    """Metrics per subset plus an 'all' row.

    The per-subset split is the point of the harness: a mode that wins overall
    while collapsing on one subset is not an improvement, and only the split
    reveals it.
    """
    out: dict[str, MetricSet] = {}
    for subset in sorted({r.subset for r in results}):
        out[subset] = compute([r for r in results if r.subset == subset], subset)
    out["all"] = compute(results, "all")
    return out
