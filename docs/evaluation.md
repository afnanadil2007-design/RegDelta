# Evaluation

## What is measured, and how

| Suite | Ground truth | Status |
|---|---|---|
| Retrieval | mined from the corpus's citation graph (1,324 pairs) | **implemented and run** |
| Extraction | 120 labels over 30 circulars | **implemented and run** |
| Refusal | `out_of_scope.jsonl`, 30 cases | **implemented and run** |
| Groundedness L1 | programmatic span resolution | **enforced live + audited** |
| Latency / cost | `agent_steps` per node | **implemented**; needs an assessment to report on |
| Groundedness L2 | LLM judge, calibrated vs human labels | metric implemented, **not run** (needs a key + human labels) |

This table is deliberately honest about what exists. Everything marked
"implemented and run" produced numbers on this machine; the one unrun suite
says so and why.

Run them with:

```bash
make eval            # retrieval ablation + all other suites
make eval-suites     # extraction, refusal, groundedness, latency/cost only
make eval-gate       # the CI regression gate alone
```

## The corpus caveat, stated once and loudly

The measurements below were taken on a **synthetic corpus**
(`ingestion/generate_corpus.py`), not on real SEBI circulars.

`ingestion/scrape_sebi.py` targets the real sebi.gov.in listing, and the
listing page does yield circular links — but each detail page returns a
JavaScript shell with no reference number, date, or PDF link in the markup.
Fetching the real corpus therefore requires a headless browser, a dependency
this project deliberately does not take.

What this means for the numbers:

- **The pipeline is real.** The same `retrieve()` the UI and the agent call.
- **The gold set is real** in construction: relevance genuinely comes from
  resolved citations, not from a model's opinion.
- **The documents are not real.** They imitate SEBI reference formats,
  citation density, supersession language, and obligation phrasing, but they
  are generated from eight topic templates.

So these numbers are valid as a **comparison between retrieval modes on a
fixed corpus** — which is what an ablation is for — and invalid as an estimate
of retrieval quality on real SEBI text. Do not quote them as the latter.

## Retrieval

### Gold set

Built by `evaluation/build_gold_set.py` from resolved citations:

| | count |
|---|---:|
| Circulars | 300 |
| Resolved citations | 662 (100% of those found) |
| Supersession edges | 73 |
| **Gold pairs** | **1,324** |
| — semantic subset | 662 |
| — identifier subset | 662 |

A resolved citation is a human relevance judgement: the author of circular A,
writing paragraph P, decided circular B was relevant. Two subsets stress
different behaviour:

- **semantic** — query is P's prose *with the reference string removed*, so it
  cannot be solved by exact match.
- **identifier** — query is the raw reference string alone.

The 100% resolution rate is an artefact of a closed synthetic corpus in which
every reference points at a document that exists. A real corpus resolves lower,
and unresolved references are kept with `resolved=False` precisely so that rate
is visible rather than hidden.

### Ablation

See `evaluation/reports/retrieval_ablation.md` for the current table, generated
by `make eval`. Numbers are also written to `eval_runs` / `eval_results` with
the git SHA so trends are reconstructable.

### Results

50 queries per mode (stratified, fixed seed), 25 per subset.

| Mode | Subset | Recall@5 | Recall@10 | MRR |
|---|---|---:|---:|---:|
| dense | semantic | 0.120 | 0.240 | 0.103 |
| dense | identifier | 0.160 | 0.200 | 0.077 |
| dense | **all** | 0.140 | 0.220 | 0.090 |
| lexical | semantic | 0.320 | 0.480 | 0.153 |
| lexical | identifier | 0.880 | 1.000 | 0.659 |
| lexical | **all** | 0.600 | 0.740 | 0.406 |
| hybrid | semantic | 0.280 | 0.440 | 0.161 |
| hybrid | identifier | 0.880 | 0.960 | 0.590 |
| hybrid | **all** | 0.580 | 0.700 | 0.375 |
| hybrid_rerank | semantic | 0.400 | 0.520 | 0.179 |
| hybrid_rerank | identifier | **1.000** | **1.000** | **0.953** |
| hybrid_rerank | **all** | **0.700** | **0.760** | **0.566** |

### What the ablation actually shows

**1. The full pipeline wins, and the cross-encoder is the component that earns
it.** This is the load-bearing result. Reciprocal Rank Fusion *on its own* is a
slight regression against lexical alone (0.580 vs 0.600 Recall@5, 0.375 vs
0.406 MRR) — dense contributes so little on this corpus that blending it in
dilutes an already-good lexical ranking. Reranking the fused candidates
recovers that loss and goes past both: +0.12 Recall@5 and +0.19 MRR over
fusion, and +0.10 / +0.16 over lexical alone.

