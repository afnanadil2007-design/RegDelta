# ADR 0004 — Postgres full-text search instead of Elasticsearch

Status: accepted

## Context

Half the retrieval workload is lexical. SEBI reference numbers
(`SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2023/17`) are exact identifiers where
embedding similarity is close to useless — the ablation shows dense retrieval
scoring 0.14 Recall@5 against lexical's 0.60 on this corpus. A strong keyword
retriever is not optional here.

## Decision

Use Postgres full-text search: a `tsvector` generated column on `chunks.text`
with a GIN index, queried with `websearch_to_tsquery` and ranked with
`ts_rank_cd`.

## Alternatives considered

**Elasticsearch / OpenSearch.** Rejected. It is a better search engine in the
abstract — BM25, better analyzers, richer query DSL. But adopting it means a
second datastore with its own JVM, memory profile, backup story, and
deployment surface, plus a synchronisation problem: chunks would be written to
Postgres and indexed into Elasticsearch, and those two can drift. Every drift
bug is a correctness bug in an application whose whole premise is verifiable
provenance. It also breaks the composed filter (ADR 0001) for the same reason
a dedicated vector store does.

**SQLite FTS5.** Rejected: we already run Postgres for pgvector.

**BM25 in Python (rank_bm25).** Rejected: the index would live in process
memory, be rebuilt per process, and not compose with SQL filters.

## Consequences

**What we gain.** One datastore. The `tsv` column is `GENERATED ALWAYS AS
(to_tsvector('english', text)) STORED`, so it *cannot* drift from the text it
indexes — there is no trigger to forget and no sync job to fail. Lexical and
dense search apply the identical `WHERE` clause, so RRF fuses comparable
candidate sets. Lexical search is also by far the cheapest mode measured (1.1s
for 50 queries against 82s for dense).

**What it costs.**

- `ts_rank_cd` is not BM25. It has no document-length normalisation and no
  saturation term, so it ranks worse than a real BM25 implementation on long
  documents. RRF partly absorbs this because fusion uses ranks, not scores.
- The `english` configuration stems English and drops English stop words. It
  has no analyzer for Indian-language terms and no domain lexicon.
- Reference numbers survive tokenisation only because of how `/`-separated
  tokens split; a change to the reference format could degrade lexical recall
  silently. The 40-reference regex fixture guards extraction, not indexing.
- No phrase-slop, no fuzzy matching, no per-field boosting.

The honest summary: we accepted a measurably weaker ranking function in
exchange for removing an entire class of consistency bug and one whole service.
The ablation is how we know the cost is acceptable.
