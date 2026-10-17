# RegDelta final corrections — report (C01–C05)

> **2026-10-17 update:** PR #1 merged at `4d090cc`; hosted backend,
> frontend, retrieval-gate and e2e passed on that commit (established handoff
> evidence). A Groq `openai/gpt-oss-20b` smoke passed; run
> `07525384-7c53-4301-ba5f-28f0bdb7a2ff`, four synthetic support candidates
> committed in `b4b3236`. Earlier statements below describe the historical
> pass, not current status. Human retrieval and semantic-support evaluation
> remain pending. See [the current handoff](final-handoff-2026-10-17.md).

Review handoff for the correction pass of 2026-10-16, which followed an
independent review of the `RegDelta-review-v2.zip` package (head `bd10a94`,
code `7602abd`). It fixes what had to be right before a real-provider run.
The per-item record is the ledger's [C01–C05 section](regdelta-cleanup-ledger.md#final-corrections-2026-10-16-c01c05);
results are in [regdelta-correction-results.json](regdelta-correction-results.json);
logs are under `review-evidence/c/` in the package. The release repair
before it is described in [regdelta-completion-report.md](regdelta-completion-report.md).

## 1. Status

| ID | Status | Implementation |
|---|---|---|
| C01 one database target | verified | `backend/app/core/config.py` (`database_target`, `describe_database`, `psycopg_args`), `backend/alembic/env.py`, `backend/app/db/session.py`, `backend/app/main.py`, `ingestion/prepare_db.py`, `ingestion/seed.py`, `evaluation/provider_smoke.py` (preflight), `scripts/stack_check.py`, tests `test_database_target.py`, `test_database_guards.py`, `test_migrations.py`, `test_provider_smoke.py` |
| C02 smoke success | verified (the paid run itself not executed) | `evaluation/provider_smoke.py`, tests `test_provider_smoke.py`, `test_assessment_limits.py`, `docs/demo-script.md` |
| C03 model-loading boundary | verified as a mitigation | `backend/app/core/model_sources.py`, `config.py` validators, `backend/app/ai/retrieval/{embeddings,reranker}.py`, tests `test_model_sources.py`, `.env.example` |
| C04 dependency and reseed evidence | verified | [dependency-advisories.md](dependency-advisories.md), `review-evidence/c/resolver/`, `review-evidence/c/logs/reseed-repro/` |
| C05 verification and package | verified | `review-evidence/c/logs/gate/`, `review-evidence/c/logs/gate2/`, `scripts/package_review.py` |

Still open, and not reported as passed: F07 (human reviews of 39
retrieval records and 41 semantic-support candidates), G02 (one real-provider
run), G04 (hosted CI), R04 (a human decision on the advisories). No
screen-reader session or demo recording was made.

## 2. The database contract (C01)

**Before:** `Settings.sqlalchemy_url` preferred `DATABASE_URL`, but
`prepare_db`'s safety check, its `CREATE DATABASE` and the printed target
read `POSTGRES_*`, while Alembic and the app used the URL. With both set,
the check could inspect one database and the migration write another; the
smoke preflight checked the `POSTGRES_DB` name and then queried the URL. The
URL was also assembled with an f-string, so a password containing `@`, `/`
or `%` produced a different (or unparsable) URL, and Alembic's ini
interpolation rejected any `%`.

**Now, in plain terms:** the database is named by five settings,
`POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD` and
`POSTGRES_DB`, and by nothing else. One function, `Settings.database_target()`,
turns them into a SQLAlchemy URL object with `URL.create` (no string is
assembled or parsed), and every component uses it: the API's engine,
Alembic, `make db`, `make seed`, the tests and the smoke run. If
`DATABASE_URL` is set to anything non-empty, in `.env` or the shell, every
one of them refuses to start, before connecting, with a message that names
the variable but never its value; the API refuses at start-up. An empty
`DATABASE_URL` (the compose file sets one for the api container) counts as
unset. `POSTGRES_DB` may not be empty or one of the server's own databases
(`postgres`, `template0`, `template1`); the port must be 1–65535.

`prepare_db` resolves the target once and uses that same object for every
step: it creates the database over an administrative connection to the
server's `postgres` database (not the application database), runs the
safety check (now also refusing tables in a schema other than the one
migrations write to), and passes the object to Alembic, which migrates it
instead of resolving the settings again. Everything printed names the
target as `user@host:port/name`; no password is printed, and the password
setting is a secret type that does not appear in a settings repr.

## 3. What a smoke pass means (C02)

`python -m evaluation.provider_smoke` ends with one line,
`SMOKE <OUTCOME>: <reason>`, and its exit code says which outcome it was.

