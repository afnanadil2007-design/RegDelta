# RegDelta repair — completion report

Review handoff for the 2026-10 repair and frontend overhaul. The evidence
for every claim is in the [ledger](regdelta-cleanup-ledger.md); resumable
state is in [`regdelta-cleanup-state.json`](regdelta-cleanup-state.json).

## 1. Status

**Ready for human review.** Every locally verifiable engineering and design
gate passed. Three items need something this task could not supply: human
annotation (F07), a provider key (G02), and a push for remote CI (G04). None
of them is reported as passed.

Principal changes:

- **The repo builds and migrates again.** `.gitignore:25` (`models/`) had
  silently excluded `backend/app/db/models/`, which was never committed. The
  package was rebuilt from the migrations and checked against them by an
  autogenerate parity test. The ignore rules are now anchored, and a test
  fails if model sources are ignored again.
- **Domain bugs reproduced and fixed:**
  - `as_of` removed amended circulars from force.
  - The citation graph duplicated edges on rebuild.
  - Run token caps were checked only after the fan-out.
  - Unlocated quotes were stored as verified.
  - Confidences were invented (0.4, 0.5, 0.55).
  - Unpriced models were shown as $0.
  - The trace stream never re-sent completed steps.
  - Duplicate launches raced.
- **The interface was rebuilt** around the evidence a reviewer checks:
  - the "law lexicon" design;
  - findings index, two document leaves with located quotes and a travelling arrow, verdict plate, and a decision bar that stays pessimistic;
  - every route and state at 1440/1024/768/390 px and 200% zoom;
  - axe-clean.
- **The evaluation can be trusted:**
  - four modes on one fixed manifest, with provenance (code identity and dirty digest, model revisions, data hashes, machine);
  - refusal measured separately with its denominators;
  - cluster-bootstrap and Wilson intervals;
  - an 18-document official corpus with a provisional-label annotation workflow;
  - two measurement bugs caught and fixed along the way.
- **Reproducible delivery:**
  - one Linux `make` workflow;
  - locked dependencies;
  - CI split into fast gates, a hybrid gate on a fixed corpus, and E2E;
  - an E2E suite against the real API, a disposable DB and the deterministic judge, with inspected screenshot baselines.
- **The final verification pass found and fixed six more defects:**
  - `make setup` installed with a bare `python` before the venv existed (`d0b57a8`).
  - `make e2e-db` failed on a fresh clone (`74a1182`).
  - The MCP check dropped `POSTGRES_*` and connected to the default database (`7984056`).
  - Keyboard focus could land beneath the sticky top bar, against WCAG 2.4.11 (`178660b`).
  - Circular numbers in prose broke mid-segment on phones (`eb0325f`).
  - A visual baseline depended on how long the run took (`c3ca32f`).

  The clean-clone run (§4, row 6) covers all of them.

## 2. Branch and working tree

- Repository `/home/afnan/Downloads/Reg-Delta/RegDelta`, local branch
  `repair/regdelta-cleanup`.
- Base `f4a4b57edc5807b5c1ec57072b04db6b8f619ead`. The last code commit is `2c54739`; the commit that adds this report follows it and touches only `docs/maintenance/` (§9).
- There were no pre-existing user changes: the tree was clean at the base,
  with no stash and a single worktree.
- **Nothing was pushed, deployed, merged or opened as a PR.** No remote was
  changed and no history was rewritten.
- Containers and volumes were left alone:
  - untouched: `regdelta-postgres-1`, `regdelta_pgdata`, `ai-trading-*`, `jarvis-*`, and the uvicorn on `0.0.0.0:8000`;
  - all work used the disposable container `regdelta-repair-pg` on `127.0.0.1:55432`;
  - one exception: before its fix, the MCP check's server subprocess tried `127.0.0.1:5432` (your `regdelta-postgres-1`) with the default credentials. Authentication was refused, so nothing was read or written.

