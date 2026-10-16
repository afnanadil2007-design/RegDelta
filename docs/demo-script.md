# Five-minute demo

A guided tour of the running app, written to be read aloud or followed
alone. It is a script, not a recording. Everything shown comes from the seeded
synthetic database and the deterministic judge, so it needs no API key and
looks the same on every machine.

Before you start: `make db seed`, then `make dev-api` and `make dev-web`, and
open http://127.0.0.1:5173. Or run it all in containers (`make stack-up`, see
the README) and open http://127.0.0.1:8080 (`WEB_PORT`).

## 0:00 — Where the work is (Overview)

- The top bar names the judge in words: "Database up · rule-based judge
  (demo)". Nothing here pretends to be a language model.
- *Awaiting review* lists runs with undecided findings; *Latest circulars*
  shows the newest documents. The "Synthetic data throughout" tag is not
  decoration: the corpus is generated, and every page says so.

## 0:40 — Find a circular (Circulars)

- Type `2024/306` in *Number or title*. The list filters as you type and the
  filter is in the URL, so a refresh or a shared link keeps it.
- Open **SEBI/HO/MIRSD/MIRSD_Div1/P/CIR/2024/306**, *Client onboarding and KYC
  verification norms (2024)*.

## 1:00 — Read it (Circular detail)

- The text is set as a leaf: paragraph numbers in the left margin, guide
  words at the head (¶1 … ¶9). Obligations are underlined with dots and listed
  on the right with their subject and the extractor that found them
  (`rules-v2`).
- *Relationships* says this circular supersedes 2024/282 from 11 Dec 2024.
  Follow **See it on the timeline**.

## 1:30 — What was in force when (Point in time)

- Set the date to 1 Dec 2024: the older circular is *In force*, the newer one
  *Not yet issued*. Move it to 11 Dec 2024: the older one is *Out of force*.
  Supersession removes a circular; an amendment would not.
- Go back to the circular.

## 2:00 — Run an assessment

- Under *Assess*, keep the fictional Meridian Broking manual and choose
  **Start assessment**. The workspace opens on the new run at once.
- The *Agent trace* is open while it runs: one row per step, updating in
  place. Retrieval is the slow step (the cross-encoder reads 50 clauses per
  obligation on the CPU); judging and quote checks take milliseconds.

## 3:00 — Review the evidence (the workspace)

- Pick **A.3 In-person verification** in the findings index (or use the
  arrow keys). The quoted passage lights up in both documents, and in each
  an arrow beside its first line points at it.
- Read the plate under the circular: *Modified*, by the rule-based judge, "3
  days" against "fifteen (15) calendar days". The quote check says *Quotes
  located*, and why that is not the same as the interpretation being right.
  The score is labelled as a rule score, not a confidence.

## 3:45 — Decide, and prove it stuck

- **Accept**. The button stays pressed only after the server has saved the
  decision; a tick settles into the margins and the index entry says
  *Accepted*.
- Reload the page. The decision is still there, with its time.
- (Optional) Stop the API and try **Reject**: the page says the decision was
  not saved and keeps showing *Accepted*. Start the API and **Try again**.

## 4:20 — Search and refusal (Search)

- Search `client due diligence before account activation` in **Hybrid**: an
  answer in well under a second, query terms marked in each passage.
- Switch to **Hybrid + rerank** and search `What is the capital of France?`.
  After the cross-encoder has read the candidates (tens of seconds on a
  laptop; a clock and Cancel are shown) it refuses: no passage scored above
  the threshold. The other modes never refuse.

## 4:50 — The evidence behind the claims (Evaluation)

- Four modes on one query manifest, with refusal beside ranking quality,
  per-query latency, intervals, and the code version and models that produced
  each number. The labels are template-derived from the synthetic corpus,
  which the page states.

## Afterwards — the real-provider smoke check (not part of the demo)

The demo and every automated test use the deterministic judge. One capped
run with a real model shows the provider path works; it has **not** been run
for this revision (no key was available), and it can be billed, so it runs
only when asked for:

```bash
# in .env or the shell: LLM_PROVIDER=groq (or anthropic), its key, LLM_MODEL
REGDELTA_ALLOW_PAID_CALLS=1 POSTGRES_DB=regdelta_demo make provider-smoke
```

It first prints the database it will use and refuses (exit 2) unless that
database is seeded and synthetic, then assesses the synthetic circular with
the fewest obligations, capped at 12 provider calls, 20,000 tokens and 300 s,
one call at a time. Run it while no API is serving that database. It prints
the run, status, provider and model, calls, tokens and the cost estimate (or
why it is unknown), and ends with one line, `SMOKE <OUTCOME>: <reason>`.
Only `SMOKE PASSED` (exit 0) counts: a completed run by that provider, within
the caps, with a finding for every obligation, no failed task and a memo.
FAILED, CAPPED, INCOMPLETE, MALFORMED, TRANSPORT, INVALID and EXPORT_FAILED
each have their own exit code (`evaluation/provider_smoke.py` lists them).
After a pass it adds the findings to the semantic-support candidates as
real-model output (`evaluation/datasets/support/`). Then open the run in the
workspace: the plate names the model, scores read "model-stated,
uncalibrated", and the memo must not call any finding verified.

