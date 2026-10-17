# Recorded-demo plan — 2026-10-17

This is a 2–3 minute script and recording preparation, not evidence that a
video exists. Use the existing seeded `regdelta_demo` on localhost:55432.
Exact launch and recording commands are in
[the handoff](maintenance/final-handoff-2026-10-17.md). Do not reseed.

Use completed deterministic run `98dc9b79-d75e-49d1-900a-83dbd8daf85f` so CPU
retrieval is outside the recording. Opening it makes no provider call. The
recorder selects an undecided finding with quotations in both sources and
leaves its accepted decision saved. This is a demonstration action, not a
human evaluation annotation. If none remain, stop and choose another existing
deterministic run; do not overwrite an earlier decision.

| Time | Browser action | Suggested narration |
|---|---|---|
| 0:00–0:20 | Overview; point out synthetic-data and rule-based judge labels | “RegDelta compares regulatory obligations with an internal manual. These documents are synthetic; this walkthrough uses an offline rule-based judge.” |
| 0:20–0:45 | Open the run's circular detail; show the marked obligations and source text | “Each finding points back to source text. The underlying documents and offsets remain inspectable.” |
| 0:45–1:30 | Open the completed assessment; select a pending finding; show the highlighted circular and policy quotations | “The machine proposes an interpretation. Located quotations prove that the text exists, not that the interpretation is correct. Rule scores are not calibrated probabilities.” |
| 1:30–2:00 | Accept; wait for saved confirmation; reload; show Accepted still selected | “An analyst records a decision. The server saves it, and it survives a reload. This workflow action does not count as an independent research review.” |
| 2:00–2:30 | Evaluation page; explain its synthetic labels | “The comparisons use template-derived retrieval labels. Human retrieval and semantic-support evaluations remain pending, and AI-assisted annotations are not independent human validation.” |
| 2:30–2:45 | Hold on Evaluation | “Hosted CI passed on merge commit 4d090cc. One Groq smoke exercised the real-provider path on October 17; that establishes integration, not semantic accuracy. Dependency exceptions remain documented. This is a research prototype.” |

The automatic capture follows this sequence with deliberate reading pauses,
without narration. Record a voiceover separately if desired. A slow page or a
failed assertion may lengthen or abort the capture; review the actual result
before sharing it. No live assessment or slow reranked search is needed.

The prior five-minute script is preserved in git at
`4d090cc:docs/demo-script.md`. The provider smoke already passed on 2026-10-17
with Groq `openai/gpt-oss-20b`, run
`07525384-7c53-4301-ba5f-28f0bdb7a2ff`; four candidates were committed in
`b4b3236`. Do not rerun it for the demo. Human evaluation remains pending.