Read the identifier column for the mechanism: fusion ranks the right document
in the top 5 for 88% of queries but only puts it *first* 59% of the time
(MRR 0.590). The cross-encoder, reading query and passage together, lifts that
to 100% and 0.953 — it is not finding new documents, it is ordering the ones
fusion found. That is exactly what a reranker is for, and the ablation is how
we know it is doing its job rather than adding latency for nothing.

**2. Dense retrieval underperforms on both subsets.** 0.120 Recall@5 on the
semantic subset it was supposed to win is the surprise. Two causes: the corpus
is generated from eight topic templates, so hundreds of documents are near
paraphrases of each other and embeddings have almost nothing to separate them;
and document-level relevance means the "right" answer is one specific circular
among dozens that say nearly the same thing.

**3. The semantic ceiling of 0.400 is a corpus artefact, not a pipeline
limit.** With 300 documents drawn from 8 templates, "which margin circular does
this paragraph cite" is often genuinely undecidable from the text. Real
regulation is far more distinguishable. Treat the semantic column as a floor.

**The methodological conclusion**, which transfers even though the numbers do
not: report subsets separately, and never assume the dense retriever is doing
the work. A single blended number would have shown hybrid_rerank winning and
left the reader believing the embeddings were responsible.

### The cost of that win

| Mode | 50 queries |
|---|---:|
| lexical | 1.1s |
| hybrid | 35s |
| dense | 82s |
| hybrid_rerank | 97min |

The cross-encoder scores 50 passages per query on a 4-core CPU, which is three
orders of magnitude more expensive than lexical search for a 0.10 Recall@5
gain. Whether that trade is worth taking is a product decision — but it is now
a decision made against a number rather than a preference, and the `mode`
parameter means a latency-sensitive caller can choose `lexical` deliberately.

## Extraction

Scored by `evaluation/metrics/extraction.py` against 120 labels across 30
circulars, using the specified match rule: **overlapping span AND matching
actor**.

| Metric | Value |
|---|---:|
| Precision | 0.822 |
| Recall | 1.000 |
| F1 | 0.902 |

Overlap rather than exact span equality, because a model and an annotator
routinely disagree about whether a trailing clause belongs to the obligation
while agreeing entirely about which requirement is meant; scoring that as both
a false positive and a false negative measures nothing useful. Actor matching
is what keeps overlap from being too generous — a sentence binding two parties
holds two obligations, and a prediction that merges them matches neither.
Matching is greedy and one-to-one, so five near-duplicate predictions of one
obligation score one true positive and four false positives.

**What these numbers describe.** They score the **rules-mode** extractor
(`--mode rules`), which is the seeding path used to populate the demo database
without a provider key. Recall of 1.000 is expected: the regex is looking for
sentences a generator planted from a fixed template list. Precision of 0.822
is the informative half — the remaining ~18% are sentences that are
structurally obligations ("X shall …") but carry no requirement, mostly
citation and supersession language that the exclusion list does not catch.

The LLM path (`--mode llm`) is implemented with schema validation, one repair
attempt, and span resolution, but has not been scored here because it needs a
provider key. The metric is identical for both; only the predictions differ.

**Label provenance.** The labels are derived from the corpus generator's own
ground truth rather than from a human reading PDFs — see
`evaluation/build_extraction_labels.py`. That is correct for a synthetic
corpus and free, with one honest limit: it tests whether extraction finds
deliberately planted obligations, and cannot test judgement on genuinely
ambiguous sentences, because the generator produces none. On a real corpus this
step must be human annotation.

## Refusal

Scored over `evaluation/datasets/out_of_scope.jsonl`: 15 queries that should be
refused (other regulators, general knowledge, live market data, a prompt
injection attempt, nonsense) and 15 that should be answered (core corpus
topics). Two rates are reported separately because they trade off, and a single
"accuracy" hides which way the threshold is wrong:

- **correct-refusal rate** — of queries that should be refused, how many were.
- **false-refusal rate** — of queries that should be answered, how many were
  refused anyway.

A refusal here is the pipeline's explicit `below_threshold` signal, not a model
declining in prose.

| Metric | Before the reranker fix | After |
|---|---:|---:|
| Correct-refusal rate | 0.000 | **1.000** |
| False-refusal rate | 0.000 | **0.000** |

30/30 cases correct: every out-of-scope question refused, every in-scope
question still answered. Note what the "before" column is — not a threshold set
too loosely, but a threshold that could not fire at all. The `RELEVANCE_THRESHOLD`
of 0.35 was correct the whole time; the scores reaching it were not.