**One side effect to undo.** The Impeccable finish reviewer (a subagent) ran
`impeccable concept-seed`, which overwrote the git-ignored
`.impeccable/questions/roll.json`: the direction-round record, key `54afe040`,
was replaced by a surface roll, key `b2e730e3`. The reviewer's own attempt to
restore it was blocked by the permission check. I did not repeat that write,
because doing so would get around the block. The original content is saved
at `.artifacts/impeccable-roll-original.json`. Restore it with:

    cp .artifacts/impeccable-roll-original.json .impeccable/questions/roll.json

## 3. Ledger

**63 verified, 3 blocked, 0 pending, 0 in progress, out of 66.**

| Section | IDs and status |
|---|---|
| A. Recoverable baseline | A01 ✓, A02 ✓, A03 ✓, A04 ✓, A05 ✓ |
| B. Missing source and reproducibility | B01 ✓, B02 ✓, B03 ✓, B04 ✓, B05 ✓, B06 ✓, B07 ✓ |
| C. Backend and agent correctness | C01 ✓, C02 ✓, C03 ✓, C04 ✓, C05 ✓, C06 ✓, C07 ✓, C08 ✓, C09 ✓, C10 ✓ |
| D. Clean, readable implementation | D01 ✓, D02 ✓, D03 ✓, D04 ✓, D05 ✓, D06 ✓, D07 ✓, D08 ✓, D09 ✓ |
| E. Frontend overhaul | E01 ✓, E02 ✓, E03 ✓, E04 ✓, E05 ✓, E06 ✓, E07 ✓, E08 ✓, E09 ✓, E10 ✓, E11 ✓, E12 ✓, E13 ✓, E14 ✓, E15 ✓, E16 ✓ |
| F. Evaluation and research evidence | F01 ✓, F02 ✓, F03 ✓, F04 ✓, F05 ✓, F06 ✓, F07 **blocked**, F08 ✓, F09 ✓, F10 ✓ |
| G. Demonstration, CI and delivery | G01 ✓, G02 **blocked**, G03 ✓, G04 **blocked**, G05 ✓, G06 ✓, G07 ✓, G08 ✓, G09 ✓ |

✓ = verified: a command or inspection recorded in the ledger row produced the stated result.

Non-verified IDs:

| ID | Status | Why | Smallest external prerequisite |
|---|---|---|---|
| F07 | blocked | Semantic-support evaluation only counts reviewed labels. All 39 real records are model-drafted and marked provisional, so `annotation evaluate` reports 0 reviewed. The mechanics are tested on synthetic fixtures. | A person reviews the 39 records (`python -m evaluation.annotation review`). |
| G02 | blocked | No provider key in this session, so the real-model smoke check was **not run**. All durable tests use the deterministic provider at the provider boundary. | A key and one real-model assessment run. |
| G04 | blocked | Every CI job's commands were run locally (§4). The hosted runs need a push, which this task does not authorise. | Push the branch and read the CI run's four jobs (`backend`, `retrieval-gate`, `frontend`, `e2e`). |

## 4. Verification

All checks below ran locally on this machine, Ubuntu with Linux 6.14,
an i5-5300U and 7.6 GiB of RAM. The machine was shared with other workloads
and swap was often full, so latencies are upper-biased. No real-provider
check ran, and remote CI is pending.

There were two clones:

- **Clean clone:** a fresh `git clone` of the branch into the scratchpad
  (`clean2`), with `.env` copied from `.env.example` and only the port and
  database name changed.
- **CI clone:** an earlier clone (`clean`) at `6c2cb18`, used for the
  60-document CI corpus so the 300-document demo data was not overwritten.
  No backend, ingestion or evaluation code changed after it; the only change
  in those areas is the baseline file it produced.

