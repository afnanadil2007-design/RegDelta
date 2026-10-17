# Frontend baseline (before the 2026-10 overhaul)

How the pre-overhaul UI behaved, captured so the redesign is judged against
evidence rather than memory (ledger item E01).

**How it was captured.** The old frontend speaks the old API, so it ran from a
throwaway worktree at commit `941d9d1` (ORM restored, old contract) against a
separately seeded database (`ingestion.seed --count 300` plus rules
obligations; 300 synthetic circulars, 1,500 obligations). The old code only
supports Groq or Anthropic, so one assessment was run against a local
OpenAI-compatible stub that answers with the deterministic rule provider: a
test double at the provider boundary, never a hand-written row. Browser:
Google Chrome via Playwright, 1440×900 and 390×844. Selected captures are in
[`docs/screenshots/before/`](../screenshots/before/); the full set and the
Taste-skill reports were kept under the git-ignored `.artifacts/`.

## Routes and flows

| Route | Purpose | Observed state |
|---|---|---|
| `/` Dashboard | corpus counts, recent circulars and assessments | three KPI cards, list, empty panel |
| `/circulars` | corpus list with department filter | one 7,557 px page, no text search or paging |
| `/circulars/:id` | obligations, amendment chain, references, source text | obligations as cards; source text in a narrow side column |
| `/search` | query with a retrieval-mode select | skeleton bars during the rerank wait, then 8 near-identical hits |
| `/assessments`, `/assessments/:runId` | findings table, evidence pane, memo, agent trace | 22 trace cards beside a table; accept/reject buttons |
| `/point-in-time` | question + "as of" date | search form and an empty box; no timeline |
| `/evaluation` | ablation table | empty state "run `make eval`" |

## Defects observed (functional)

| Defect | Evidence | Cause |
|---|---|---|
| "Circulars ingested: **200**" while the database held 300 | `overview-desktop.png` | count was the length of a list fetched with `limit=200` |
| 100 of 300 circulars unreachable from the list | full-page circulars capture | list stopped at its `limit=200` fetch; no paging |
| Every evidence highlight started at character 0 of the shown text | `assessment-evidence-desktop.png` (clause A.3 highlight from `###` to mid-word "cale…") | `SpanHighlight` received `baseOffset = span_start`; the API never sent the clause's or obligation's own offset |
| Synthetic banner reads "SYNTHETIC CORPUS **?** NOT A REAL…" | `circular-detail-desktop.png` | generator wrote "—" with PyMuPDF's base-14 Helvetica, which cannot encode it; the PDF itself contains "?" |
| Rule obligations start mid-sentence ("**document** shall be acknowledged…", actor "document") | `circular-detail-desktop.png` | lazy actor pattern only spans capitalised words |
| Fixed rules score shown as "Medium 55"; retrieval no-match shown as "Low 40" | detail and assessment captures | invented values displayed as confidence |
| Phone layout clipped: the 220 px sidebar stays, content and the primary button cut at the edge | `circular-detail-mobile.png` | no responsive shell |
| Default search mode waits **48 s per query** (warm) with no explanation | API timing; 58 s in the browser | cross-encoder scores 50 whole-circular chunks on CPU |

Search latency on this machine (old API, same query): dense 0.06 s, lexical
0.02 s, hybrid 0.05 s, hybrid + rerank 47.6 s and 48.4 s (two calls).

## Taste skill — redesign review (round 0, baseline)

`lint.mjs` over `frontend/src`: 26 FAIL (12 decorative rules, 14 monospace
uses), 5 WARN (3 looping pulse animations, `h-screen`, 19 em dashes).
`inspect.mjs` at 1440/768/390: overview 8 FAIL / 6 WARN, circular detail
7 FAIL / 7 WARN. Applicable findings: 19–21 text blocks under 13 px, body
text 13–14 px in soft grey (5.7:1), sub-AA labels (`db connected` 4.1:1,
confidence badges 3:1), KPI eyebrow labels, uppercase tracked micro-labels,
1 px outlined boxes and dashed empty states, a 143-character prose measure, a
row clipped at the edge, and no dominant element on the first screen. Not
applied, as this is an app rather than a landing page: the photograph, video,
and entrance-motion rules.

```
ROUND 0 (baseline)
Seen in one second: a grey sidebar and grey boxes; nothing leads.
Idea (one sentence): none stated; reads as a generic admin dashboard.
Live thing: the agent trace, rendered as 22 identical cards.
Layout words by section: overview=cards+list / circulars=table / detail=split cards /
  search=list / assessment=table+cards+list / point-in-time=empty / evaluation=empty
Scores: design 4.5 · usability 4.0 · creativity 3.5 · content 5.0 → overall 4.2
Caps applied: inspector FAILs (≤ 6.0); mono labels, eyebrows, hairlines (≤ 6.5)
Top three problems:
1. The evidence view highlights the wrong text (assessment-evidence-desktop.png):
   the product's central promise is broken. Fix: slice by the clause's own offset.
2. No hierarchy on any screen: largest type 18 px, everything in outlined boxes,
   document text squeezed into a side column. Fix: one dominant reading surface.
3. The phone layout clips content and the primary action. Fix: a responsive shell.
```
