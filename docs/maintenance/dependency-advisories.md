# Dependency advisories (scanned 2026-10-16)

What `npm audit` and `pip-audit` report for the committed lockfiles, what a
fix would take, and, for every advisory left, the code path it needs and
whether RegDelta reaches it. An exposure note is an assessment for a human
to check, not a passed gate: every advisory below is still open.

**Evidence** (all in `review-evidence/` in the review package):

- `audit/`: the raw scans, unedited. `npm-audit-{prod,full}-{before,after,final}.json`
  (npm 10.8.2, 2026-10-16 05:59 UTC); `pip-audit-requirements-lock.json` and
  `pip-audit.stderr` (pip-audit 2.9.0, `-r backend/requirements.lock
  --no-deps`, 2026-10-16 05:59 UTC); `pip-audit-details.json` (the same
  findings with CVSS vectors and summaries from OSV).
- `resolver/`: disposable resolver dry runs, 2026-10-16 ~14:00 UTC, uv 0.12.5
  (`uv pip compile`, Python 3.11, x86-64 Linux; nothing installed, no
  environment changed). The input is `backend/pyproject.toml`'s declared
  requirements plus the dev extras; each file holds the input, the exit code
  and the resolver's own output. `summary.json` collects them.
- Registry check, 2026-10-16 14:02 UTC: braces' latest release is 3.0.3
  (last published 2024-09-18); react-router-dom's latest 6.x is 6.30.6, the
  locked version.

Neither lockfile changed after these scans; the counts below are as of
2026-10-16 and will move as advisories are published.

## How a fix was classified

Each fix version comes from the raw scan. The dry runs then asked, in order:

1. **Upstream fix:** does the fixed release resolve within the ranges
   RegDelta declares? Then only the lock needs to change.
2. **Constraint conflict:** if not, does it resolve when only RegDelta's own
   range for that package is relaxed?
3. **Coupled changes:** if not, which other declared range has to change
   with it (shown with the versions the resolver then picks)?
4. **No fix:** the scan lists no fixed version.

## Frontend (`frontend/package-lock.json`)

| | Production | Full tree |
|---|---|---|
| Before (`0dc9437`) | 2 moderate | 24: 2 critical, 13 high, 7 moderate, 2 low |
| After `3dc1f57` (unchanged since; scanned again 2026-10-16) | 2 moderate | 9: 0 critical, 5 high, 4 moderate |

