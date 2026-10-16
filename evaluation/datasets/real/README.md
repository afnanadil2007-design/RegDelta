# Real-source annotations (provisional)

Relevance labels over official SEBI documents, for evaluating RegDelta on real
regulatory text. **Every record here is provisional**: the questions and labels
were drafted by a model (`annotator.type = "agent"`) and no person has
reviewed them yet. No metric is reported from them until they are reviewed.

They label retrieval relevance (does this passage answer this question?), so
reviewing them measures search, not whether an assessment's rationale is
supported by its evidence. That is a separate review:
[`../support/`](../support/README.md).

## The documents

`data/real_sources/manifest.jsonl` lists 18 documents fetched on 2026-10-15 by
`python -m ingestion.scrape_sebi`, with page URL, PDF URL, issue date, circular
number and SHA-256. The PDFs are not in the repository; re-fetch and verify
them with `make real-corpus`.

Selection rule (in `ingestion/scrape_sebi.py`, not a hand pick): the first
listing page of *Legal > Circulars* and of *Legal > Master Circulars* (25 most
recent each on the retrieval date), kept when the title matches the domain
keywords and none of the excluded topics. That gave 7 circulars and 11 master
circulars, fewer than the 20–30 aimed for; later listing pages are only
reachable through the site's JavaScript form. One circular
(`sebi_103277`, digital-accessibility timelines) is a scan with no text layer
and is not ingested without OCR.

## The candidate annotations

`annotations.jsonl`: 39 records for 33 questions over 16 documents.

- Passages were chosen by rule: paragraphs of 160–650 characters that contain
  "shall" and a topic keyword, at most three per document (first, middle and
  last match).
- One question was written per passage. Where the same passage appears in two
  versions of a master circular (2025 and 2026), the question has one record
  per version, marked `ambiguity: minor`.
- Because each question was written while reading its passage, it shares
  wording with it, which favours lexical retrieval. A reviewer should rephrase
  questions the way an analyst would ask them.
- Splits are by document family (a title and its later versions), so a passage
  repeated across versions cannot sit in both dev and test: 28 records in dev,
  11 in test.

## Reviewing

```bash
POSTGRES_DB=regdelta_real python -m evaluation.annotation validate   # offsets still match the text
python -m evaluation.annotation review --reviewer "Your Name"        # interactive, saves each answer
python -m evaluation.annotation status
POSTGRES_DB=regdelta_real python -m evaluation.annotation evaluate   # reviewed records only
```

A reviewed record names its human reviewer and the time; `validate` rejects a
"reviewed" record without both. The review history is kept on each record.
