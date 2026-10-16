# Screenshots after the rebuild

Captured on 2026-10-15 from the build committed with this folder, against
the seeded synthetic demo database, with the deterministic rule-based judge.
The five workspace images were captured again on 2026-10-16 from the release
repair's code (graph v3), on the end-to-end database: they show the current
quote-check wording ("Each quote was found verbatim in its source") and the
memo summary that counts quotations found instead of "verified" findings.
Every circular is generated and the manual is fictional. `../before/` holds the interface as it was at
`f4a4b57`.

| File | What it shows |
|---|---|
| `workspace-1440.png`, `workspace-390.png` | The assessment workspace: findings index, circular and manual leaves with the located quotes marked, the verdict plate, the decision bar, the memo. At 390 px the index becomes a picker with previous and next. |
| `workspace-memo-1440.png` | The memo alone: "7 finding(s) for … : 7 whose quotations were found in their sources, 0 with no clause to compare". It is labelled as written by the rule-based judge. |
| `workspace-decided-1440.png` | The same finding after **Accept**, once the server has stored it: the tick in both margins and the decision's time. |
| `workspace-capped-failed-1440.png` | **Simulated state.** A real run's response was altered by route interception, because the seeded demo run neither stops at a limit nor misquotes: the run shown stopped at its call limit, with one task failed and one finding whose clause quote was not located (struck through in the plate). The judge named is the deterministic one that produced the underlying run; no model was called. |
| `circular-detail-1440.png`, `circular-detail-390.png` | A circular as a leaf with its obligations underlined, the assessment launcher, relationships and provenance. |
| `search-1440.png` | Hybrid search with the query's terms marked. The results are near-duplicates because the synthetic corpus is generated from eight templates. |
| `search-refused-1440.png` | The reranked mode refusing an out-of-scope question. It took 2 min 19 s on the evaluation laptop, under load. |
| `point-in-time-1440.png` | What was in force on 1 Dec 2024: the older circular in force, the newer one not yet issued. |
| `overview-1440.png` | Runs awaiting review and the newest circulars. |
| `evaluation-1440.png` | Stored retrieval results with intervals and one provenance block. |