### What this suite caught

The first run scored a **0.000 correct-refusal rate**: the pipeline answered
all fifteen out-of-scope questions, including "What is the capital of France?".
The false-refusal rate was also 0.000, so it was not a threshold set too
aggressively — nothing was ever below threshold at all.

The cause was in `rerank()`. `sentence_transformers`' `CrossEncoder.predict`
already applies the model's own activation, and for this single-label model
that activation is a sigmoid — it returns calibrated 0..1 probabilities. The
code applied a *second* sigmoid on top. Measured directly:

| Pair | `predict()` | after the extra sigmoid |
|---|---:|---:|
| "capital of France?" vs a margin clause | 0.00004 | 0.50001 |
| "upfront margin collection" vs the same clause | 0.97158 | 0.72543 |

A second sigmoid is monotonic, so **the ordering it produces is identical** —
which is why the ablation above, measured through this bug, showed nothing
wrong. What it destroys is the *scale*: every score is compressed into
(0.5, 0.731), so nothing can fall below a 0.35 threshold and the refusal path
is dead code that still looks healthy.

One consequence needs checking rather than assuming, and it is **not yet
measured**. `hybrid_rerank` applies the threshold, and a refused query returns
no hits, so restoring real scores can only leave recall unchanged or *lower*
it — a gold query whose best passage now scores below 0.35 counts as a miss.
The ablation table above was measured *before* this fix. Re-measure it with:

```bash
python -m evaluation.run_eval --mode hybrid_rerank --sample 25   # ~20 min on 4 CPU cores
python -m evaluation.run_suites --suite refusal
```

If `hybrid_rerank` recall drops, the threshold is trading recall for refusal
accuracy, and `RELEVANCE_THRESHOLD` is the dial: lower it to recover recall,
raise it to refuse more aggressively. Update `evaluation/baseline.json` (via
`--write-baseline`) once you have settled on a value, since CI gates on it.

`evaluation/reports/evaluation_refusal.md` holds the post-fix refusal run
(1.000 / 0.000). `retrieval_ablation.md` is still the pre-fix ablation.

This is the argument for measuring refusal as its own suite rather than
trusting that a threshold works because retrieval scores look reasonable. No
recall or MRR number could have surfaced it. The fix removes the extra sigmoid;
`test_rerank_scores_span_the_full_zero_to_one_range` asserts an unrelated query
scores below the threshold and below 0.5, so the bug cannot return silently.

## Groundedness (layer 1)

Enforced in the graph, not measured after the fact. `judge_impact` must quote
verbatim; `verify_grounding` re-resolves both quotes against the source text
via `app/ai/extraction/spans.py`. A quote that does not resolve is retried up
to `MAX_VERIFICATION_RETRIES` and then **the claim is dropped** — never stored
with a guessed offset.

The same primitive is asserted over stored data:

| Assertion | Result |
|---|---|
| Every paragraph span resolves in `full_text` | 0 violations across the corpus |
| Every chunk span resolves in `full_text` | 0 violations |
| Every obligation span resolves | 0 violations / 1,500 obligations |
| Every obligation sits inside its paragraph | 0 violations |

## Cost and latency

Captured per node in `agent_steps` (`tokens_in`, `tokens_out`, `cost_usd`,
`latency_ms`), and per assessment on `assessments`. `AgentRunRepository.
node_latency_breakdown` aggregates by node. Pricing is tabulated in
`app/ai/pricing.py`; a model with no published price yields cost 0.0 **and a
warning**, so an unpriced model is visible rather than silently free.

Measured retrieval latency on a 4-core CPU box, for the whole evaluation run:

| Mode | 50 queries |
|---|---:|
| lexical | 1.1s |
| hybrid | 35.3s |
| dense | 81.8s |
| hybrid_rerank | ~20s/query (cross-encoder dominates) |

The cross-encoder is the cost centre by an order of magnitude. That is why the
ablation samples the gold set rather than running all 1,324 queries in every
mode, and why the sample size is printed in the report.

## Reproducing

```bash
make seed                      # corpus → ingest → graph → policy pack → embed → gold set
make obligations               # rules mode; no API key needed
python -m evaluation.run_eval --ablation --sample 25 --write-baseline
```

The corpus generator is seeded, so the corpus — and therefore every number — is
reproducible from the seed alone.

## CI gate

`.github/workflows/ci.yml` runs lint, typecheck, and the deterministic test
suites. The retrieval gate compares a fresh run against
`evaluation/baseline.json` and fails the build if Recall@10 drops more than 3
points below the committed baseline.
