# Evaluation

What RegDelta measures, how, and what the numbers do not show. The tables
themselves are generated from result files into
[evaluation-results.md](evaluation-results.md); this page explains them.

## At a glance

| Suite | Ground truth | Status |
|---|---|---|
| Retrieval, four modes | template-derived citation labels on the synthetic corpus | measured (sample of 120; fast modes also on all 1,324) |
| Refusal | 15 hand-written questions to refuse, 15 on-topic controls, and the 120 labelled queries | measured with the retrieval run |
| Extraction | 132 obligations planted by the generator in 30 circulars | measured (a regression check; see below) |
| Quote location (groundedness layer 1) | programmatic: quotes must be found verbatim | enforced in every run |
| Real-source retrieval | 39 model-drafted candidate relevance labels (33 questions) on 16 SEBI documents | **not measured**: human review pending |
| Semantic support of findings | human evidence review of 45 exported findings (41 deterministic, four Groq; synthetic corpus) | **not measured**: candidates exported, human review pending |

## The synthetic corpus, and what it can show

The demo and the measured suites use 300 synthetic SEBI-style circulars from
eight topic templates (`ingestion/generate_corpus.py`). They imitate reference
formats, citation density, supersession and amendment language, and obligation
phrasing, and each one is stamped as synthetic.

The numbers are therefore valid as **comparisons between configurations of
one pipeline on one fixed corpus**. They are not estimates of quality on real
SEBI circulars, and they are neither a floor nor a ceiling for it: real
documents are longer, less templated and differently cited, which could move
results either way. That question is unmeasured here.

## Retrieval

### Labels

`evaluation/build_gold_set.py` turns each resolved citation into two queries:

- **semantic**: the citing paragraph with the reference removed;
- **identifier**: the reference string alone.

The cited circular is the one relevant document. In this corpus the
generator wrote the citations, so these are template-derived labels, not
human relevance judgements, and a sibling circular on the same topic that
would also answer a query still counts as a miss. Labels name circulars by
number, so the gold file (1,324 queries from 662 citations) is valid for any
database built from the same corpus.

### Protocol

- **One manifest for all modes.** `retrieval_sample.json` fixes 60 citations
  (seed 20261015), so 120 in-scope queries, plus the 30-question refusal
  suite: 15 questions the system should refuse and 15 on-topic controls it
  should answer. Every mode answers exactly these ids. The manifest stores the
  gold file's SHA-256 and the runner refuses a mismatched pair.
- **Same code as the product.** Each query goes through the `retrieve()` the
  API uses, with only `mode` varied.
- **Threshold off for ranking.** The refusal threshold is not applied while
  ranking is scored, so all modes are compared on the same lists; refusal is
  then computed from the same run by applying the threshold rule to the
  reranked scores.
- **Exclusion.** The circular a query was taken from is removed from that
  query's ranking. It contains the query verbatim and is never the cited
  circular, so leaving it in would penalise every mode for finding the
  source of the query.
- **Fast modes on everything.** Dense, lexical and hybrid also run on all
  1,324 queries (`make eval-fast`); the reranked mode is too slow on CPU for
  that (a median of 56 s per query on the evaluation laptop, under load).

### Metrics and denominators

- **Recall@k** (k = 1, 5, 10): the share of in-scope queries whose relevant
  circular is among the first k distinct circulars returned. With one relevant
  document per query this is a hit rate.
- **MRR@10**: mean of 1/rank of the relevant circular, 0 when it is not in the
  top 10.
- **Refusal, in scope**: labelled queries the reranked mode declined
  (unwanted). **Refusal, controls**: on-topic questions without a relevance
  label that it declined (also unwanted; they count nowhere else).
  **Refusal, out of scope**: questions it should decline and did (wanted).
  The other modes have no threshold and never refuse; the tables say so
  instead of printing 0 as if it were measured behaviour.
- **Answered Recall@10**: Recall@10 counting a refused query as a miss, which
  is what a user of the refusing mode experiences.
- **Latency**: wall time of one `retrieve()` call, models already loaded, one
  query at a time; p50 and p95 per mode. Model loading is timed separately,
  and so is each mode's whole run.

### Uncertainty