- **REFUSED (2)**, before any provider call: no `REGDELTA_ALLOW_PAID_CALLS=1`;
  no `POSTGRES_DB` in the environment; a `DATABASE_URL`; the deterministic
  provider; a missing key; the smoke caps not being the settings in effect;
  or a target that `ingestion.seed` did not build (it must be at this
  checkout's migration head, hold only circulars the synthetic generator
  wrote, `synthetic://regdelta/…`, one with obligations, and the seed's
  manual by name and version with every clause embedded; the refusal names
  the database it resolved). An empty, unmigrated, foreign, mixed or
  half-seeded database cannot pass, and neither can the test suite's
  database (synthetic fixtures, but not the seed's: the gate found the first
  version of the preflight accepting it, see §6).
- **PASSED (0)**, and only then: the run reached COMPLETED; it is the run
  that was started (run id, circular, pack); it was made by the configured
  provider and model, not the deterministic one; the app counted between 1
  and 12 provider calls; its tokens are above zero and equal the sum over
  its steps; at least one judgement used tokens; no step called the provider
  after the token cap was reached; it finished within the 300 s timeout (30 s
  allowed for start-up and clock skew); and the fixture's expected
  behaviour holds: every finding belongs to the circular, its obligations
  and the manual, every obligation has a finding, no task failed, and a memo
  was written.
- **Rule for a missing memo, missing findings and failed tasks:** each makes
  the run INCOMPLETE, not a pass, even where the app skips the memo by design
  (no finding had located quotes): the end-to-end path was then not
  exercised.
- Every other ending has its own name: **FAILED (3)** and **CAPPED (4)** (the
  run's own status), **INCOMPLETE (5)** (still PENDING or RUNNING, an unknown
  status, or completed without the output above), **MALFORMED (6)** (a
  response that is not JSON or not the API's schema), **TRANSPORT (7)** (an
  exception, or an unexpected HTTP status), **INVALID (8)** (well formed but
  wrong: another run, another provider, no provider activity, a limit
  exceeded) and **EXPORT_FAILED (9)**.
- `--export` (which `make provider-smoke` passes) adds the findings to the
  semantic-support candidates only after a pass; if the export fails, the
  exit is 9, never 0.

The app runs inside a `TestClient` used as a context manager, so its
start-up (settings, the database target, recovery of interrupted runs) and
shutdown run as in a server; every response is checked for status and
schema before any field is read. The caps are real limits, tested at run
level: a call cap of 1 stops a run after exactly one call, a token cap stops
it after the call that crosses it, and a 1 s timeout stops a slow run, each
ending CAPPED with its reason (`test_assessment_limits.py`).

## 4. The model-loading boundary (C03): a mitigation, not a patch

sentence-transformers 3.4.1 (CVE-2026-68770) loads a local directory instead
of the Hub whenever the configured model name exists as a path relative to
the working directory, and then imports custom Python from it even with
`trust_remote_code=False`. This was reproduced: a planted
`BAAI/bge-small-en-v1.5/` directory made the library's own constructor run
its code (`review-evidence/c/logs/c03-shadow-demonstration.log`).

What RegDelta now does:

- one accepted source per role, in `backend/app/core/model_sources.py`: the
  embedding model is only `BAAI/bge-small-en-v1.5` at
  `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, the reranker only
  `BAAI/bge-reranker-base` at `2cfc18c9415c912f9d8155881c133215df768a70`;
- settings refuse anything else at start-up: local or absolute paths, `~`,
  URL forms (`https://`, `hf://`), case variants, trailing slashes, other
  repositories, the other role's model, branch names, short or other
  commits;
- each loader checks again immediately before constructing and refuses if a
  file, directory or link exists at the Hub name in the working directory
  (the same test the library applies); in the reproduction the guarded
  loader refused and the planted code did not run;
- both constructors receive `trust_remote_code=False` explicitly (both
  installed signatures accept it; a test asserts that).

Residual assumptions, stated rather than solved: the Hugging Face cache
(`HF_HOME`, by default `~/.cache/huggingface`) is trusted as it stands, and
whoever can write to it can change what the pinned revisions load; a
shadowing path created in the instant between the check and the load is not
caught; and the library remains vulnerable until it is upgraded (5.6.0,
which changes CrossEncoder behaviour the refusal threshold depends on).
Caches were not deleted. The real models were loaded once through the
guarded loaders (`c03-real-model-load.log`), and the retrieval, score and
refusal tests run on them.

## 5. The two tracked changes after the reseed (C04)

The v2 final pass recorded "tracked changes after the 300-circular reseed:
2", while the report said the tracked corpus files were byte-identical. Both
were true of different files; the report's wording hid the two. A fresh
reproduction at the same revision, `207f466`, in the clean clone, recording
`git status` after every step (`review-evidence/c/logs/reseed-repro/`):

