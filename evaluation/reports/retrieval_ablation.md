# Retrieval ablation

- Commit: `unknown`
- Generated: 2026-08-12T14:29:33+00:00
- Queries per mode: 50 (stratified sample of the gold set)
- Corpus: **synthetic** (see `ingestion/generate_corpus.py`) — these are
  real measurements of the real pipeline, on a corpus that is not real SEBI text.

Relevance comes from the corpus's own citation graph: a chunk is relevant
if it belongs to the circular the querying paragraph cited.

| Mode | Subset | N | Recall@5 | Recall@10 | MRR |
|---|---|---:|---:|---:|---:|
| `hybrid_rerank` | semantic | 25 | 0.400 | 0.520 | 0.179 |
| `hybrid_rerank` | identifier | 25 | 1.000 | 1.000 | 0.953 |
| `hybrid_rerank` | all | 50 | 0.700 | 0.760 | 0.566 |