Queries drawn from the same citing circular share its wording and template,
so they are not independent. Intervals for retrieval metrics are 95%
percentile intervals from a bootstrap that resamples citing circulars (2,000
resamples, fixed seed), and mode comparisons are paired on identical queries.
The refusal-suite questions are independent, so their refusal rates use the
Wilson interval. With 60 clusters these intervals are wide; differences inside
them are not evidence of a difference.

### Threshold

`RELEVANCE_THRESHOLD = 0.35` is the configuration default set before this
evaluation. It was not tuned on the reported sample, and no held-out tuning
set exists yet; tuning it on these queries and reporting the same queries
would overstate it. The cross-encoder's sigmoid output is a score in 0..1, not
a calibrated probability.

## Retrieval results (2026-10-15)

Full tables, intervals, misses and provenance:
[evaluation-results.md](evaluation-results.md). The run's own notes (which
code ran, one recomputed summary, load during timing):
[`results/retrieval/2026-10-15-ablation/README.md`](../evaluation/results/retrieval/2026-10-15-ablation/README.md).

On the 120-query sample, with 95% intervals:

| Mode | Recall@10 | MRR@10 | Median latency |
|---|---:|---:|---:|
| Dense | 0.250 (0.17–0.34) | 0.074 | 48 ms |
| Lexical | 0.658 (0.60–0.72) | 0.353 | 5 ms |
| Hybrid (RRF) | 0.650 (0.59–0.71) | 0.388 | 47 ms |
| Hybrid + rerank | 0.758 (0.70–0.82) | 0.545 | 56 s |

What the numbers support, and what they do not:

- **Reranking helps on this corpus.** Paired on the same queries, it adds
  +0.108 Recall@10 (+0.059 to +0.164) and +0.157 MRR@10 over Hybrid, and
  +0.100 Recall@10 over Lexical. Most of it is identifier queries moving to
  rank 1 (Recall@1 0.467 → 0.900).
- **Fusion does not beat lexical here.** Hybrid − Lexical is −0.008 Recall@10
  (−0.026 to 0.000) on the sample; on all 1,324 queries Lexical has 0.695 and
  Hybrid 0.665, and fusion costs identifier queries (0.998 → 0.931) while
  adding little to semantic ones (0.391 → 0.399). The dense model alone is
  weak on this corpus (0.274): template-generated circulars are close to one
  another in embedding space, and a reference string carries no meaning an
  embedding can use. Whether fusion helps on real circulars is unmeasured.
- **Semantic queries are hard for every mode** (best Recall@10 0.517, best
  MRR@10 0.142). Many misses return a sibling circular from the same
  department and template, which would often answer the paragraph as well;
  one relevant document per query makes those count as misses.
- **Refusal separated perfectly on a small, easy suite.** The reranked mode
  refused 15 of 15 questions it should refuse (best passage score ≤ 0.011)
  and none of the 15 controls or 120 labelled queries (lowest best score
  0.993). The intervals (0.80–1.00 and 0.00–0.20 for the suite) are wide, and
  the suite has no near-miss questions, such as a SEBI topic the corpus lacks.
- **Latency is this laptop under load**, not the models: medians of the
  reranked mode drifted from 46 s to 102 s across the run as memory filled.
  The fast modes ran slower on the full set (Dense 205 ms median) than on the
  sample for the same reason. The ratio, not the absolute time, is the
  finding: reranking costs about a thousand times a Hybrid query here.

## Refusal history: the double sigmoid

An earlier version of the refusal suite answered every out-of-scope question,
including "What is the capital of France?". `CrossEncoder.predict` already
applies this model's sigmoid, and the code applied a second one, which
squeezed every score into (0.5, 0.731): ordering unchanged, so ranking metrics
looked healthy, but nothing could fall below 0.35 and refusal never fired.
The second sigmoid was removed, and
`test_rerank_scores_span_the_full_zero_to_one_range` (real model) asserts that
an unrelated query scores below the threshold. The August numbers measured
through that bug are kept, labelled, in `evaluation/results/historical/`.

## Extraction and quote location

