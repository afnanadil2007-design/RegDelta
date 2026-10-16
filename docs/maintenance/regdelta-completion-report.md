# RegDelta release repair — completion report

Review handoff for the focused release repair of 2026-10-16 (R01–R11),
which followed an independent review of the `0dc9437` package. The first
version of this report, for the 66-item cleanup, is in git at `0dc9437`.
Evidence for every claim is in the [ledger](regdelta-cleanup-ledger.md)
(R01–R11 section and the corrections table), the recorded
[results](regdelta-release-results.json), and the logs packaged under
`review-evidence/`.

## 1. Status

**A release candidate for independent review, not yet releasable.** Every
locally achievable R item is done and verified except R04, which needs a
human decision. Outstanding, and not reported as passed:

- **R04, dependency advisories:** one high npm advisory with no patched
  release (braces, through Tailwind 3), and 24 Python advisories whose
  fixes are framework majors; each is assessed as not reached by RegDelta's
  code paths in [dependency-advisories.md](dependency-advisories.md), but
  a written assessment is not a passed gate.
- **External evidence:** human review of the 39 retrieval-relevance
  records and of the 41 semantic-support candidates (F07); one capped
  real-provider run (G02); hosted CI after an authorised push (G04). No
  demo video was recorded.

## 2. Branch, revisions, safety

- `repair/regdelta-cleanup`, local only. Commits since the previous review
  revision `0dc9437`: see §8. **Tested application revision `bd1e82d`.**
  The package manifest's code revision is `73f680c`, the last commit outside
  `docs/maintenance` and `docs/screenshots`; it differs from `bd1e82d` only
  in `scripts/package_review.py` (what goes into the ZIP). The commit after
  it records evidence only.
- Native final pass on `207f466` (it differs from `bd1e82d` only in
  `frontend/nginx/default.conf.template`, which no native check uses);
  container final pass on `bd1e82d`.
- Nothing was pushed, merged, deployed, published or opened as a PR; no
  remote or history was changed (`origin/main` is still `f4a4b57`).