| After | Tracked files changed |
|---|---|
| `seed --count 60` (the CI database) | `data/synthetic/manifest.jsonl`, `evaluation/datasets/synthetic/retrieval_gold.jsonl` |
| `check_baseline` | same two |
| `build_extraction_labels --count 30` | + `evaluation/datasets/synthetic/obligations_labeled.jsonl` |
| `run_suites --suite extraction` | + `evaluation/results/suites/evaluation_extraction.md` |
| `make e2e-db` (300 circulars) | **`obligations_labeled.jsonl` and `evaluation_extraction.md` only** |

The reseed restores the manifest and the gold set byte for byte. The two
files that stay changed are written by the CI job's extraction step, which
the reseed does not regenerate: `build_extraction_labels` labels the first
30 circulars of the database it runs on, so on the 60-circular CI database it
writes 132 labels for 30 different circulars (none shared with the committed
file, which was built from the 300-circular database); and the extraction
report records the working tree's revision (`207f466…+dirty:…` instead of
the committed `9b50ce0`). Neither is a corpus file, and neither affects a
later step. The gate in this pass keeps that diff
(`review-evidence/c/logs/gate/retrieval-gate-tracked.diffstat`) and then
restores exactly those two files.

## 6. Verification (C05)

Focused tests ran in the main tree as each fix landed (rows in the results
file, including the failing first runs). The integrated gate then ran in the
disposable clean clone, with `git status` recorded after every step, on new
databases `regdelta_c_gate_*` on the disposable server:

**Full gate on `a2ef73f`** (`review-evidence/c/logs/gate/`):

| Check | Result |
|---|---|
| `make lint typecheck` | ruff 0 findings, 172 files formatted, mypy 0 issues (27 files) |
| pytest, new `regdelta_c_gate_test` migrated from empty | **452 passed, 0 failed, 0 skipped** |
| retrieval regression, new `regdelta_c_gate_ci` (60 circulars) | Recall@10 0.9713 (baseline 0.9713), MRR@10 0.5026 (0.5031), tolerance 0.03 |
| extraction suite | P = R = 1.000; its two tracked outputs (§5) kept as a diff, then restored |
| refusal suite on the approved models | 15/15 refused, 0/15 controls refused (22 min) |
| smoke run without the opt-in | `SMOKE REFUSED`, exit 2, no app built |
| smoke preflight | **finding:** it accepted the test suite's database; fixed in `b078808` |
| `make e2e-db` (300 circulars) | 0 tracked changes afterwards |
| `make e2e`, native | **21/21** |
| `make mcp` | pass |
| `make stack-up` (`regdelta-r2acc`) | API image rebuilt (start-up and configuration changed; dependency layer cached); web image from cache (frontend unchanged); start-up loaded both approved models at their pinned revisions; `nginx -t` ok |
| container walk through http://127.0.0.1:8081 | **17/17** (SSE 28 events over 55 s) |
| Playwright through nginx | **21/21** |
| API stopped | 502 `api_unreachable` in 0.003 s; the UI's unreachable notice; 200 after restart |
| `make down`; pre-existing containers and volumes | 0 diff lines; 0 tracked changes at the end |

**Follow-up gate on `b078808`** (`review-evidence/c/logs/gate2/`), which
differs from `a2ef73f` in `evaluation/provider_smoke.py`,
`ingestion/generate_corpus.py` (a named constant; same output), two test
files and the advisories document (`changed-since-full-gate.diffstat`).
Neither image contains `evaluation/` or `ingestion/`, so the container
results carry over; everything the change can affect was re-run:

