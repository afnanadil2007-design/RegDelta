"""Reciprocal Rank Fusion.

RRF combines ranked lists using **ranks only**, never scores. That is the
whole point: pgvector cosine distances and Postgres ``ts_rank_cd`` values live
on incomparable scales, and any attempt to normalise them into a weighted sum
requires a calibration that drifts with the corpus. Ranks are already
comparable, so RRF needs no tuning beyond ``k``.

    score(d) = sum over retrievers r of  1 / (k + rank_r(d))

``k`` (default 60) damps the influence of the very top ranks so a single
retriever cannot dominate the fusion on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FusedHit:
    """One document after fusion, carrying each retriever's rank.

    The per-retriever ranks are surfaced through the API so the UI can show
    which retriever contributed a result — the fusion is explainable, not a
    black box.
    """

    chunk_id: int
    rrf_score: float
    dense_rank: int | None = None
    lexical_rank: int | None = None
    contributions: dict[str, float] = field(default_factory=dict)


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[int]], k: int = 60
) -> list[FusedHit]:
    """Fuse named ranked lists of chunk ids into one ranking.

    ``ranked_lists`` maps a retriever name ("dense", "lexical") to its ranked
    chunk ids, best first. Documents missing from a list simply contribute
    nothing from that retriever.
    """
    scores: dict[int, float] = {}
    ranks: dict[str, dict[int, int]] = {}
    contributions: dict[int, dict[str, float]] = {}

    for name, chunk_ids in ranked_lists.items():
        ranks[name] = {}
        for position, chunk_id in enumerate(chunk_ids, start=1):
            # A document repeated within one list keeps its best rank.
            if chunk_id in ranks[name]:
                continue
            ranks[name][chunk_id] = position
            contribution = 1.0 / (k + position)
            scores[chunk_id] = scores.get(chunk_id, 0.0) + contribution
            contributions.setdefault(chunk_id, {})[name] = contribution

    hits = [
        FusedHit(
            chunk_id=chunk_id,
            rrf_score=score,
            dense_rank=ranks.get("dense", {}).get(chunk_id),
            lexical_rank=ranks.get("lexical", {}).get(chunk_id),
            contributions=contributions.get(chunk_id, {}),
        )
        for chunk_id, score in scores.items()
    ]
    # Ties broken by chunk id so the ordering is deterministic across runs —
    # a flapping order would make evaluation numbers irreproducible.
    hits.sort(key=lambda h: (-h.rrf_score, h.chunk_id))
    return hits