The extraction suite compares the rule extractor (`rules-v2`) with the
obligations the generator planted in 30 synthetic circulars. On 2026-10-15
(commit `9b50ce0`, evaluated sources clean) it scored precision 1.000 and recall 1.000 (132 of 132;
`evaluation/results/suites/evaluation_extraction.md`). Read that as a
regression check, not as accuracy: the extractor's rules and the generator's
templates describe the same sentences.

The first run that day reported precision 0.909 (132 predicted, 120
labelled). Every one of the 12 "false positives" was a planted obligation the
*label builder* had missed: it matched templates with literal spaces, and the
PDF wraps long sentences across lines. The matcher now accepts any
whitespace; the labels went from 120 to 132.

On real text there are no reviewed labels, so there is no metric. As a
qualitative check, the extractor found 4,978 obligation sentences in the 17
ingested SEBI documents (1,575 in the Master Circular for Stock Brokers). In a
random sample of 15 (seed 20261015, judged by the model that drafted this
page, so provisional), all 15 were genuine obligation sentences, but the
recorded actor named the obligated party in only 7: passive sentences yield
the object ("This report shall be placed…"), pronouns need coreference
("They shall also ensure…"), and leading headings or adverbials stick to the
subject ("Order Tracking – The system auditor…").

Quote location is not a
metric but a gate: every finding's quotes are re-found in the circular and the
clause, and a quote that cannot be found makes the finding `FAILED` with the
quote kept for inspection. **Quote location shows that quoted text exists; it
does not show that the verdict drawn from it is right.** That question is the
semantic-support review below, and it has not been run.

## Real-source evaluation (prepared, not run)

`data/real_sources/manifest.jsonl` lists 18 official SEBI documents chosen by
a recorded rule; 17 are ingested into a separate database. 39 candidate
relevance records (33 questions) were drafted by a model while reading the
passages and are marked `provisional`. `python -m evaluation.annotation
evaluate` reads reviewed records only, so it reports nothing until a person
has reviewed them. See
[evaluation/datasets/real/README.md](../evaluation/datasets/real/README.md).

These are retrieval-relevance labels: reviewing them would measure whether
search finds the passage that answers a question. They say nothing about
whether an assessment's rationale is supported by its evidence.

## Semantic-support review (prepared, not run)

`evaluation/support_review.py` is a separate workflow for that question. It
exports findings whose quotes were located, with the exact rationale, impact
classification, both quotations with offsets, document checksum and context,
and the generator (provider, model, graph version, deterministic or real
model), and binds every human review to a hash of that snapshot, so a review
of evidence that later changed no longer counts. Reviews record a named human,
a time and one of `supported`, `unsupported` or `insufficient`; anything else
is rejected, never read as approval. The report counts only valid, current
reviews and keeps insufficient-or-ambiguous ones and every denominator
visible; with no reviews it says nothing is measured.

As of 2026-10-17, 45 candidates are exported: 41 from eight deterministic
runs and four from Groq `openai/gpt-oss-20b` smoke run
`07525384-7c53-4301-ba5f-28f0bdb7a2ff`, all on the synthetic corpus. Human
review remains pending and results must be separated by generator. AI-assisted
annotations are not independent human validation. A model judge can later be compared with the human labels
(raw agreement and Cohen's kappa, undefined rather than 1.0 when both raters
never vary); none is implemented. See
[evaluation/datasets/support/README.md](../evaluation/datasets/support/README.md).

## Reproducing

```bash
make db seed              # the synthetic demo database
make gold                 # gold set + the 60-citation sample manifest (already committed)
make eval-retrieval       # four modes on the manifest; stores results for the UI
make eval-fast            # fast modes on every query
python -m evaluation.report
```

Each result directory holds `per_query.jsonl` (one row per mode and query) and
`summary.json` (metrics, intervals, paired differences, error examples, and the
provenance block: commit and a digest of any uncommitted evaluated source,
model revisions, threshold, data checksums, machine, timing method).

## The CI gate

The pull-request gate (`make eval-gate`) runs hybrid retrieval over every
gold query of the 60-document corpus CI builds and fails if Recall@10 or
MRR@10 drops more than 0.03 below `evaluation/baseline.json`. The baseline
records the gold file it was measured on and the gate refuses to compare
against a different one. The reranked mode is not in the PR gate; it is
measured by the manual evaluation workflow.
