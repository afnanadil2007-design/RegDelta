# Architecture

## What the system does

Ingest SEBI circulars → extract obligations with verifiable source spans →
map each obligation onto an internal policy pack → produce cited findings an
analyst accepts or rejects. Point-in-time queries respect supersession. Every
retrieval decision is measured against a gold set mined from the corpus.

## Layering

Strict, one direction only:

```
routers/       HTTP only — Pydantic in, Pydantic out, zero business logic
   ↓
services/      orchestration: ingestion, citation graph, policy pack, assessment
   ↓
ai/            all model and retrieval logic
   ↓
repositories/  all SQL — no raw SQL exists outside this layer
   ↓
db/            models, session, migrations
```

Two rules that are enforced rather than encouraged:

- **No AI calls from routers.** A router that wants a model answer calls a
  service.
- **All LLM and vision calls go through `app/ai/gateway.py`.** No other module
  constructs a provider client. The gateway owns provider selection, model
  pinning, bounded concurrency, retries with exponential backoff, token
  counting, cost accounting, and per-call structured logging carrying the
  `run_id`. Three providers are wired: **deterministic** (the default: a
  rule-based judge, labelled as such everywhere it appears, that makes no
  network call and costs nothing), **Groq** (via its OpenAI-compatible
  endpoint) and **Anthropic**. The nodes stay provider-agnostic; request
  translation, structured-output shaping and error mapping live in the
  gateway. Cost is a *list-price estimate* from token counts, not a bill; a
  model missing from the price table reports its cost as unknown, never as
  zero. A missing key is reported by `/api/health` and refused by
  `POST /api/assessments` with a 503 naming the variable to set.

## Data flow

```
PDF ──pymupdf──▶ pages + quality score
                     │
        quality < threshold OR table-dominant
                     │yes                        │no
                     ▼                           ▼
              render 200dpi PNG            embedded text
              → vision model
                     └────────────┬────────────┘
                                  ▼
                       normalise → paragraphs
                                  ▼
                    full_text built FROM paragraphs   ← the offset contract
                                  ▼
                    chunks (whole paragraphs only)
                                  ▼
                    embeddings (bge-small, 384-d)
```

### The offset contract

`circulars.full_text` is the single normalised text of a circular. It is
**derived from** its paragraphs — each paragraph's text is appended to a buffer
and its `char_start`/`char_end` recorded as it goes — so

```
full_text[p.char_start:p.char_end] == p.text
```

is true *by construction*, not by bookkeeping that can drift. Every downstream
span — chunks, citations, obligations, finding evidence — is an offset pair
into that same string. An integration test asserts the invariant against the
database, not just in memory.

This is what makes "cited and verifiable" mean something: a finding's evidence
is not a quote the model produced, it is a range that resolves in the source.

## Retrieval

```
query
  ├─▶ dense   (pgvector cosine, HNSW)  ─┐
  │                                     ├─ RRF (k=60, ranks only) ─▶ top 50
  └─▶ lexical (tsvector, ts_rank_cd)   ─┘                              │
                                                                       ▼
                                                        cross-encoder rerank
                                                                       ▼
                                                        top 8 → threshold
                                                                       ▼
                                              hits, or an explicit refusal
```

Both retrievers apply the *same* metadata and `as_of` filter, so fusion
compares like with like. RRF uses ranks only: pgvector distances and
`ts_rank_cd` values are on incomparable scales, and any weighted-sum
normalisation would need recalibrating as the corpus changes.

In the reranked mode, a best cross-encoder score below `RELEVANCE_THRESHOLD`
(0.35) returns `below_threshold=True` with no hits. Callers must treat that as
a refusal; the API returns it as `refused` with the threshold and the top
score, and the UI shows it as one. The threshold applies to the reranked mode
only: cosine, `ts_rank_cd` and RRF scores are on scales it does not describe.
The cross-encoder's sigmoid output is a score in 0..1, not a calibrated
probability. Evaluation passes `apply_threshold=False` to measure ranking and
refusal from the same run.