- No existing data was touched. Every container and volume that existed
  before (`regdelta-postgres-1` and `regdelta_pgdata`, `ai-trading-*`,
  `jarvis-*`, and this repair's own `regdelta-repair-pg`) had the same id,
  state and creation time before and after each container run (diff 0
  lines). New resources: compose project `regdelta-r2acc` (containers
  removed by `make down`; volumes `regdelta-r2acc_pgdata` and
  `regdelta-r2acc_modelcache` kept), images `regdelta-r2acc-api` (2.52 GB)
  and `regdelta-r2acc-web` (95.5 MB), and disposable `regdelta_r2_*` and
  `regdelta_guard_*_test` databases inside `regdelta-repair-pg` (the guard
  tests drop theirs). No paid model request was made.

## 3. R01–R11

| ID | Status | Proof |
|---|---|---|
| R01 container path | verified | nginx serves the build and proxies `/api` to `api:8000`. Through http://127.0.0.1:8081: walk 17/17 (JSON 404s for unknown and bare `/api`, deep links serve the app, 422 passes through, assessment, unbuffered SSE over 43–54 s, evidence, decision persisted after reload) and the full Playwright suite 21/21, on three revisions. Stopping the API gives 502 `api_unreachable` and the UI's unreachable notice; the final pass found that right after a stop nginx returned a misleading 504 after 60 s, fixed in `bd1e82d` (3 s, 502). |
| R02 reproducible images | verified | `npm ci` and `pip install --no-deps -r requirements.lock` + `pip check`; image packages equal the lock (143 pins); one-stage API image with an honest size comment; web image without Node; ignore files exclude env files, caches, venvs, node_modules, screenshots. Base images pinned by tag, digests recorded. |
| R03 isolation | verified | `name: regdelta-local`; `make stack-check` refuses taken ports and another stack's containers or volumes (checked against the real host); acceptance under `regdelta-r2acc` touched nothing else; `prepare_db` and `seed` refuse foreign databases; precedence documented and observed (the container keeps port 8000 and its own postgres whatever `.env` says). |
| R04 advisories | **blocked** | npm full tree 24 → 9 (critical 2 → 0); remaining high braces has no patched release. pip-audit (new): 24 in 8 packages, all assessed, model revisions pinned as a mitigation. Needs a human decision. |
| R05 semantic support | verified (review pending) | Separate snapshot-bound workflow; 23 tests; 41 candidates exported and validated; report says nothing is measured; kappa undefined when degenerate. |
| R06 wording | verified | Memo "whose quotations were found in their sources" (no "verified"); quote check "Each quote was found verbatim in its source"; failed quotes no longer "unverified"; tests and inspected screenshots. |
| R07 slow retrieval | verified | Hybrid default 0.10 s; rerank 62.4 s median under load; repeat requests share one computation; Cancel documented honestly; length sorting and 20 candidates measured and not adopted. |
| R08 CI path | verified (hosted run pending) | Runs on pushes to `repair/**`; `ubuntu-24.04`; web image + `nginx -t`; model cache keyed by revision; actionlint clean; every job's commands run locally. |
| R09 clean-source acceptance | verified | Final pass in a clean clone with its own venv (the lock, hardlinked by uv) and `npm ci`: all checks in §4. Fixed on the way: stale PDFs joining a corpus (`ce18f45`), unpinned model revisions (`68d893b`), `make e2e-db` reusing a 60-PDF corpus (`207f466`), the proxy's stopped-API answer (`bd1e82d`). |
| R10 UI evidence | verified (no screen reader) | Baselines inspected and accepted; screenshots refreshed at 1440/390; 200% zoom 0 overflow on six routes; ARIA tree captured; no console errors; Impeccable `detect` 0. No screen-reader session was run. |
| R11 package | verified | §5. |

Original 66 IDs: **63 verified, 3 blocked (F07, G02, G04)**, unchanged in
count; the ledger's corrections table amends B05, B06/B07, E14, E15, F07,
G02, G04, G08 and G09. In particular the earlier claim that reviewing the
39 records would unblock semantic support was wrong: they are retrieval
labels.

## 4. Verification

Native, clean clone, revision `207f466`, fresh databases on the disposable
server:

| Check | Result |
|---|---|
| `make lint typecheck` | pass: ruff 0 findings, 168 files formatted, mypy 0 issues (27 files) |
| `make test-frontend` | pass: eslint, prettier, tsc; Vitest 36/36 (9 files); build 344.44 kB JS (106.70 kB gzip) |
| pytest on new `regdelta_r2_final_test` (migrated from empty) | **354 passed, 0 failed, 0 skipped** |
| retrieval gate on new `regdelta_r2_final_ci` (60 circulars) | pass: Recall@10 0.9713 (baseline 0.9713), MRR@10 0.5026 (0.5031), tolerance 0.03 |
| extraction suite | pass: P = R = 1.000 (132/132) |
| refusal suite (at `ce18f45`) | pass: 15/15 refused, 0/15 controls refused, 23 min 15 s |
| `make e2e-db` after the CI seed | pass: 300 circulars regenerated, tracked corpus files byte-identical |
| `make e2e` (own API + production build) | **21/21** |
| `make mcp` | pass |

Containerised, project `regdelta-r2acc`, revision `bd1e82d` (and earlier
on `867cb8a` and `207f466`): `make stack-up` from the clean clone, `nginx
-t`, acceptance walk **17/17**, Playwright through nginx **21/21**, API
outage 502 `api_unreachable`, `make down`, resource diff 0.

Failures found and fixed during the repair (each kept in the results
file): two visual baselines (intended wording, inspected, accepted), the
retrieval gate's correct refusal of a corpus polluted by stale PDFs, and
the 504 for a just-stopped API.

Audits: npm production 2 moderate, full 9 (5 high from one braces
advisory); pip-audit 24 in 8 packages. Workflows: actionlint 0 findings.

Not run: a screen-reader session, the real-provider smoke run, hosted CI,
the human reviews, a demo recording.

## 5. Screenshots and package

- Current screenshots: `docs/screenshots/after/` (workspace at 1440 and
  390, decided, simulated capped/failed, memo; earlier pages unchanged),
  visual baselines in `frontend/e2e/__screenshots__/`, container acceptance
  captures in `review-evidence/container*/`.
- Package: `RegDelta-review-v2.zip` beside the repository, built by
  `python3 scripts/package_review.py --previous 0dc9437 --results
  docs/maintenance/regdelta-release-results.json --out
  ../RegDelta-review-v2.zip`. It holds `git archive HEAD` plus
  `review-evidence/` (redacted logs, audits, container results and images,
  the diff `0dc9437..73f680c`, the commit list, and `MANIFEST.json` with
  UTC time, revisions, tool versions, the results table and a SHA-256 per
  entry). The ZIP's own size and SHA-256 cannot be inside it; they are in
  `RegDelta-review-v2.zip.sha256` beside it.

## 6. Launch, reproduce, review

```bash
cp .env.example .env          # pick free POSTGRES_PORT / API_PORT / WEB_PORT
make stack-check              # what Docker will touch; refuses conflicts
make setup && make db seed    # this checkout's postgres, venv, npm ci, demo data
make dev-api                  # terminal 1
make dev-web                  # terminal 2, http://127.0.0.1:5173
# or in containers:
make stack-up                 # http://127.0.0.1:$WEB_PORT
make down
```

A 10-minute review sequence:

1. `review-evidence/logs/final/summary.txt` and
   `logs/final-container/summary.txt`: every step of the final pass.
2. `frontend/nginx/default.conf.template` with
   `logs/final-container/accept-walk.log` and `api-outage.log`.
3. `scripts/stack_check.py` with `logs/container-acceptance/
   stack-check-before-up.log` and the `identity-*.txt` files.
4. `docs/maintenance/dependency-advisories.md` (the R04 decision).
5. `evaluation/support_review.py` and
   `evaluation/datasets/support/README.md`.
6. `docs/screenshots/after/workspace-memo-1440.png`.
7. `evaluation/results/latency/2026-10-16-rerank-bench/README.md`.

## 7. External steps

1. Decide R04: accept the documented exposures, or schedule Tailwind 4 and
   the FastAPI/sentence-transformers/transformers/LangGraph upgrades as
   measured changes of their own.
2. Review the 39 retrieval-relevance records
   (`python -m evaluation.annotation review --reviewer "Name"`) and,
   separately, the 41 semantic-support candidates
   (`python -m evaluation.support_review review --reviewer "Name"`).
3. With a key and explicit authorisation:
   `REGDELTA_ALLOW_PAID_CALLS=1 POSTGRES_DB=regdelta_demo make provider-smoke`.
4. After authorising a push of `repair/regdelta-cleanup`: read the four CI
   jobs (`backend`, `retrieval-gate`, `frontend`, `e2e`); inspect any
   screenshot diff in the uploaded report before accepting it.
5. Restore the Impeccable `roll.json` if wanted
   (`cp .artifacts/impeccable-roll-original.json .impeccable/questions/roll.json`),
   and remove the acceptance volumes and images when no longer needed
   (`docker volume rm regdelta-r2acc_pgdata regdelta-r2acc_modelcache`;
   `docker rmi regdelta-r2acc-api regdelta-r2acc-web`).

## 8. Commits since `0dc9437`

`git log --oneline 0dc9437..HEAD` (also `review-evidence/commits-since-0dc9437.txt`
with each commit's message and files).