Fixed by the smallest compatible versions: react-router-dom 6.30.6
(GHSA-jjmj), vite 6.4.3 (server.fs.deny bypasses, optimized-deps `.map`
traversal, launch-editor, esbuild's dev-server CORS), vitest 4.1.11
(tinypool prototype pollution, critical; @vitest/mocker traversal; UI server
file read), eslint 9.39.5 and @eslint/js, typescript-eslint 8.70.1 (drops
fast-glob), source-map-js 1.2.2.

Remaining:

| Advisory | Package path | Severity | Fix (category) | Reached here? |
|---|---|---|---|---|
| GHSA-vfj7-8cjw-p6xm, braces stack exhaustion on deeply nested brace patterns | tailwindcss 3.4.19 → chokidar 3.6.0 / micromatch 4.0.8 / fast-glob 3.3.3 → braces 3.0.3 (dev, build time) | high (5 entries: braces, chokidar, micromatch, fast-glob, tailwindcss) | **No fix**: affected range `<=3.0.3`, and 3.0.3 is the latest braces release. npm's only suggestion is Tailwind 4.3.3, which drops the chain (a major, with a full visual re-verification). | **Scope exception.** The only brace patterns braces sees are this repository's own, in `tailwind.config.js` (`./index.html`, `./src/**/*.{ts,tsx}`), read at build time; no user or network input reaches it. Not reached, but a high advisory without a fix: **a human decision** (accept, or schedule Tailwind 4). |
| GHSA-rj75-hqrm-r3gf, postcss-selector-parser quadratic parsing | tailwindcss 3 → postcss-nested 6.2.0 → postcss-selector-parser 6.1.4 (dev) | moderate | 7.1.6, but Tailwind 3's postcss-nested requires 6.x (coupled: Tailwind 4) | Parses this repository's own CSS at build time. Not reachable by outside input. |
| GHSA-wrjc-x8rr-h8h6, open redirect via backslash in `<Link>`/`useNavigate` | react-router 6.30.6 (production) | moderate | **7.18.0** fixes it (`>=6.0.0 <7.18.0` affected; no 6.x release has the fix): constraint conflict, a major | Every `<Link to>` and `navigate()` target is a constant path, or a constant prefix plus an API-issued numeric id or UUID; no URL or user text becomes a navigation target. Not reached. |
| GHSA-337j-9hxr-rhxg, constructor injection via `deserializeErrors()` | react-router 6.30.6 (production) | moderate | **7.18.0** fixes it (`>=6.4.0 <7.18.0`): constraint conflict, a major | **Scope exception.** The vulnerable function runs when a data router hydrates server-rendered errors (SSR). SSR does not apply to Declarative Mode, and the app is Declarative: `<BrowserRouter>` in `frontend/src/main.tsx`, no data router, no SSR, no hydration data. Not reached. |

React Router 7.18.0 (prepared for by the v7 future flags in `main.tsx`)
closes both production advisories; it is a major upgrade and was not made.

## Python (`backend/requirements.lock`, 143 pins)

**24 known vulnerabilities in 8 packages** (pip-audit 2.9.0, 2026-10-16).
torch `2.14.1+cpu` could not be audited (a local version, not on PyPI).
pip-audit gives no severities; the CVSS vectors are from OSV.

| Package (locked) | Advisory | Fixed in (raw scan) | Category and dry-run result | Reached here? |
|---|---|---|---|---|
| langgraph-sdk 0.1.74 | CVE-2026-48776, unsafe URL path construction | 0.3.15 | **Upstream fix**: resolves within the declared ranges, but only because the resolver moves **langgraph back from 0.2.76 to 0.2.35**, the last 0.2 release that does not cap the SDK below 0.2. The same advisory on langgraph itself is not closed by that. | The SDK (a client for a LangGraph server) is not used. Not reached. |
| langgraph-sdk 0.1.74 | CVE-2026-104873, custom auth ignores `actions=` | 0.4.4 | Coupled: needs RegDelta's langgraph range changed (`<0.3` caps the SDK below 0.2); resolves with langgraph 1.2.15, langgraph-sdk 0.4.7 | Not used. Not reached. |
| langgraph 0.2.76 | CVE-2026-48776 (same advisory as above) | 0.3.15 | Constraint conflict: RegDelta declares `langgraph<0.3`. With only that range relaxed to `>=0.3.15,<0.4` it resolves to langgraph 0.3.34 with checkpoint 2.1.2, sdk 0.1.74 and langchain-core 0.3.86 unchanged | The SDK URL code is not used. Not reached. |
| langgraph 0.2.76 | CVE-2026-28277, the SQLite checkpointer | 1.0.10rc1 | Constraint conflict: with the range relaxed to `>=1.0.10` it resolves to langgraph 1.2.15, checkpoint 4.3.0, sdk 0.4.7, langchain-core 1.6.11 (a major across the family) | The SQLite checkpointer is a separate package that is not installed, and the graph is compiled without any checkpointer (`build.py: graph.compile()`). Not reached. |
| langgraph-checkpoint 2.1.2 | CVE-2025-64439, CVE-2026-27794, CVE-2026-48775 (checkpoint/cache deserialisation) | 3.0.0; 4.0.0; 4.1.1 | Coupled: langgraph 0.2 requires checkpoint `<3`; resolves with langgraph 1.2.15 (checkpoint 4.3.0) | No checkpointer or cache is configured. Not reached. |
| langchain-core 0.3.86 | CVE-2026-34070 (`load_prompt` path traversal), CVE-2026-26013 (ChatOpenAI image SSRF) | 1.2.22; 1.2.11 | Coupled: langgraph 0.2 requires langchain-core `<0.4`; resolves with langgraph 1.2.15 (langchain-core 1.6.11) | Prompts are this repository's markdown files; no LangChain prompt loading or chat model is used. Not reached. |
| sentence-transformers 3.4.1 | CVE-2026-68770 (CVSS 9.8), loading a model from an existing local directory imports custom Python even with `trust_remote_code=False` | 5.6.0 | Constraint conflict: RegDelta declares `<4`; with `>=5.6.0,<6` it resolves to 5.7.0 and brings transformers 5.20.1 and huggingface-hub 2.2.0. v4 rewrote CrossEncoder, whose activation the refusal threshold depends on, so it needs the evaluations re-run | **Mitigated, not patched** (C03): only the two measured Hub repositories at their pinned commits are accepted, at start-up and again at load time; a local path at the Hub name is refused; `trust_remote_code=False` is passed explicitly (`backend/app/core/model_sources.py`). Assumes the Hugging Face cache is trusted. Open until upgraded. |
| transformers 4.57.6 | CVE-2026-1839 (`Trainer` RNG state) | 5.0.0 | Coupled: sentence-transformers 3.x requires transformers `<5`; resolves with sentence-transformers 5.7.0 (transformers 5.20.1) | Never trains. Not reached. |
| transformers 4.57.6 | CVE-2026-4372 (malicious `config.json` → kernel download via `AutoModelForCausalLM`) | 5.3.0 | Coupled, as above | Loads two fixed encoders, never a causal LM. Not reached. |
| transformers 4.57.6 | CVE-2026-9856 (`save_pretrained` chat-template path) | 5.10.0 | Coupled, as above | Never saves a model. Not reached. |
| transformers 4.57.6 | CVE-2025-14929 (X-CLIP checkpoint conversion) | none listed | **No fix** | The conversion scripts are never run. Not reached. |
| transformers 4.57.6 | CVE-2026-5241 (LightGlue model loading; the advisory text names 5.2.0) | none listed | **No fix** | LightGlue is never loaded. Not reached. |
| transformers 4.57.6 | CVE-2026-80047 (custom generation code downloaded before consent) | none listed | **No fix** | Never generates text with transformers. Not reached. |
| starlette 0.46.2 | CVE-2025-54121 (multipart DoS) | 0.47.2 | Coupled: RegDelta's `starlette<0.47` and FastAPI 0.115's own `starlette<0.47`; resolves only with FastAPI changed, to fastapi 0.143.2, starlette 1.8.0 (fastmcp 3.4.8) | No form or file endpoints. Not reached. |
| starlette 0.46.2 | CVE-2025-62727 (Range header DoS in `FileResponse`) | 0.49.1 | Coupled, as above | No `FileResponse`. Not reached. |
| starlette 0.46.2 | CVE-2026-48710 (Host header poisons `request.url.path`) | 1.0.1 | Coupled, as above | `request.url.path` is only written to the log of an unhandled error, never used for a decision; the API binds to loopback. Not reached. |
| starlette 0.46.2 | CVE-2026-48817 (`HTTPEndpoint` method dispatch), CVE-2026-48818 (StaticFiles SSRF, Windows) | 1.1.0 | Coupled, as above | No `HTTPEndpoint`, no `StaticFiles`. Not reached. |
| starlette 0.46.2 | CVE-2026-54282 (path not validated for `request.url`) | 1.3.0 | Coupled, as above | As for CVE-2026-48710. Not reached. |
| starlette 0.46.2 | CVE-2026-54283 (`request.form()` limits) | 1.3.1 | Coupled, as above | No `request.form()`. Not reached. |
| pytest 8.4.2 (dev) | CVE-2025-71176, predictable `/tmp/pytest-of-{user}` directories | 9.0.3 | Constraint conflict: RegDelta declares `pytest<9`; relaxed, it resolves to pytest 9.1.1 but moves **pytest-asyncio from 0.23.8 back to 0.23.3**, the last 0.23 without a `pytest<9` cap (untested with pytest 9) | Test runs only, on a single-user machine. A local exposure on shared hosts. |

### Summary by category

- **Upstream fix within the declared ranges:** one, langgraph-sdk 0.3.15,
  and only by downgrading langgraph 0.2.76 → 0.2.35 (not adopted: it
  replaces the measured orchestration library to close an advisory in an SDK
  RegDelta does not use).
- **Constraint conflict, RegDelta's own range:** langgraph (0.3.15 is a
  minor step, 0.3.34; 1.0.10 is a major), sentence-transformers (5.x, a
  major with a behaviour change the refusal threshold depends on), pytest
  (9.x, with pytest-asyncio moved back).
- **Coupled changes:** starlette with FastAPI; langgraph-checkpoint,
  langchain-core and the second SDK advisory with langgraph 1.x;
  transformers 5.x with sentence-transformers 5.x; the frontend's
  postcss-selector-parser with Tailwind 4.
- **No fix published:** braces (npm) and three transformers advisories.

No upgrade was made in this repair: each one either changes a library the
measured behaviour depends on or, in the one in-range case, downgrades one.
They remain open for a human decision and a separate, measured upgrade.