The `mode` parameter (`dense` | `lexical` | `hybrid` | `hybrid_rerank`) exists
so the evaluation harness and the UI traverse **identical code**. An ablation
measuring a parallel implementation would measure the harness, not the product.

Reranking scores `RETRIEVE_TOP_N` (50) passages with the cross-encoder in a
worker thread, one search at a time (the tokenizer is not thread-safe): about
a minute per search on the evaluation laptop. The UI defaults to Hybrid and
shows a clock and Cancel for the reranked mode. Cancel only stops the browser
waiting; the thread cannot be interrupted and finishes. So the search service
shares identical reranked searches: one already running is joined rather than
started again behind it, and a finished one is reused for five minutes
(`app/services/search.py`). The evaluation calls the pipeline directly and is
never served from that cache.

### Point-in-time filtering

`as_of` excludes any chunk whose circular is taken out of force by a resolved
*supersedes* or *rescinds* edge effective on or before that date, and
restricts results to circulars issued by that date. An *amends* edge does not
remove anything: an amended circular stays in force as amended. An edge with
no recorded effective date is not applied, and the Point in time page says so
rather than guessing a date.

Reporting *what was hidden* takes a second query, and the reason is worth
stating because the obvious implementation is silently wrong: the retrievers
already apply the temporal predicate in SQL, so asking which of their results
were excluded always answers "none". `_temporal_exclusions` therefore re-runs
retrieval with the supersession predicate removed (keeping every other filter,
and skipping the reranker — the banner needs to say results were hidden, not
rank them), then asks which of those candidates are superseded. Those ids come
back in `excluded_by_temporal_filter`, and the UI shows a banner rather than
silently returning less.

## The agent

```
plan_assessment ──(Send per obligation)──▶ assess_obligation ──▶ synthesize_memo
                                                  │
                                     retrieve_clauses
                                          → judge_impact ◀──┐
                                          → verify_grounding┘ (≤ MAX_VERIFICATION_RETRIES)
```

The fan-out is a conditional edge returning a list of `Send(...)`, one per
obligation, because obligations are independent — assessing one tells you
nothing about the next. `findings` is `Annotated[list, operator.add]` because
those workers write the same state key concurrently; without the reducer the
last writer would silently win.

`judge_impact` must emit a Pydantic-validated `JudgedImpact`. A schema
violation gets one repair attempt with the validation error fed back, then
counts as a failed task. `verify_grounding` re-resolves both quoted spans
against the source. Each finding records one of three quote states, kept
apart from the verdict itself:

- `VERIFIED`: both quotes were found verbatim; offsets point at them. This
  proves the quoted text exists, not that the interpretation is right.
- `FAILED`: a quote was not found within the retry budget. The finding is
  stored, never shown as verified, with the reason and the quote that could
  not be located (`unlocated_quote`), and no guessed offset.
- `NOT_APPLICABLE`: retrieval found no clause above the threshold, so nothing
  was judged and no score is recorded.

Hard limits, all enforced and all configured:

| Limit | Setting | Behaviour |
|---|---|---|
| Verification retries | `MAX_VERIFICATION_RETRIES` | store the finding as `FAILED` |
| Model calls per run | `MAX_ASSESSMENT_CALLS` | checked before every call; mark `CAPPED`, keep findings |
| Tokens per run | `MAX_ASSESSMENT_TOKENS` | checked before every call; mark `CAPPED`, keep findings |
| Wall clock | `ASSESSMENT_TIMEOUT_SECONDS` | mark `CAPPED` with a stored reason, keep findings |
| Concurrent calls (process) | `LLM_MAX_CONCURRENCY` | a semaphore in the gateway |

