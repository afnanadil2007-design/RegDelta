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
  pinning, retries with exponential backoff, token counting, cost accounting,
  and per-call structured logging carrying the `run_id`. Two providers are
  wired: **Groq** (the default, via its OpenAI-compatible endpoint through the
  `openai` client) and **Anthropic**. The nodes stay provider-agnostic — all
  request translation, structured-output shaping (strict JSON schema for the
  OpenAI-compatible path, `output_config` for Anthropic), and error mapping live
  in the gateway. Cost is a *list-price estimate* from token counts, not a
  billed amount, so a Groq free-tier run still reports a non-zero estimate.

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

Below `RELEVANCE_THRESHOLD` the pipeline returns `below_threshold=True` with no
hits. Callers must treat that as a refusal — the UI shows it as one.

The `mode` parameter (`dense` | `lexical` | `hybrid` | `hybrid_rerank`) exists
so the evaluation harness and the UI traverse **identical code**. An ablation
measuring a parallel implementation would measure the harness, not the product.

### Point-in-time filtering

`as_of` excludes any chunk whose circular is named by a resolved supersession
edge effective on or before that date, and restricts results to circulars
issued by that date.

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
plan_assessment ──(Send per obligation)──▶ assess_obligation ──▶ check_token_cap ──▶ synthesize_memo
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
records an extraction failure. `verify_grounding` re-resolves both quoted spans
against the source; a claim whose quote cannot be found is **dropped**, not
stored with a guessed offset.

Hard limits, all enforced and all configured:

| Limit | Setting | Behaviour |
|---|---|---|
| Verification retries | `MAX_VERIFICATION_RETRIES` | drop the unsupported claim |
| Token budget | `MAX_ASSESSMENT_TOKENS` | halt, mark the run `CAPPED`, keep findings |
| Wall clock | `ASSESSMENT_TIMEOUT_SECONDS` | mark `FAILED` with a stored reason |

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
  with no values.

**There is no authentication.** This is a deliberate scope decision for a
single-user local tool, not an oversight. Adding auth would mean users,
sessions, and an authorisation model on findings — none of which this product
needs. It is stated here and in the README so nobody deploys it assuming
otherwise.

## Components and why each exists

| Component | Why |
|---|---|
| `ai/gateway.py` | one chokepoint for cost, retries, and provider swap |
| `ai/extraction/pdf.py` | decides text vs vision per page; vision is expensive |
| `ai/extraction/segment.py` | establishes the offset contract |
| `ai/extraction/chunking.py` | retrieval units that never split a paragraph |
| `ai/extraction/citations.py` | regex-first resolution; LLM only for ambiguity |
| `ai/extraction/spans.py` | quote → offsets, the primitive grounding rests on |
| `ai/retrieval/fusion.py` | RRF; ranks only, no score calibration |
| `ai/retrieval/pipeline.py` | the one retrieval path, shared by UI and eval |
| `ai/graph/` | the assessment control flow and its tracing |
| `repositories/search.py` | the only place retrieval SQL lives |
| `evaluation/` | the gold set, the metrics, and the ablation |
| `mcp_server/` | exposes retrieval to any MCP client without integration code |
