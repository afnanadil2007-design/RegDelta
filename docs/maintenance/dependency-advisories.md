# Dependency advisories (2026-10-16)

What `npm audit` and `pip-audit` report for the committed lockfiles, what
was fixed, and, for every advisory left, the code path it needs and whether
RegDelta reaches it. An exposure note is an assessment for a human to check,
not a passed gate: these advisories remain open.

Raw outputs: `review-evidence/audit/` in the review package
(`npm-audit-{prod,full}-{before,after,final}.json`,
`pip-audit-requirements-lock.json`, `pip-audit-details.json` with CVSS
vectors from OSV).

## Frontend (`frontend/package-lock.json`)

| | Production | Full tree |
|---|---|---|
| Before (`0dc9437`) | 2 moderate | 24: 2 critical, 13 high, 7 moderate, 2 low |
| After `3dc1f57` (unchanged at the final revision) | 2 moderate | 9: 0 critical, 5 high, 4 moderate |

Fixed by the smallest compatible versions: react-router-dom 6.30.6
(GHSA-jjmj), vite 6.4.3 (server.fs.deny bypasses, optimized-deps `.map`
traversal, launch-editor, esbuild's dev-server CORS), vitest 4.1.11
(tinypool prototype pollution, critical; @vitest/mocker traversal; UI server
file read), eslint 9.39.5 and @eslint/js, typescript-eslint 8.70.1 (drops
fast-glob), source-map-js 1.2.2.

Remaining:

| Advisory | Package path | Severity | Fix | Reached here? |
|---|---|---|---|---|
| GHSA-vfj7-8cjw-p6xm, braces stack exhaustion on deeply nested brace patterns | tailwindcss 3.4.19 → chokidar 3.6.0 / micromatch 4.0.8 / fast-glob 3.3.3 → braces 3.0.3 (dev, build time) | high (reported as 5 entries: braces, chokidar, micromatch, fast-glob, tailwindcss) | **No patched braces release exists** (3.0.3 is the latest and is affected). Only Tailwind 4 drops the chain. | Tailwind expands the glob patterns in `tailwind.config.js` (`./index.html`, `./src/**/*.{ts,tsx}`) and watches the files they match. No user or network input reaches braces. Not reachable, but a high advisory without a fix: **needs a human decision** (accept, or migrate to Tailwind 4 with a full visual re-verification). |
| GHSA-rj75-hqrm-r3gf, postcss-selector-parser quadratic parsing | tailwindcss 3 → postcss-nested 6.2.0 → postcss-selector-parser 6.1.4 (dev) | moderate | 7.1.6; Tailwind 3 requires 6.x | Parses this repository's own CSS at build time. Not reachable by outside input. |
| GHSA-wrjc-x8rr-h8h6, open redirect via backslash in `<Link>`/`useNavigate` | react-router 6.30.6 (production) | moderate | 7.18.0 only | Every `<Link to>` and `navigate()` target is a constant path or a constant prefix plus an API-issued numeric id or UUID; no URL or user text becomes a navigation target. Not reached. |
| GHSA-337j-9hxr-rhxg, constructor injection via `deserializeErrors()` | react-router 6.30.6 (production) | moderate | 7.18.0 only | Runs only when a data router hydrates server-rendered state. The app uses `<BrowserRouter>` with no SSR. Not reached. |

React Router 7 (already prepared for by the v7 future flags in `main.tsx`)
would close the two production advisories; it is a major upgrade and was
not made in this repair.

## Python (`backend/requirements.lock`, 143 pins)

`pip-audit 2.9.0 -r backend/requirements.lock --no-deps` (OSV/PyPI data,
2026-10-16): **24 known vulnerabilities in 8 packages**. torch
`2.14.1+cpu` could not be audited (a local version, not on PyPI). pip-audit
gives no severities; the CVSS vectors below are from OSV.

| Package (locked) | Advisories | Fixed in | Reached here? |
|---|---|---|---|
| sentence-transformers 3.4.1 | CVE-2026-68770 (CVSS 9.8): loading a model **from an existing local directory** imports custom Python even with `trust_remote_code=False` | 5.6.0 (a major; v4 rewrote CrossEncoder, whose activation the refusal threshold depends on) | Models are loaded by Hub repository id, for which the trust gate holds. Reachable only if `EMBEDDING_MODEL`/`RERANKER_MODEL` are pointed at a local directory someone else controls. **Mitigated in `68d893b`**: both models are pinned to the measured commits, and `.env.example` warns against untrusted directories. Open until upgraded. |
| transformers 4.57.6 | CVE-2026-4372 (malicious `config.json` → kernel download via `AutoModelForCausalLM`), CVE-2026-1839 (`Trainer` RNG state), CVE-2025-14929 (X-CLIP conversion script), CVE-2026-5241 (LightGlue loading, 5.2.0), CVE-2026-9856 (`save_pretrained` chat-template path), CVE-2026-80047 (`load_custom_generate`) | 5.x (some none) | RegDelta loads two fixed BAAI encoders through sentence-transformers, now pinned by commit, and never trains, converts, saves, generates or loads causal-LM configs. Not reached by the code paths described. |
| starlette 0.46.2 | CVE-2026-48710 (Host header poisons `request.url.path`), CVE-2026-54282 (path not validated for `request.url`), CVE-2026-54283 (`request.form()` limits), CVE-2025-62727 (Range header DoS in `FileResponse`), CVE-2025-54121 (multipart DoS), CVE-2026-48818 (StaticFiles SSRF on Windows), CVE-2026-48817 (`HTTPEndpoint` method dispatch) | 0.47.2 to 1.3.1; FastAPI 0.115 requires starlette < 0.47 | No form or file upload endpoints, no `FileResponse`/`StaticFiles`, no `HTTPEndpoint`, `request.url.path` is only written to the log of an unhandled error, never used for a decision; the API binds to loopback. Not reached. Closing them means a FastAPI upgrade. |
| langgraph 0.2.76, langgraph-checkpoint 2.1.2, langgraph-sdk 0.1.74, langchain-core 0.3.86 | checkpoint/cache deserialisation RCE (CVE-2025-64439, CVE-2026-48775, CVE-2026-27794), SQLite checkpointer, SDK URL paths and auth (CVE-2026-48776, CVE-2026-104873), `load_prompt` path traversal (CVE-2026-34070), ChatOpenAI image SSRF (CVE-2026-26013) | langgraph 1.x / checkpoint 4.x / langchain-core 1.2.x | The graph is compiled without a checkpointer or cache (`build.py: graph.compile()`), the SDK and LangChain prompt loading and chat models are not used (prompts are this repository's markdown files). Not reached. |
| pytest 8.4.2 (dev) | CVE-2025-71176, predictable `/tmp/pytest-of-{user}` directories | 9.0.3 (pytest-asyncio 0.23 would need upgrading too) | Test runs only, on a single-user machine. Local exposure on shared hosts. |

None of these is fixed in this repair: every fix is a major upgrade of a
framework the measured behaviour depends on (FastAPI/Starlette,
sentence-transformers, transformers, LangGraph). They remain open for
human assessment and a separate, measured upgrade.