Workers persist their own findings as they finish, so a cap or timeout keeps
completed work. A second launch of the same circular and manual while one is
running is refused (409, with the running run's id) under an advisory lock,
and runs left `RUNNING` by a dead process are marked `FAILED` at startup.

### The live trace

`GET /api/assessments/{run_id}/stream` is Server-Sent Events. Every connection
(and reconnection) starts with a `snapshot` of the whole trace; afterwards a
`step` event is sent whenever a step is created *or changes*, keyed by its
sequence number, so the client upserts rather than appends and a replayed or
duplicated event is harmless. The stream ends with `done` (terminal status),
`timeout`, or `error`; events carry increasing ids and a retry hint. The
client (`frontend/src/hooks/traceReducer.ts`) counts and ignores malformed
payloads and refreshes the stored run when the stream ends.

Every node execution is persisted to `agent_steps` with inputs, outputs,
tokens, and latency. That table is a product feature — it drives the live
timeline and the per-node cost breakdown — not debug logging.

Because obligations fan out concurrently, step numbers cannot be derived from
`MAX(agent_steps.seq)+1`: concurrent workers would read the same max and collide
on the `uq_agent_step_seq` unique constraint. Each step instead claims its number
with an atomic `UPDATE agent_runs SET next_step_seq = next_step_seq + 1 …
RETURNING` (see `AgentRunRepository.allocate_seq`), which serialises allocation
on the run row while leaving the actual work concurrent. The unique constraint
stays in place as a database-level safety net.

## Security

**The agent has no external-action tools.** Its only capability is read-only
retrieval over the local corpus and the policy pack. There is nothing a prompt
injection embedded in a circular could make the system *do*: no HTTP client, no
filesystem write, no email, no shell. The worst case for a malicious circular
is a wrong finding shown to an analyst who accepts or rejects it — and whose
evidence spans must still resolve against the source text.

Supporting measures:

- Retrieved document text is always delimited and labelled as data, with an
  explicit instruction that content inside the markers is never an instruction.
- All SQL is parameterised; raw SQL exists only in `repositories/`.
- No secrets in code. `.env` is gitignored; `.env.example` lists every variable
  with no values. Provider keys are `SecretStr` and never appear in reprs or
  logs.
- The API binds to `127.0.0.1` by default and Docker Compose publishes every
  port on loopback only; CORS allows the local web origin with GET and POST.
- Errors leave the API as one envelope (`{error: {code, message, detail}}`);
  unexpected exceptions are logged server-side and reach clients as a generic
  message.

**There is no authentication.** This is a deliberate scope decision for a
single-user local tool, not an oversight. Adding auth would mean users,
sessions, and an authorisation model on findings — none of which this product
needs. It is stated here and in the README so nobody deploys it assuming
otherwise.

## Components and why each exists

| Component | Why |
|---|---|
| `ai/gateway.py` | one chokepoint for cost, retries, concurrency, and provider swap |
| `ai/deterministic.py` | the rule-based demo judge behind the gateway |
| `ai/graph/budget.py` | the per-run call and token budget, checked before each call |
| `services/assessment_stream.py` | the snapshot-then-upsert SSE protocol |
| `ai/extraction/pdf.py` | decides text vs vision per page; vision is expensive |
| `ai/extraction/segment.py` | establishes the offset contract |
| `ai/extraction/chunking.py` | retrieval units that never split a paragraph |
| `ai/extraction/citations.py` | regex-first resolution; LLM only for ambiguity |
| `ai/extraction/spans.py` | quote → offsets, the primitive grounding rests on |
| `ai/retrieval/fusion.py` | RRF; ranks only, no score calibration |
| `ai/retrieval/pipeline.py` | the one retrieval path, shared by UI and eval |
| `ai/graph/` | the assessment control flow and its tracing |
| `repositories/search.py` | the only place retrieval SQL lives |
| `evaluation/` | gold set, query manifest, metrics, ablation, provenance, annotation workflow |
| `frontend/` | the analyst workspace; its design system is recorded in `DESIGN.md` |
| `mcp_server/` | exposes retrieval to any MCP client without integration code |
