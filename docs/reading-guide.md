# Reading guide

A route through the codebase that builds up in dependency order, so nothing
refers forward to something you have not seen. Roughly two hours end to end.

If you only have twenty minutes, read **§1**, **§3**, and **§7** — the offset
contract, the retrieval pipeline, and the agent graph are the three ideas the
rest of the system is arranged around.

---

## 1. The offset contract — start here

**Read:** `backend/app/ai/extraction/segment.py`, then
`backend/app/ai/extraction/spans.py`.

Everything downstream depends on one invariant:

```
full_text[paragraph.char_start:paragraph.char_end] == paragraph.text
```

`circulars.full_text` is not stored alongside its paragraphs — it is **built
from** them, appending each paragraph to a buffer and recording offsets as it
goes. That makes the invariant true *by construction* rather than by
bookkeeping that can drift.

Why it matters: a citation is not "the model said this quote appears" — it is a
character range that either resolves in the source or does not. `resolve_span()`
converts a quoted string to offsets or reports failure, and a quote that cannot
be located is **dropped** rather than stored with a guessed offset.

**Check yourself:** why does the system ask the model to *quote* rather than to
report character positions? (Models cannot count characters; they can copy text.)

## 2. The data model

**Read:** `backend/app/db/models/corpus.py`, then `backend/app/db/models/enums.py`.

Note `tsv` on `Chunk` — a Postgres *generated* column
(`GENERATED ALWAYS AS (to_tsvector(...)) STORED`). It cannot fall out of sync
with `text`, and there is no trigger to maintain.

The enums file holds a subtle one worth understanding: `pg_enum()` passes
`values_callable` so Postgres stores enum *values* (`"vision"`), not Python
member *names* (`"VISION"`). Without it, `vision_page_fraction()` compares
against `"vision"`, the database holds `"VISION"`, and the function silently
returns 0 forever. There is a regression test pinning the labels.

## 3. Retrieval — the core of the project

**Read:** `backend/app/repositories/search.py` (the only place retrieval SQL
lives), then `backend/app/ai/retrieval/fusion.py`, then `backend/app/ai/retrieval/pipeline.py`.

The order is fixed:

```
dense + lexical (same filters, in parallel)
   -> RRF (k=60, ranks only) -> top 50
   -> cross-encoder rerank    -> top 8
   -> threshold               -> hits, or an explicit refusal
```

Three decisions to understand:

- **RRF uses ranks, never scores.** pgvector cosine distances and `ts_rank_cd`
  values are on incomparable scales; any weighted sum would need recalibrating
  as the corpus changes.
- **Both retrievers apply the same filter**, so fusion compares like with like.
- **`mode` exists so evaluation and the UI traverse identical code.** An
  ablation measuring a parallel implementation would measure the harness.

Then read `_temporal_exclusions()` in the same file, which answers "what did
`as_of` hide?". The obvious implementation is silently wrong: the retrievers
already apply the temporal predicate in SQL, so asking which of *their* results
were excluded always answers "none". It re-runs retrieval with that predicate
removed.

## 4. Where measurement drove a decision

**Read:** `docs/evaluation.md`, especially "What this suite caught".

Two things here are the point of the whole project:

1. **The ablation table.** Fusion alone is a slight *regression* against lexical
   alone; the cross-encoder is what earns the win, at 97 minutes against 1.1
   seconds. The trade is defensible only because it was measured.
2. **The refusal bug.** `CrossEncoder.predict` already applies a sigmoid;
   applying a second one is monotonic, so ranking looks perfect and every
   retrieval metric stays healthy — while every score is compressed into
   (0.5, 0.731) and the refusal path becomes dead code. Correct-refusal went
   0.000 → 1.000 when removed.

The second is the more useful lesson: a metric that looks healthy can be
measuring the wrong property. Read `backend/app/ai/retrieval/reranker.py` and
the guard test in `backend/tests/test_retrieval.py`.

## 5. The gold set

**Read:** `evaluation/build_gold_set.py`, then `evaluation/metrics/retrieval.py`.

Labels are free at corpus scale: when circular A's paragraph cites circular B,
that is a human relevance judgement already in the text. Two subsets are
reported separately — **semantic** (the citing prose, reference stripped) and
**identifier** (the raw reference string) — because a blended number hides that
either retriever alone fails half the workload.

Its limits are stated in `docs/decisions/0003-citation-graph-gold-set.md`. Read
those too; knowing why a gold set is weak matters as much as having one.

## 6. The gateway

**Read:** `backend/app/ai/gateway.py`.

Every LLM and vision call goes through this one module — no other file
constructs a provider client. That is what makes retries, model pinning, token
counting, cost accounting, and per-`run_id` logging exist in exactly one place.

Two providers are wired: **Groq** (default; Groq's OpenAI-compatible endpoint
driven through the `openai` client) and **Anthropic**. Look at `_call_groq` /
`_call_anthropic` for the per-provider request translation, `_openai_strict_schema`
for how a Pydantic JSON schema is adapted to OpenAI-compatible strict structured
output, and `GatewayError.code` for the typed failure taxonomy (missing key,
invalid key, rate limit, timeout, …) the API surfaces to the analyst.

Note `max_retries=0` on the client: the module owns retries via tenacity, and
leaving the SDK's own retries on would make the effective count the *product*
of the two.

## 7. The agent

**Read:** `backend/app/ai/graph/state.py`, then `backend/app/ai/graph/nodes.py`, then `backend/app/ai/graph/build.py`.

```
plan_assessment --(Send per obligation)--> assess_obligation --> synthesize_memo
                                                 |
                                     retrieve_clauses
                                          -> judge_impact <---+
                                          -> verify_grounding-+  (<= MAX_VERIFICATION_RETRIES)
```

The shape is justified by the problem, not by fashion: obligations are
independent, so the fan-out is a conditional edge returning a list of `Send(...)`.
Because those workers write the same state key concurrently, `findings` is
`Annotated[list, operator.add]` — without the reducer the last writer silently
wins.

`verify_grounding` is the part worth studying: it re-resolves both quoted spans
against the source, and a claim whose quote cannot be found is dropped rather
than stored. That is grounding enforced programmatically, not requested politely
in a prompt.

## 8. The edges

- `backend/app/routers/` — HTTP only. No `app.ai` imports, no SQL. Compare
  `backend/app/routers/search.py` against `backend/app/services/search.py` to
  see exactly where the line sits.
- `mcp_server/` — exposes retrieval to any MCP client.
- `frontend/src/pages/` — start with `frontend/src/pages/Search.tsx` (shows
  per-retriever ranks) and `frontend/src/pages/ImpactAssessment.tsx` (renders
  the agent trace progressively over SSE).

---

## Things worth questioning

The project is not above criticism, and these are the honest weak points:

- **The corpus is synthetic.** sebi.gov.in renders circular detail pages
  client-side. Every measurement is a valid comparison *between modes on a fixed
  corpus*, not an estimate of real-world quality. The semantic subset tops out
  at 0.400 partly because 300 documents from 8 templates are genuinely
  near-duplicates.
- **The ablation samples 50 queries**, not all 1,324, because the cross-encoder
  costs ~20s per query on CPU.
- **Groundedness layer 2** (LLM judge with Cohen's κ) is implemented but never
  run — it needs a provider key and human labels.
- **The agent has never run end-to-end against a real model** in this
  environment, for the same reason.
- **No authentication**, deliberately. Stated in the README so nobody deploys it
  assuming otherwise.
