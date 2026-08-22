# ADR 0001 — PostgreSQL + pgvector instead of a dedicated vector database

Status: accepted

## Context

RegDelta needs dense vector search over ~300 circulars (a few thousand chunks
at production scale), lexical search over the same text, and relational
queries over a citation graph, a supersession graph, obligations, findings,
and evaluation runs. The temporal filter — "exclude circulars superseded on or
before this date" — is a join against the supersession table applied to the
*same* candidate set as the vector search.

## Decision

Use PostgreSQL 16 with the `pgvector` extension as the only datastore. Dense
search uses an HNSW index with `vector_cosine_ops`; lexical search uses a
Postgres `tsvector` generated column with a GIN index and `ts_rank_cd`.

## Alternatives considered

**A dedicated vector database (Pinecone, Weaviate, Chroma, Qdrant).** Rejected.
The decisive problem is not vector performance, it is the *filter*. The
`as_of` filter is defined by a join over supersession edges; the metadata
filters are over circular attributes. In a split architecture those live in
Postgres while the vectors live elsewhere, which forces one of two bad shapes:
pre-filter (fetch candidate ids from Postgres, pass a potentially huge id list
to the vector store) or post-filter (over-fetch from the vector store, then
discard, with no guarantee of filling top-k). Both are worse than a single
`WHERE` clause.

**Elasticsearch for both.** Rejected for lexical search specifically — see
ADR 0004 — and it would not remove the relational half of the schema.

**FAISS in-process.** Rejected: no persistence, no filtering, and the index
would have to be rebuilt and held in memory by every process that reads it.

## Consequences

**What we gain.** One connection string, one backup, one migration path, one
transaction boundary. A chunk and its circular are written in the same
transaction, so there is no window in which a vector exists for a document
that does not. Filters and vector search compose in SQL. `docker-compose` has
one stateful service.

**What it costs.**

- HNSW build time on a large corpus is slower than a purpose-built engine, and
  index parameters (`m`, `ef_construction`) are less tunable at query time.
- pgvector has no native sharding. This design is stated as single-user and
  local; a multi-tenant deployment at millions of vectors would need
  revisiting.
- Postgres holds both the OLTP working set and the vector index in the same
  buffer pool, so a large index competes for cache with ordinary queries.
- We are on pgvector's release cadence for ANN improvements.

At this corpus size those costs are theoretical and the operational
simplicity is immediate, which is why the trade is worth taking here and
would not necessarily be worth taking at 100x the scale.
