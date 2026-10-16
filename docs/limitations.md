# Limitations

What RegDelta does not do, or does not yet show, stated plainly.

## Scope

- **Single user, one machine.** No authentication, no multi-tenancy, no
  hosting configuration. The API binds to loopback and Compose publishes every
  port on loopback. Exposing it to a network would expose unauthenticated
  endpoints that can start metered model calls.
- **Not legal advice.** Findings are aids for an analyst who accepts or
  rejects them. An analyst's decision is a workflow record, not an
  independent research annotation.
- **SEBI-shaped.** Reference formats, supersession language and the manual's
  structure are modelled on SEBI and a broker; other regulators would need
  their own parsing rules.

## Data

- **The demo corpus is synthetic.** 300 circulars generated from eight topic
  templates. Each carries a visible "[SYNTHETIC CORPUS - NOT A REAL SEBI
  CIRCULAR]" banner, and the interface labels it. The manual is fictional.
- **The real-source corpus is small and unlabelled.** 18 official SEBI
  documents chosen by a recorded title rule from the first listing page of
  Circulars and of Master Circulars (fewer than the 20–30 aimed for; later
  pages are only reachable through the site's JavaScript form). One of them
  has no text layer and needs OCR. The PDFs are not redistributed; the
  manifest records URLs and checksums.
- **No OCR without a model.** Pages with no usable text take a vision-model
  path, which needs a provider key. The deterministic demo does not read them.

## Evaluation

- **Relevance labels are template-derived.** The retrieval gold set comes
  from the synthetic corpus's citations, which its generator wrote. They are
  not human judgements; every query has exactly one relevant circular even
  when a sibling would also answer it.
- **Synthetic results do not bound real performance.** They are neither a
  floor nor a ceiling for retrieval on real circulars; that is unmeasured.
- **The reranked mode is measured on a sample.** At a median of 56 seconds
  per query on the evaluation laptop's CPU (under load; see the run's
  README), the four-mode comparison uses a fixed sample of 120 labelled
  queries plus the 30-question refusal suite rather than all 1,324. The fast
  modes are also run on every query.
- **The refusal suite is small.** 15 questions to refuse and 15 on-topic
  controls: 15 of 15 refused and 0 of 15 controls refused still leaves a 95%
  interval of roughly 0.80–1.00 and 0.00–0.20. The threshold was not tuned
  on it, and near-miss questions (a SEBI topic the corpus lacks) are absent.
- **Scores are not probabilities.** The cross-encoder's sigmoid output and
  any model-stated score are uncalibrated; no calibration has been measured.
- **Quote checks are not correctness checks.** A located quote proves the
  text exists in the source, not that the impact judgement is right. Whether
  findings are supported by their evidence has not been reviewed: the
  semantic-support workflow and 41 exported candidates (deterministic judge,
  synthetic corpus) are ready, and no human has reviewed them.
- **Human review of the real-source labels is pending.** The candidate
  annotations are model-drafted and provisional by design; no metric is
  reported on them until a person reviews them. They are retrieval-relevance
  labels, so reviewing them would not measure semantic support.

## Engineering

- **Remote CI has not run on this revision.** The workflows were exercised
  locally with the same commands; the hosted run happens after review and
  push.
- **Reranking is slow on CPU.** A reranked search took a median of 62 s on
  the evaluation laptop on 2026-10-16 (eight queries, load average up to 8,
  swap full), against 0.10 s for Hybrid, which is the default mode; the search
  page shows a running clock and Cancel for the reranked mode. Cancel stops
  the browser waiting, not the server: the reranking it started runs to the
  end. An identical reranked search sent meanwhile (a reload, a retry, a
  second tab) joins that computation instead of queueing another, and a
  finished one is reused for five minutes. `RETRIEVE_TOP_N=20` made reranking
  about 2.4 times faster (25.7 s median) but changed the top 10 on half the
  queries, and its recall has not been measured, so the default stays 50
  ([the benchmark](../evaluation/results/latency/2026-10-16-rerank-bench/README.md)).
- **Master circulars are too large to assess whole on a CPU.** The rule
  extractor finds hundreds to over a thousand obligations in one master
  circular, and clause retrieval reranks for each; the run's wall-clock and
  call limits stop it (`CAPPED`, findings so far kept) long before the end.
  Assessment is practical for ordinary circulars, not consolidated ones.
- **Long assessments run in the API process.** A run is a background task of
  the server; a restart fails any run in progress (it is marked FAILED at
  startup, never left RUNNING).
- **Light theme only.** A dark theme would need every state, contrast pair and
  chart verified, which has not been done, so none is offered.