| Check | Result |
|---|---|
| `make lint typecheck` | clean (172 files) |
| pytest, new `regdelta_c_gate2_test` | **458 passed, 0 failed, 0 skipped** |
| `make e2e-db` into new `regdelta_c_gate2_e2e` | 0 tracked changes (the generator's output is unchanged) |
| smoke run without the opt-in | `SMOKE REFUSED`, exit 2 |
| smoke preflight against five databases | the two 300-circular and the 60-circular seeded databases give the fixture `SEBI/HO/DDHS/CIR/P/2019/17` (4 obligations); both test-suite databases are refused |

Also measured: a deterministic run of that fixture makes 5 provider calls
(4 judgements and the memo) of the 12 allowed; `regdelta_demo` passes the
preflight with the same fixture (read-only check).

Frontend gates (eslint, Vitest, build) were not re-run: no frontend file
changed since the v2 package (`git diff --stat bd10a94 -- frontend` is
empty). Not run: the real-provider smoke run, hosted CI, the human reviews,
a screen-reader session.

## 7. Branch, commits, package

- Branch `repair/regdelta-cleanup`, local only. Commits since the v2
  package's head `bd10a94`:

  | Commit | Kind | Content |
  |---|---|---|
  | `19fa48f` | code | C01 database target, C02 smoke outcomes, their tests |
  | `7fd3395` | code | C03 model-source policy and tests |
  | `a2ef73f` | code | packaging reads this pass's evidence; one test constant |
  | `ac1e8db` | evidence | C04 advisories document |
  | `b078808` | code | preflight requires the seed's corpus and manual; run-level limit tests |
  | the `docs(maintenance)` commit after it | evidence | this report, the ledger section, results, state |

- **Tested code revision `b078808`** (full gate on `a2ef73f`, follow-up gate
  on `b078808`, §6). The package manifest's `code_revision` is the last
  commit outside `docs/maintenance` and `docs/screenshots`, so it is
  `b078808`; the commit after it records evidence only.
- Nothing was pushed, merged, deployed, published or opened as a PR; no
  hosted CI was dispatched; no remote or history was changed. No paid
  provider call was made (every run used the deterministic provider; the
  smoke command was only run without its opt-in, and refused).
- No existing data was modified. Pre-existing containers and volumes
  (`regdelta-postgres-1` and `regdelta_pgdata`, `ai-trading-*`, `jarvis-*`)
  kept their identity (0 diff lines). New, all disposable and kept: databases
  `regdelta_c_focus_test`, `regdelta_c_reseed_ci`, `regdelta_c_reseed_e2e`,
  `regdelta_c_gate_test`, `regdelta_c_gate_ci`, `regdelta_c_gate_e2e`,
  `regdelta_c_gate2_test`, `regdelta_c_gate2_e2e` on `regdelta-repair-pg`
  (the tests' `regdelta_guard_*_test` databases and temporary role are
  dropped by the tests); the acceptance stack `regdelta-r2acc` was started
  and removed with `make down`, its two volumes kept, and its API image
  rebuilt under the same tag. `regdelta_demo` was only read (the preflight).
- Package: `RegDelta-review-v3.zip` beside the repository (v2 is kept), built
  by `python3 scripts/package_review.py --previous bd10a94 --results
  docs/maintenance/regdelta-correction-results.json --out
  ../RegDelta-review-v3.zip`. It holds `git archive HEAD`; `review-evidence/`
  with the release repair's evidence as in v2 and this pass's under
  `review-evidence/c/` (gate logs, focused-test logs, reproductions, resolver
  outputs, the scripts that ran them, all redacted); the diff
  `bd10a94..b078808`; the commit list with messages and files; and
  `MANIFEST.json` (UTC time, revisions, tool versions, the results table and
  a SHA-256 per entry). The ZIP's own size and SHA-256 are in
  `RegDelta-review-v3.zip.sha256` beside it.

## 8. Later steps (not executed in this pass)

1. **Real-provider smoke run (G02)**, with a key and explicit authorisation,
   while no API is serving `regdelta_demo` and with `DATABASE_URL` unset:

   ```bash
   cd RegDelta
   # GROQ_API_KEY in .env (never on the command line); LLM_MODEL defaults to openai/gpt-oss-20b
   REGDELTA_ALLOW_PAID_CALLS=1 LLM_PROVIDER=groq \
     POSTGRES_HOST=localhost POSTGRES_PORT=55432 POSTGRES_DB=regdelta_demo \
     HF_HUB_OFFLINE=1 make provider-smoke
   ```

   It prints `target regdelta@localhost:55432/regdelta_demo`, assesses
   `SEBI/HO/DDHS/CIR/P/2019/17` (4 obligations) with at most 12 calls,
   20,000 tokens and 300 s, and ends with `SMOKE <OUTCOME>`. Only
   `SMOKE PASSED` (exit 0) validates G02; record the run id and the summary.
   A pass appends to `evaluation/datasets/support/` (a tracked file): review
   that diff before committing it. Any other outcome is a result to report,
   not to retry until it passes.
2. **Human reviews (F07)**, by a named person, separately:
   `python -m evaluation.annotation review --reviewer "Name"` (39
   retrieval-relevance records) and `python -m evaluation.support_review
   review --reviewer "Name"` (41 semantic-support candidates, plus any the
   smoke run adds).
3. **R04 decision** on the open advisories, per
   [dependency-advisories.md](dependency-advisories.md): accept the stated
   scope exceptions, or schedule the measured upgrades (Tailwind 4,
   React Router 7.18, FastAPI with Starlette 1.x, LangGraph 1.x,
   sentence-transformers 5 with transformers 5).
4. **Hosted CI (G04)** after an authorised `git push origin
   repair/regdelta-cleanup`: read the four jobs (`backend`,
   `retrieval-gate`, `frontend`, `e2e`); inspect any screenshot difference
   in the uploaded report before accepting it, never automatically.
5. Optional clean-up, when no longer needed: the `regdelta_c_*` databases
   on `regdelta-repair-pg`, and the acceptance volumes and images listed in
   the completion report §7.