| # | Check | Command | Where / commit | Result | Evidence |
|---|---|---|---|---|---|
| 1 | Install from lockfiles | `make venv install` | clean clone, `d0b57a8` | Pass. The venv equals `backend/requirements.lock` (143 packages; names normalised). `npm ci` added 391 packages. The first attempt failed: `make setup` used a bare `python` before the venv existed. Fixed in `d0b57a8`. | `.artifacts/logs/clean-clone/setup.log` |
| 2 | Python lint and format | `make lint` (ruff check, ruff format --check) | clean clone, `d0b57a8` | Pass: 0 findings, 150 files formatted | `…/clean-clone/lint-typecheck.log` |
| 3 | Types | `make typecheck` (mypy `app/ai`) | clean clone, `d0b57a8` | Pass: no issues in 27 files | same |
| 4 | Backend unit and integration tests | `prepare_db` on a new `regdelta_clone_test`, then `pytest -q -rs` | clean clone, `d0b57a8`. No backend, ingestion, evaluation or MCP file changed after it. | **307 passed, 0 skipped, 0 failed** (64 s). The main tree on `regdelta_test` gave the same: 307 passed, 272 s under load. | `…/clean-clone/pytest.log`, `.artifacts/logs/pytest-final.log` |
| 5 | Frontend gates | `make test-frontend` (eslint, prettier --check, `tsc -b`, vitest, vite build) | clean clone, `2c54739` | Pass. Vitest **32/32** in 8 files. Main JS 342.5 kB (105.8 kB gzip); lazy Evaluation chunk 379.7 kB; CSS 27.8 kB | `…/clean-clone/frontend.log` |
| 6 | End-to-end | `REGDELTA_E2E_DB=regdelta_clone_e2e make e2e-db e2e` (API 8030, web 4181): generated corpus, fresh DB, real API, production build, deterministic judge | clean clone, `2c54739` | **21/21 passed** in 3.0 min, including axe on every route, the focus sweep, the real reranked refusal (57 s) and all six visual baselines. Regenerating the corpus left the tracked files byte-identical. | `…/clean-clone/e2e-db.log`, `…/clean-clone/e2e.log` |
| 7 | End-to-end, main tree | `npx playwright test` against `regdelta_e2e` | main tree, before `178660b` | 18/20. Two **real failures found**: keyboard focus hidden under the sticky bar (axe target-size), and the 390 px baseline moved by variable masked text. Both were fixed (`178660b`, `c3ca32f`). After the fixes: 20/21 with the new test, the only failure being the expected 390 px baseline. That baseline was inspected and accepted, then passed. | `.artifacts/logs/e2e-final.log`, `e2e-final2.log` |
| 8 | MCP server over STDIO | `python -m mcp_server.test_mcp_client` (`make mcp`) | main tree, `regdelta_demo` | Pass: 3 tools discovered and all invoked, and an unknown circular returns a readable error. The first attempt hit the default port 5432 because the check dropped `POSTGRES_*`. Authentication was refused there, so no data was read or written. Fixed in `7984056`. | `.artifacts/logs/mcp-check.log` |
| 9 | CI retrieval gate | `prepare_db`, `seed --count 60`, `check_baseline` | CI clone, `regdelta_ci` (and a reseed) | Pass. Reseeding gave the same gold sha. | ledger F10 |
| 10 | CI suites | `build_extraction_labels --count 30`, `run_suites --suite extraction`, `--suite refusal` | CI clone, `regdelta_ci` | Extraction P = R = 1.000 (132/132). Refusal 15/15 correct, 0/15 false. 36 min 42 s. | `.artifacts/logs/ci-suites.log` |
| 11 | Dependency audit | `npm audit`, `npm audit --omit=dev` | clean clone | **Not clean.** Production: 2 moderate, both `react-router-dom` 6.x (open redirect via `<Link>`/`useNavigate`). Dev tooling: 2 critical, 13 high, 5 moderate, 2 low (vitest 2, vite 5, tailwind's chokidar/braces, typescript-eslint). Same majors as the base; nothing was upgraded (B05). See §9. | — |
| — | Real-provider smoke | — | — | **Not run**: no provider key (G02) | — |
| — | Remote CI | `.github/workflows/{ci,evaluation}.yml` | — | **Pending**: needs a push (G04). Every job's commands ran locally (rows 2–10). | — |

## 5. Screenshots

The same synthetic workflow, before (`f4a4b57`) and after:

| Step | Before (`docs/screenshots/before/`) | After (`docs/screenshots/after/`) |
|---|---|---|
| Overview | `overview-desktop.png` | `overview-1440.png` |
| Circular detail | `circular-detail-desktop.png`, `circular-detail-mobile.png` | `circular-detail-1440.png`, `circular-detail-390.png` |
| Search | `search-results-desktop.png` | `search-1440.png`, `search-refused-1440.png` |
| Assessment evidence | `assessment-evidence-desktop.png` | `workspace-1440.png`, `workspace-390.png`, `workspace-decided-1440.png` |
| Point in time, evaluation | (not captured before) | `point-in-time-1440.png`, `evaluation-1440.png` |

`workspace-capped-failed-1440.png` is a **simulated state**, served by route
interception, and is labelled as such in the after README.

What was inspected:

- System Chrome 151 through the Playwright library, and Playwright Chromium
  1234 for the tests.
- Nine routes at 1440, 1024, 768 and 390 px, plus 200% zoom (720 CSS px at
  DPR 2): no console errors, no horizontal overflow, no off-viewport elements.
- Loading, empty, error, refused, capped, disconnected and unavailable-provider
  states.

Unresolved, recorded rather than fixed:

- **Surface-brief drift.** The findings index is 300 px; the brief says about
  330 px. The measure cap is 62ch, but three columns at 1440 set 49–57
  characters.
- **Screenshot baselines.** They were rendered on this machine, so the hosted
  runner may rasterise fonts differently. The first remote run may need the
  same inspect-then-accept step.
- **Accessibility.** No screen-reader session was run; the axe scans are
  automated only.
- **Reranked search is slow.** It takes tens of seconds on this CPU, and the
  UI shows a clock and Cancel.
- **One after-screenshot predates a fix.** `docs/screenshots/after/workspace-390.png`
  was taken before `eb0325f`, so its memo still breaks the circular number
  mid-segment. The E2E baseline
  `frontend/e2e/__screenshots__/visual.spec.ts/workspace-390.png` shows the
  current wrapping.

## 6. Measured evaluation

All numbers come from committed result files: `evaluation/results/retrieval/*/summary.json`
and `per_query.jsonl`, plus `evaluation/baseline.json`.
`docs/evaluation-results.md` is generated from them.

**Four-mode ablation** (`results/retrieval/2026-10-15-ablation/`).

The set is 120 labelled queries: 60 semantic and 60 identifier, from a
fixed manifest (`retrieval_sample.json`, seed 20261015). The refusal suite
is 15 out-of-scope questions plus 15 on-topic controls. Intervals are 95%:
a cluster bootstrap by citing circular for ranking, and Wilson for the
refusal suite. "Never" means the mode has no threshold.

| Mode | Recall@10 | MRR@10 | Out-of-scope refused | Controls refused (false) | Labelled refused | p50 / p95 latency |
|---|---|---|---|---|---|---|
| Dense | 0.250 (0.169–0.341) | 0.074 (0.044–0.111) | never | never | never | 48 ms / 73 ms |
| Lexical | 0.658 (0.603–0.716) | 0.353 (0.299–0.404) | never | never | never | 5 ms / 11 ms |
| Hybrid (RRF) | 0.650 (0.589–0.708) | 0.388 (0.333–0.446) | never | never | never | 47 ms / 58 ms |
| Hybrid + rerank | **0.758** (0.700–0.820) | **0.545** (0.513–0.579) | 15/15 (0.80–1.00) | 0/15 (0.00–0.20) | 0/120 | **55.5 s / 117.3 s** |

Paired differences on the same 120 queries:

| Comparison | Recall@10 | MRR@10 |
|---|---|---|
| Rerank − hybrid | +0.108 (+0.059 to +0.164) | +0.157 (+0.108 to +0.201) |
| Rerank − lexical | +0.100 (+0.051 to +0.155) | +0.192 (+0.146 to +0.242) |
| Hybrid − lexical | −0.008 (−0.026 to 0.000) | +0.036 (−0.010 to +0.082) |

Fusion does not beat lexical retrieval on this corpus, and the report says
so.

**Fast modes on every query** (`results/retrieval/full-fast/`): 1,324
queries, code `87ccc92` (clean).

| Mode | Recall@10 |
|---|---|
| Dense | 0.274 |
| Lexical | 0.695 |
| Hybrid | 0.665 |

Hybrid − lexical: −0.030 (−0.044 to −0.018).

**CI corpus** (60 generated documents, gold sha256 `2ca4eefa…`, measured in
a clean clone):

- Hybrid baseline: Recall@10 0.9713 and MRR@10 0.5031 on 244 queries
  (`cad9ccf`). The gate passes, with tolerance 0.03.
- Extraction suite (`rules-v2`): precision and recall both 1.000, 132 of
  132. This is a regression check, because the labels come from the same
  templates the generator uses.
- Refusal suite (reranked): 15 of 15 out-of-scope questions refused, 0 of 15
  controls refused. The run took 36 min 42 s.

**Provenance of the ablation:**

- **Code.** The process loaded `8f72b88` and recorded `9b50ce0` at the end
  (clean). Only `persist()` differs, as the run's README documents. Identity
  has been recorded at the start of a run since then. The summary was
  recomputed from the stored rows at `87ccc92` (`--resummarise`, clean),
  without rerunning retrieval.
- **Models.** `BAAI/bge-small-en-v1.5` at `5c38ec7c`, and
  `BAAI/bge-reranker-base` at `2cfc18c9` (a sigmoid over one logit, not
  calibrated).
- **Configuration.** RRF k = 60, top-n = 50, cutoff 10. The threshold is
  0.35, the configured default, not tuned on this sample.
- **Data.**
  - Synthetic corpus of 300 circulars in `regdelta_demo`.
  - Gold set sha256 `a15a3c88…`; out-of-scope set sha256 `798316f8…`.
  - Relevance is one cited circular per query, derived from the templates.
- **Machine.** Intel i5-5300U (4 threads), 7.6 GiB of RAM, CPython 3.11.16,
  torch 2.14.1+cpu, sentence-transformers 3.4.1.

**Limitations:**

- The labels are template-derived, and the corpus has eight near-duplicate
  templates.
- Latency was measured on a shared laptop with swap full. Reranked medians
  drifted from 46 s to 102 s across the run.
- The refusal suite is small, so its intervals are wide.
- The threshold is not tuned and the reranker scores are not calibrated.

**Real corpus:**

- Obtained: 18 official SEBI documents, against an initial target of 20–30.
  17 were ingested; one is a scan with no text layer.
- 33 candidate questions (39 records), against an initial target of 40–60.
- Every label is model-drafted and marked provisional, and 0 are reviewed.
  So **no real-corpus retrieval or semantic-support number is claimed**
  (F07).

## 7. Plugins, skills and fallbacks

| Tool | Used for | Notes |
|---|---|---|
| Impeccable 4.5.2 (`impeccable:impeccable`, commit `2f98774f86bc`) | `context`, init (PRODUCT.md), direction round (the user chose the law lexicon), shape, critique, audit, harden, polish, `detect`; subagents `impeccable-finish-reviewer` (3 rounds + confirmation → ship) and `impeccable-documenter` (DESIGN.md + `.impeccable/design.json`) | Side effect on `roll.json` (§2). The plugin ships its own detector hook (it runs after Edit/Write) as part of the installed plugin. This task added or changed no hook configuration. |
| Taste (`design-taste-frontend`, Leonxlnx/taste-skill) | Lint, inspection and critique of the old UI (E01) | The skill says it is not for app screens, so only findings that fit an analyst tool were applied. |
| Awesome Design | The named `veeralspatel/awesome-design-skill` is **not installed** | Fallback: the installed `design-md` skill (`moesuito/claude-skill-design-md` @ `aeddb0d`), plus VoltAgent/awesome-design-md reference files read without installing anything. |
| Playwright MCP | — | **Fails to connect.** Its `npx` resolves the system Node 18.19.1, and Playwright needs Node ≥ 20. Host fix, not made by this task: point the server's `command` at `~/.nvm/versions/node/v22.23.2/bin/node`, or prepend that `bin` to its `PATH`, then reconnect with `/mcp` or restart the host. |
| Fallback browser tooling | `playwright-cli` for interactive inspection; the Playwright library for captures; `@playwright/test` for E2E, axe and visual tests | — |
| Chrome DevTools MCP | — | Fails to connect; not needed. |
| img2threejs | — | Not installed and not guessed; no 3D was added. |

## 8. Launch, reproduce, review

Demo (Linux, Python 3.11, Node 20, Docker):

    cp .env.example .env          # set POSTGRES_PORT if 5432 is taken
    make setup                    # postgres container, venv from the lockfile, npm ci
    make db seed                  # synthetic corpus, graph, manual, embeddings, obligations
    make dev-api                  # terminal 1: 127.0.0.1:8000, deterministic judge
    make dev-web                  # terminal 2: http://127.0.0.1:5173

**On this machine, do not run `make up`, `make setup` or `make down`.**

- Your `regdelta-postgres-1` was created by this compose file from
  `/home/afnan/Downloads/RegDelta`, under project `regdelta`, service
  `postgres`. This checkout has the same project name.
- So compose would adopt or recreate that container and attach your
  `regdelta_pgdata` volume, and `make down` would remove the container.
- Ports 5432 and 8000 are also taken by that stack.

Use the disposable container and other ports instead:

    cp .env.example .env          # then set POSTGRES_PORT=55432, API_PORT=8010 (and POSTGRES_DB as you like)
    make venv install             # instead of make setup
    make db seed
    make dev-api                  # API on 127.0.0.1:8010
    REGDELTA_API_URL=http://127.0.0.1:8010 make dev-web

`regdelta-repair-pg` is labelled `owner=regdelta-repair-session` and was
started by hand, not by compose. Its databases are disposable.

Checks:

    make lint typecheck           # ruff, ruff format --check, mypy app/ai
    make test-backend             # pytest on regdelta_test (created and migrated)
    make test-frontend            # eslint, prettier --check, tsc, vitest, vite build
    make e2e-db e2e               # disposable regdelta_e2e + Playwright against the real API
    make mcp                      # MCP discovery and invocation over STDIO
    POSTGRES_DB=regdelta_ci make db && POSTGRES_DB=regdelta_ci python -m ingestion.seed --count 60 \
      && POSTGRES_DB=regdelta_ci make eval-gate   # the CI retrieval gate

Five-minute review sequence:

1. **0:00 — the fix that unblocked everything.** Read `941d9d1`, the restored
   ORM package, and run
   `backend/tests/test_model_migration_parity.py`.
2. **1:00 — the reviewer's screen.** Open a run in the workspace. Arrow
   through findings, Accept one, then reload: the decision persists. Check the
   plate's quote status ("Quotes located") and the score wording.
3. **2:30 — a domain bug.** Read `tests/test_api.py::test_as_of_hides_superseded_circulars_but_not_amended_ones`,
   then go to Point in time on 1 Dec 2024 and on 11 Dec 2024.
4. **3:30 — the evaluation.** Read
   `evaluation/results/retrieval/2026-10-15-ablation/README.md` and
   `docs/evaluation.md`: rerank beats lexical by +0.100 Recall@10, but costs
   about 55 s a query here, and hybrid does not beat lexical.
5. **4:30 — what is not claimed.** Read `docs/limitations.md` and the three
   blocked rows in §3.

## 9. Remaining external steps and commits

External steps:

1. Restore `roll.json` (§2).
2. Fix the Playwright MCP host config if you want it (§7).
3. Have a person review the 39 provisional real-corpus records, then run
   `python -m evaluation.annotation evaluate` (F07).
4. Run one real-provider assessment with a key (G02).
5. Push the branch and read the CI run: jobs `backend`, `retrieval-gate`,
   `frontend` and `e2e` (G04). `evaluation.yml` is manual (`workflow_dispatch`).
   If the visual baselines differ on the runner, inspect them before accepting.
6. Decide on dependency upgrades. All are outside this task, which upgraded
   no runtime package:
   - `react-router-dom` 6 → 7 for the 2 moderate production advisories;
   - vitest, vite, tailwind and typescript-eslint for the dev-tool
     advisories (§4, row 11).

Local commits on `repair/regdelta-cleanup`, oldest first:

| Commit | Subject |
|---|---|
| `941d9d1` | fix(db): restore the ORM package lost to an unanchored ignore rule |
| `14b28d7` | chore: normalize line endings to LF and pin them with .gitattributes |
| `55c4605` | style: one ruff config for all Python; apply ruff format |
| `90e039c` | fix(backend): truthful evidence states, bounded runs, and a resumable trace |
| `0ad571c` | feat: product and design records, separated corpora, rules-v2 extraction |
| `26967ea` | fix(backend): keep the quote that could not be located on a FAILED finding |
| `8f72b88` | feat(evaluation): one query manifest for all four modes, with provenance |
| `2e7c739` | feat(data): an official SEBI corpus and a reviewable annotation workflow |
| `1e3d85b` | build: one Linux workflow from a fresh clone, locked deps, and split CI |
| `9b50ce0` | fix(evaluation): label wrapped obligations; never truncate provenance |
| `87ccc92` | fix(evaluation): score refusal controls as false refusals, not correct ones |
| `72ab9e1` | data(evaluation): four-mode results on the sample, fast modes on every query |
| `45e0990` | feat(frontend): rebuild the interface around the evidence a reviewer checks |
| `83b4282` | test(e2e): accept inspected screenshot baselines; keep status icons with their text |
| `4a6e97c` | fix(frontend): place the evidence arrow by CSS; finish-review round 2 |
| `9fd4af5` | build: lint and format-check the frontend in CI and make test-frontend |
| `a61af00` | fix(frontend): a shared search link runs its search after a remount |
| `3749009` | docs(design): record the design system as shipped |
| `6c2cb18` | docs: concise README and docs that match the code and the measurements |
| `6ce5fed` | feat(frontend): the evidence arrow travels to the next mark again |
| `cad9ccf` | data(evaluation): hybrid retrieval baseline for the CI gate |
| `7984056` | fix(mcp): pass the caller's environment to the server in the MCP check |
| `d0b57a8` | fix(build): resolve the venv interpreter when each target runs |
| `74a1182` | fix(build): make e2e-db works on a fresh clone |
| `178660b` | fix(frontend): keep keyboard focus clear of the sticky top bar |
| `eb0325f` | fix(frontend): circular numbers in prose wrap after a slash |
| `c3ca32f` | test(e2e): pin the run's duration text in the workspace baseline |
| `2c54739` | build: let make e2e-db and make e2e take REGDELTA_E2E_DB |
| (next) | docs(maintenance): ledger closed, state and completion report |

Each commit stages explicit paths only. Every staged diff was scanned for secrets before committing, and no commit contains pre-existing user changes (there were none).
