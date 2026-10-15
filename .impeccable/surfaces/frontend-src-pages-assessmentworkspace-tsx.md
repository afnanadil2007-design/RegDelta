---
version: 1
slug: "frontend-src-pages-assessmentworkspace-tsx"
primary_target: "frontend/src/pages/AssessmentWorkspace.tsx"
related_targets: []
---

# Surface brief: assessment workspace

Scope: the evidence workspace for one assessment run (`/assessments/:runId`);
the reference implementation for every other route. Mode: Operate, with two
Read panels (the circular passage and the policy clause).

Audience and job: a compliance analyst reviewing machine findings for one
circular against the firm's manual, finding by finding. Action: understand
the cited passage, the clause, the machine's interpretation, and whether the
quotes were located; then accept or reject. Proof: verbatim quotes at stored
offsets, quote status, provider and model, decided-at time. Constraints:
synthetic corpus and fictional manual labelled; model scores labelled
uncalibrated; unknown is never shown as zero; standard web controls.

Chosen direction: the law lexicon (bolder hand, chosen by the user on
2026-10-15). Memorable moment: the selected finding's quote lit in both
documents, with the shoulder pointing at it and a decision tick landing there.

Unresolved: none blocking. Dark theme is out of scope unless fully verified.

## Direction contract

THESIS: The circular and the manual are read like a law lexicon: a fixed
measure, a shoulder margin that indexes paragraphs, evidence, and decisions,
guide words naming what is in view, and colour only inside bordered plates.
It refuses the category default of a grey console with metric cards and an
evidence drawer.

OWN-WORLD: Uncoated paper (#FAF8F3) on a warm grey desk, slate engraving ink
(#1C2230); colour quarantined to bordered plates: vermilion conflict, ochre
modified, ultramarine new requirement, emerald covered, sepia no match. Charis
SIL for documents, headwords, and guide words (small caps only for guide
words); Public Sans for controls and data, tabular figures throughout.

STORY: The analyst sees which circular changed and against which manual,
picks a finding from the index, reads the exact passage and clause side by
side, reads the machine's interpretation as a plate labelled as machine
output, checks the quote status, and records a decision that survives a
refresh.

FIRST VIEWPORT: Ink top bar with the product name and route links. Below,
three columns on one grid: the findings index (about 330 px) with guide words
and an impact plate; the circular leaf and the manual leaf at a 62-character
measure, each with a guide-word head and a shoulder of paragraph or clause
numbers, a solid arrow at the quoted span, and the decision tick. The verdict
plate sits under the circular text; Accept and Reject sit under the clause.

FORM: Lexicon page with shoulder and plates (catalog rw-lexicon-shoulder-and-
plate), first and only dealt alternate the user chose over the dealt lead in
the bolder register. seed: none (unavailable)

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
