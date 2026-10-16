# Search latency, 2026-10-16 (a bounded benchmark, not an ablation)

`python -m evaluation.bench_rerank --label 2026-10-16-rerank-bench` against
`regdelta_demo` (the 300-circular synthetic corpus of the 2026-10-15
ablation). Eight queries, the first four semantic and the first four
identifier queries of `retrieval_sample.json`, each run once per variant, the
variants interleaved per query. `rows.jsonl` holds every timing and top-10;
`summary.json` the aggregates and provenance.

| Variant | Mode | Candidates | Median | Range | Same top 10 as the measured configuration |
|---|---|---|---|---|---|
| `hybrid` | Hybrid (the UI's default) | 50 | **0.10 s** | 0.06–0.15 s | (different mode) |
| `rerank-50-arrival` | Hybrid + rerank, as measured on 2026-10-15 | 50 | **62.4 s** | 53.5–89.4 s | 8 of 8 (reference) |
| `rerank-50-sorted` | the same, batches sorted by length | 50 | 62.4 s | 48.7–71.4 s | 8 of 8, top scores identical |
| `rerank-20-sorted` | `RETRIEVE_TOP_N=20` | 20 | **25.7 s** | 20.3–41.3 s | 4 of 8 |

- **Warm-up.** Loading the cross-encoder took 8.8 s and the embedder 0.2 s.
  The first reranked search after the load took 59.4 s, no slower than the
  later ones, so there is no warm-up penalty beyond the load itself (the API
  loads both models in the background at start-up).
- **Length-sorted batches: no gain.** Chunks here are 800–1,500 characters,
  so arrival-order batches of 16 pad little. The switch
  (`app/ai/retrieval/reranker.py`, `SORT_BY_LENGTH`) stays `False`, the
  measured configuration.
- **20 candidates: about 2.4 times faster**, with a different top 10 on half
  of these queries. Both found the cited circular in the top 10 for 6 of the
  8; eight queries cannot show what 20 candidates cost in recall, so this is
  a documented speed setting, not a new default. Measuring it would take the
  120-query sample under the same conditions.
- **Not comparable to a quiet machine.** Load average rose from 2.3 to 8.4
  during the run, 14 other projects' containers were running, and swap was
  full (2.0 GiB used). The 2026-10-15 ablation's reranked median was 55.5 s
  under similar sharing. These are this laptop's numbers, not the model's.

Provenance: code `b69acbe` plus the then-uncommitted reranker switch and this
benchmark script (`dirty: true`, digest `32762936…` in `summary.json`); every
variant sets the switch explicitly, so its later default does not affect these
numbers. Intel i5-5300U (4 logical CPUs, torch using 4 threads), 7.6 GiB,
CPython 3.11.16, torch 2.14.1+cpu, sentence-transformers 3.4.1;
`BAAI/bge-small-en-v1.5` @ `5c38ec7c`, `BAAI/bge-reranker-base` @ `2cfc18c9`.
Timing is wall clock around `run_eval.run_query`, in one process, after the
models had loaded.
