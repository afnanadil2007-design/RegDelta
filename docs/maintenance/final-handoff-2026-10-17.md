# RegDelta portfolio handoff — 2026-10-17

RegDelta is a research prototype. Human retrieval-relevance and
semantic-support evaluation remain pending. AI-assisted annotations must not
be described as independent human validation. Dependency exceptions remain
in [dependency-advisories.md](dependency-advisories.md); this handoff makes no
new dependency acceptance decision.

## Recovered state and checkpoint

Inspected repo and parent instruction files: no applicable `AGENTS.md` or
`CLAUDE.md` found. Read maintenance reports, results/state, ledger and demo
script. The actual checkout was clean on `main` at `4d090cc`, with no staged,
unstaged or untracked files. No `docs/final-handoff` branch existed. The last
reflog actions were the smoke-candidate commit, switch to main and fast-forward
pull. Thus the smoke candidates and merge were complete; the dated evidence
updates, shorter demo, capture preparation and backup inventory were unfinished.
Ignored local evidence and configuration were left in place.

Before edits, created `checkpoint/pre-final-handoff-20261017` at `4d090cc`
and `../RegDelta-pre-final-handoff-20261017.bundle` (`git bundle verify`
passed; complete history and refs). Then created `docs/final-handoff` at that
same commit. The bundle preserves Git history, not ignored data; back those up
separately. No restoration, reset, deletion, reseed or provider call was made.

## Evidence update

| Item | Established evidence and scope |
|---|---|
| Repair merge | PR #1 merged into main at `4d090cc`; present in local history. |
| Hosted CI, G04 | Backend, frontend, retrieval-gate and e2e passed on `4d090cc`, per the established user handoff. No run URL or downloaded hosted logs were supplied or invented; not independently re-fetched in this task. |
| Real-provider smoke, G02 | Passed 2026-10-17, Groq `openai/gpt-oss-20b`, run `07525384-7c53-4301-ba5f-28f0bdb7a2ff`, per established handoff. Read-only local SQL confirms COMPLETED and provider/model identity. |
| Durable smoke output | Four synthetic-corpus support candidates in `evaluation/datasets/support/candidates.jsonl`, committed in `b4b3236`. 45 total candidates: 41 deterministic plus 4 real-model findings. This is integration evidence, not a semantic-quality result. |
| Human evaluation, F07 | Pending: 39 retrieval-relevance records and the separate semantic-support candidates. No independent human validation claimed. |
| Demo video | Recorder prepared; no playable recording produced or claimed by this task. |

The 2026-10-16 reports and machine results are historical evidence; their
“not run” statements describe that date. Dated notices link here without
rewriting old outcomes or inventing cost, token counts, timings or CI URLs.

## Inspected runtime and safe launch

Read-only inspection on 2026-10-17 found:

- `regdelta-repair-pg` running, label `owner=regdelta-repair-session`, volume
  `regdelta_repair_pgdata`, published only at `127.0.0.1:55432`.
- `regdelta_demo`: 300 circulars, 1,313 obligations, 50 policy clauses.
  Completed deterministic run `98dc9b79-d75e-49d1-900a-83dbd8daf85f`
  and the completed Groq smoke remain available.
- Ports 8040 and 5173 free. Ports 5432, 8000, 3000 and 6379 belong to
  the ai-trading stack. Leave it, `jarvis-*`, `regdelta-postgres-1` and
  `regdelta_pgdata` alone. Port ownership can change: recheck before launch.
- Settings resolved without overrides to `regdelta@localhost:5432/regdelta`.
  Therefore do not trust ambient `.env` for this demo. Python and Vite both
  load repo-root `.env`; process variables take precedence. `DATABASE_URL`
  must be empty. Explicit overrides below select only the inspected target.

From two terminals, launch these exact commands. No setup, migrations,
`make db`, seed, E2E database setup or Compose startup is required.

