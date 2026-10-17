# 2026-10-15-ablation

Four retrieval modes on the fixed sample manifest
(`evaluation/datasets/synthetic/retrieval_sample.json`: 120 labelled queries
from 60 citations) plus the 30-question refusal suite, against the synthetic
demo database.

    python -m evaluation.run_eval --label 2026-10-15-ablation --persist
    python -m evaluation.run_eval --resummarise 2026-10-15-ablation --persist

Three things about this run are not visible in the numbers alone.

## Which code ran

The process started at 11:16:41 IST, nine seconds after commit `8f72b88`.
The `run_eval` of that commit identified the code when the run *ended*, by
which time HEAD was `9b50ce0` with the evaluated sources clean, so
`provenance.code` says `9b50ce0` and `recorded: when the run finished`.
Between the two commits the only change to a module the run imported was
`persist()` in `run_eval.py` (how the commit is written to the database);
retrieval, ranking and scoring code are identical. Since `87ccc92` the
identity is taken when a run starts.

## The summary was recomputed once

The refusal file holds 15 questions that should be refused and 15 on-topic
controls that should not. The runner as it ran labelled all 30 out of scope,
so the first summary reported the reranked mode as refusing "15 of 30
out-of-scope" questions. The correct reading is 15 of 15 refused and 0 of 15
controls refused. `--resummarise` (commit `87ccc92`) relabelled the stored
rows by question id and recomputed every metric from `per_query.jsonl`;
retrieval was not repeated, and no ranking metric changed. The summary
records this under `provenance.resummarised`.

## Latency was measured on a busy laptop

Per-query times are `time.perf_counter()` around one `retrieve()` call on an
i5-5300U (4 logical CPUs, 7.6 GiB RAM) that was also running an editor, a
browser and other containers. Swap was full by the end of the run. Median
reranked latency by sixth of the run (25 queries each) was 46, 56, 60, 44,
69 and 102 seconds, so the reported p50 (56 s) and p95 (117 s) describe this
machine under that load, not the reranker. The wall clock advanced about
7.6 hours during the reranked mode while `perf_counter` advanced 2.7 hours
(`hybrid_rerank_wall_s` = 9733), which is consistent with the laptop
sleeping; time asleep is not counted in any query's latency.
