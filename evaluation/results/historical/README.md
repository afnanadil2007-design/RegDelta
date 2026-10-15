# Historical results (superseded)

These files predate the 2026-10 repair. They are kept as history, not as
current measurements, and no current claim in the documentation rests on them.

- `2026-08-12-retrieval-ablation.md`: `hybrid_rerank` only, 50 queries,
  commit recorded as `unknown`. It was produced before the reranker scoring
  correction and before the evaluation removed the citing circular from each
  query's ranking, and its gold set named chunks by database id. Its numbers
  are not comparable with the current runs.
- `2026-08-evaluation-suites.md`, `2026-08-evaluation-refusal.md`: suite
  reports from the same period, same provenance caveats.
- `2026-08-baseline.json`: the former CI gate baseline (Recall@10 of
  `hybrid_rerank` on a 50-query sample of the 300-document corpus, while CI
  measured a 60-document corpus). Replaced by `evaluation/baseline.json`,
  which records the corpus and gold set it was measured on.

Current results live in `evaluation/results/retrieval/` and are summarised in
`docs/evaluation.md`.