```bash
# Inspect first; if either application port has a listener, identify it and stop.
ss -ltnp '( sport = :55432 or sport = :8040 or sport = :5173 )'
docker inspect regdelta-repair-pg --format '{{json .Config.Labels}} {{json .Mounts}}'

# Terminal 1
cd /home/afnan/Downloads/Reg-Delta/RegDelta/backend
env DATABASE_URL= POSTGRES_HOST=localhost POSTGRES_PORT=55432 \
  POSTGRES_DB=regdelta_demo LLM_PROVIDER=deterministic \
  REGDELTA_ALLOW_PAID_CALLS=0 HF_HUB_OFFLINE=1 \
  WARM_MODELS_ON_STARTUP=true CORS_ORIGINS=http://127.0.0.1:5173 \
  .venv/bin/python run_api.py --host 127.0.0.1 --port 8040

# Terminal 2
cd /home/afnan/Downloads/Reg-Delta/RegDelta/frontend
export PATH=/home/afnan/.nvm/versions/node/v20.20.2/bin:$PATH
env API_PORT=8040 REGDELTA_API_URL=http://127.0.0.1:8040 \
  REGDELTA_WEB_PORT=5173 npm run dev

# Terminal 3, once both servers are ready
curl --fail --silent http://127.0.0.1:8040/api/health
curl --fail --silent http://127.0.0.1:5173/api/health
```

Open http://127.0.0.1:5173. Stop only these foreground processes with Ctrl-C
when done. API startup marks interrupted assessments failed by design; the
inspection found no running/pending assessment among the current 11 records.
The demo explicitly saves one analyst decision. Back up first if preserving
the exact database state matters.

## Automatic real-browser capture

Installed locally: Node 20.20.2 and 22.23.2, Playwright Test 1.62.1 in
`frontend/node_modules`, system Chrome, cached Chromium 1234 and ffmpeg 1011.
The Codex session's installed skill/MCP catalog was inspected: it includes
research/design/hosting connectors but no directly available local Playwright
MCP. Claude's Impeccable and browser MCP availability does not transfer.
No plugin installation is required; use the local Playwright library.

`frontend/record-demo.mjs` uses a real Chromium browser, the real local API,
and real UI selectors. It creates a unique ignored output directory, checks
that the run is completed/deterministic, and chooses a pending finding with
both quotation spans. It never starts an assessment or overwrites a prior
decision. It saves Accept through the UI and asserts persistence after reload.
It does not mock responses. Output is silent WebM plus screenshots; failures
leave diagnostic media but do not count as a successful walkthrough.

After launching the servers above:

```bash
cd /home/afnan/Downloads/Reg-Delta/RegDelta/frontend
export PATH=/home/afnan/.nvm/versions/node/v20.20.2/bin:$PATH
node record-demo.mjs
```

Use `DEMO_RUN_ID=<another-completed-deterministic-run>` if all eligible
findings have already been decided. `DEMO_HEADED=1 node record-demo.mjs`
shows the browser where a desktop display is available. The script is
syntax-checked, not run end to end in this preparation task. It does not use
`playwright.config.ts`, whose normal tests create assessments and clear a
decision. No full suite was rerun for this documentation task.

Before sharing, open the emitted WebM in Chrome or a media player, verify
playback, source highlights, saved decision after reload, labels and duration.
Only then describe it as a recording. Read [the narration](../demo-script.md)
for a 2–3 minute voiceover. Recording and backup export are remaining operator
steps, not completed outputs of this handoff.

## Backup inventory before eventual cleanup

Paths below are inventory only; secret contents are not printed. Keep a
separate verified copy off this checkout before any later cleanup. A Git
bundle or review ZIP alone does not preserve the database or local config.

