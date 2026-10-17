# ADR 0003 — Mine the retrieval gold set from the corpus's citation graph

Status: accepted

## Context

Retrieval decisions (dense vs lexical vs fusion vs reranking, `k`, thresholds)
are only defensible if they are measured. Measuring needs labelled
(query, relevant-document) pairs. Hand-labelling a few hundred pairs is days of
work and has to be redone whenever the corpus changes.

## Decision

Derive relevance from resolved citations. When circular A's paragraph P cites
circular B, B is taken as relevant to what P is about. In a real corpus that
reflects an author's judgement; in the synthetic corpus the citations are
produced by the generator's templates, so the labels are template-derived and
must not be described as human relevance judgements. Either way the labels
come at corpus scale for free.

Two subsets, reported separately:

- **semantic** — the query is P's prose with the reference string *removed*.
  Answering it requires understanding the paragraph's subject.
- **identifier** — the query is the raw reference string alone. Answering it
  requires exact-token matching.

## Alternatives considered

**Hand-labelling.** Rejected as the primary source: too slow, and stale the
moment the corpus grows. Still the right tool for extraction and groundedness,
where no structural signal exists — those suites *are* hand-labelled.

**LLM-generated relevance judgements.** Rejected. Using a model to grade the
retrieval that feeds the same model's context is circular, and it measures
agreement with the judge rather than correctness.

**A public IR benchmark (BEIR, MS MARCO).** Rejected: it would measure
retrieval on someone else's corpus. Nothing about SEBI reference formats,
supersession language, or regulatory phrasing transfers.

## Consequences

**What we gain.** 1,324 labelled pairs from 662 resolved citations, regenerated
by one command whenever the corpus changes. The semantic/identifier split
turned out to be the most informative thing the harness produces: it shows
plainly that dense retrieval is weak on identifier queries and that lexical
retrieval carries most of the load on this corpus — a conclusion a single
blended number would have hidden.

**What it costs.**

- **Relevance is document-level, not passage-level.** A cited circular's chunks
  are all marked relevant, so Recall@k is really a document hit-rate. Fine for
  comparing modes; not a passage-ranking metric.
- **The labels are biased toward what authors cite.** Circulars that are
  relevant but never cited are invisible to this gold set. Recall against the
  *true* relevant set is therefore unmeasured and unmeasurable this way.
- **Incomplete labels inflate apparent errors.** A retriever returning a
  genuinely relevant but uncited document is scored as wrong.
- **It inherits the resolver's errors.** A mis-resolved citation becomes a
  wrong label. This is why unresolved references are kept and their ratio
  reported rather than silently dropped.

## Corpus caveat (important)

The measurements are taken on a **synthetic** corpus
(`ingestion/generate_corpus.py`). The pipeline, the metrics and the gold-set
construction are real; the documents and their citations are not. None of the
numbers is SEBI retrieval performance, and none is a floor or a ceiling for
it: how the pipeline would score on real circulars is unmeasured.

## Revision (2026-10)

- Labels name circulars by number, not by database id, so they survive a
  re-ingest (`evaluation/datasets/synthetic/retrieval_gold.jsonl`).
- Every mode answers the same fixed sample (`retrieval_sample.json`, 60
  citations, 120 queries), and the circular a query was taken from is removed
  from its own ranking: it contains the query verbatim and is never the cited
  document.
- A small real-source corpus (18 official SEBI documents) and an annotation
  workflow now exist for independent labels. Its candidate labels were drafted
  by a model and stay *provisional* until a person reviews them; no metric is
  reported on them before that. See `docs/evaluation.md`.
