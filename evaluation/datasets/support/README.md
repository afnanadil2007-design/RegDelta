# Semantic-support review (prepared, not run)

Does an assessment finding's evidence support its rationale? A located quote
shows that the quoted text exists in the circular and the manual; it does not
show that the impact classification or the rationale follows from it. This
review asks a person to read each finding with its evidence and decide.

It is separate from the real-source annotations in
[`../real/`](../real/README.md). Those are **retrieval-relevance** labels
(does this passage answer this search question?). Reviewing them measures
retrieval; it says nothing about whether a finding is supported.

**No review has been done.** Every count reported from this directory is
zero reviewed, and `report` says that nothing is measured.

## What is here

- `candidates.jsonl`: 41 findings exported from eight deterministic
  assessments, one per topic of the synthetic corpus, run on 2026-10-16 with
  graph v3 against the fictional Meridian manual (database `regdelta_demo`).
  Each record holds:
  - the run, the finding id, the impact classification and the exact
    rationale;
  - the circular quotation with its document SHA-256, code-point offsets and
    300 characters of context either side, plus the obligation it came from;
  - the policy clause (pack name and version, clause number and heading, its
    full text) and the clause quotation with clause-local offsets. A
    `NO_MATCH` verdict quotes no clause, so its quotation is empty and the
    reviewer reads the whole clause;
  - the generator: provider, model, graph version, and whether the output is
    from the deterministic rule-based judge or a real model;
  - `snapshot_sha256` over all of the above.

  The analyst's accept/reject decision is not exported: it is a workflow
  record, and showing it would anchor the reviewer.
- `reviews.jsonl` (created by the first review): append-only rows of
  `record_id`, `snapshot_sha256`, `label`, `reviewer {id, type: "human"}`,
  `reviewed_at` (ISO time with timezone) and `notes`.

What the 41 candidates can and cannot show: they are outputs of the
deterministic rule-based judge on generated circulars and a fictional manual.
A review of them measures that judge's explanations, not a language model's,
and not performance on real SEBI documents.

## Labels

| Label | Use it when |
|---|---|
| `supported` | Read in context, the circular and policy quotations support the impact classification and the rationale. |
| `unsupported` | They do not, or they contradict it (including a `NO_MATCH` where the clause does address the obligation). |
| `insufficient` | The evidence shown is not enough to decide, or the case is genuinely ambiguous. |

Judge only the evidence shown and the rationale given; do not credit a
finding for a reason it does not state.

## Doing the review

```bash
python -m evaluation.support_review status                     # what is pending
POSTGRES_DB=regdelta_demo python -m evaluation.support_review validate --db
python -m evaluation.support_review show <record_id>           # one record, with its review history
python -m evaluation.support_review review --reviewer "Full Name"
python -m evaluation.support_review report --out evaluation/reports/support_review.md
```

`review` runs only in a terminal. It shows each pending record, takes `s`,
`u` or `i` and optional notes, and appends the answer at once. Enter skips a
record and `q` stops; anything else is not a label and is skipped, never
saved. To change a review, review the record again: the later row becomes the
current one and the earlier stays as history.

`validate --db` re-checks that every quotation still sits at its offsets in
the database it came from and that the circular's checksum is unchanged.

## What counts

A review counts only if it is valid (one of the three labels, a named human
reviewer, a time with a timezone) and current (its `snapshot_sha256` equals
the candidate's). Re-exporting a run whose evidence or rationale changed
gives the candidate a new hash, and older reviews of it become stale. The
report lists candidates, current reviews, pending, stale and invalid rows, and
per group (generator × corpus) the supported, unsupported and insufficient
counts and the supported share of decisive reviews with a Wilson interval.
Insufficient reviews are reported beside that share, never folded into it.

`report --judge labels.jsonl` compares a model judge's labels
(`record_id`, `snapshot_sha256`, `label`) with the current human ones on
decisive pairs: raw agreement and Cohen's kappa, which is reported as
undefined, not 1.0, when both raters give every pair the same label. No model
judge exists in this repository; the comparison is ready for one.

## Adding real-model findings

After a real-provider assessment (see `docs/demo-script.md`, provider smoke
run), export it the same way: `python -m evaluation.support_review export
--run <run_id>`. Its records are grouped as `real model` and reported apart
from the deterministic ones.