| Path/resource | Value and handling |
|---|---|
| Repo `.git/`, tracked source/docs/evaluation outputs | Full work history and refs; checkpoint bundle above verified. Make a new bundle after the handoff commit if desired. |
| `../RegDelta-review.zip`, `../RegDelta-review-v2.zip`, `../RegDelta-review-v3.zip`, adjacent `.sha256` files | Historical review packages; all present. Preserve alongside their hashes. |
| `.artifacts/` (about 14 MB) | Local-only baseline, clean-clone, evaluation, C-pass, resolver, audit and container logs/screenshots; preserve original chronology. May contain sensitive local context: review privately before sharing. |
| `.env` | Local configuration, potentially credentials; copy privately with restricted access, never commit or print. Check any backend/frontend `.env*` and shell secret stores privately before cleanup. `.env.example` is tracked, not a credential backup. |
| `data/real_sources/pdf/` (about 28 MB) | Downloaded official PDFs not in Git; retain with tracked URL/checksum manifest. |
| `data/synthetic/pdf/` (about 1.2 MB) | Current generated PDFs; retain with tracked manifest if exact seed state is useful. |
| `evaluation/datasets/`, `evaluation/results/`, `evaluation/reports/` | Committed candidate snapshots, annotation history and measured results; include any later local-only reviews. Do not call AI labels human-reviewed. |
| `frontend/test-results/`, future `.artifacts/demo/` | Local browser diagnostics and future recording; preserve successful playable output and screenshots separately. |
| `.impeccable/questions/`, `.impeccable/mocks/`, `.artifacts/impeccable-roll-original.json` if present | Claude-specific local review context; keep if needed, no restoration attempted. |
| `/home/afnan/.claude/projects/-home-afnan-Downloads-Reg-Delta/`, parent `../.claude/` | Session/context recovery material; path exists, contents not exposed; archive privately if desired. |
| `regdelta_repair_pgdata` mounted by `regdelta-repair-pg` | Primary local-only seeded DB, runs, decisions and traces. Prefer per-database logical dumps and a restricted role/global backup; validate by restore into a separately authorized isolated target before any volume removal. |
| `regdelta-r2acc_pgdata`, `regdelta-r2acc_modelcache` | Acceptance volumes still present; inventory before deciding retention. No volumes changed. |
| `backend/.venv/`, `frontend/node_modules/`, `frontend/dist/`, `/home/afnan/.cache/huggingface/`, `/home/afnan/.cache/ms-playwright/` | Rebuildable dependencies/builds and expensive model/browser caches; pinned lockfiles are tracked. Retain caches if offline reproduction matters. |

Databases observed on the repair server (none exported or removed):
`regdelta_demo`, `regdelta_test`, `regdelta_before`, `regdelta_e2e`,
`regdelta_real`, `regdelta_ci`, `regdelta_ci2`, `regdelta_clone_test`,
`regdelta_clone_e2e`, `regdelta_r2_clone_test`, `regdelta_r2_clone_e2e`,
`regdelta_r2_ci`, `regdelta_r2_ci2`, `regdelta_r2_final_test`,
`regdelta_r2_final_ci`, `regdelta_r2_final_e2e`, `regdelta_c_focus_test`,
`regdelta_c_reseed_ci`, `regdelta_c_reseed_e2e`, `regdelta_c_gate_test`,
`regdelta_c_gate_ci`, `regdelta_c_gate_e2e`, `regdelta_c_gate2_test`,
`regdelta_c_gate2_e2e`; plus administrative `postgres`. Preserve demo first;
classify the rest from evidence rather than assuming “test” means valueless.

Example future export, not executed here (choose a private backup location):

```bash
umask 077
mkdir -p /tmp/regdelta-backup-20261017
docker exec regdelta-repair-pg pg_dump -U regdelta -d regdelta_demo -Fc \
  > /tmp/regdelta-backup-20261017/regdelta_demo.dump
# Inspect archive structure; this is not a restore test.
docker exec -i regdelta-repair-pg pg_restore --list \
  < /tmp/regdelta-backup-20261017/regdelta_demo.dump
sha256sum /tmp/regdelta-backup-20261017/regdelta_demo.dump
```

Repeat only for selected databases on this repair server; obtain roles/globals
privately if needed. Move backups off `/tmp` and off this machine, verify
checksums, then perform an isolated restore check before considering cleanup.
No cleanup is authorized by this handoff. The unrelated `regdelta_pgdata`,
ai-trading and jarvis resources are outside scope.

## Verification of this handoff

Passed: recorder Node syntax check, targeted ESLint and Prettier check,
state JSON parse, 45 support candidates/four smoke records, relative links in
the edited overview/handoff reports, and `git diff --check`. Read-only SQL
confirmed the selected deterministic run has pending findings with both source
spans and that no assessment is currently PENDING or RUNNING. Application
ports were rechecked free. No full suite or browser recording was run; launch
commands were derived from the installed entrypoints/configuration, not
reported as a new runtime acceptance result.
