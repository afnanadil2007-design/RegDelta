# Product

<!-- impeccable:product-schema 1 -->

Source of each fact: the owner's master brief for the 2026-10 overhaul, the
Impeccable init answers given on 2026-10-15 (marked *confirmed*), or the
repository itself (marked *repository*).

## Platform

web

## Users

- **Primary — regulatory-change compliance analyst** (*confirmed*). Works at a
  SEBI-regulated intermediary such as a stock broker. When a new circular is
  issued they read it, see which obligations it imposes, check each against
  the firm's internal compliance manual, and accept or reject every machine
  finding before anything changes in policy.
- **Secondary — evaluators of the engineering** (*confirmed*): interviewers and
  academic reviewers walking through the system to judge its retrieval,
  verification, and evaluation work. They need provenance, methodology, and
  limitations to be inspectable from the UI, not only from the README.

## Product Purpose

Turn "read this circular and work out what it changes for us" into a
structured, auditable review (*repository*, README):

circular ingestion → obligation extraction → retrieval of policy clauses →
impact judgement per obligation–clause pair → verification of quoted evidence
→ analyst review.

Success is an analyst who can, for any finding, see which circular changed,
the exact cited passage, the policy clause it touches, what the machine
concluded and why, whether the quotes were located in the sources, and what
they themselves decided — and who never mistakes a machine interpretation or
a model score for a verified fact.

## Positioning

**Evidence-first review** (*confirmed*). Every finding is tied to verbatim
quotes resolved to exact character offsets in the circular and in the policy
clause. Three states are kept separate and visible: quote verification (did
the quoted text exist in the source), machine interpretation (the judged
impact and rationale), and analyst decision. Quote verification proves the
text exists, not that the interpretation is right.

## Operating Context

- Documents: SEBI-style circulars (numbered paragraphs, reference numbers,
  annexures, supersession language) and an internal compliance manual of
  numbered clauses (*repository*).
- Workflow surfaces (*repository*, routes): overview, circular list and
  detail, corpus search with four retrieval modes, assessments with a live
  agent trace and findings review, point-in-time ("as of") exploration of
  supersession, and an evaluation view.
- Runs locally against PostgreSQL + pgvector; assessments use either a real
  LLM provider (Groq or Anthropic, key required) or the deterministic
  rule-based provider used for the demo (*repository*).

## Capabilities and Constraints

- **Synthetic data must be labelled wherever it appears** (*confirmed*). The
  demo corpus is generated (`ingestion/generate_corpus.py`) and the policy
  pack describes a fictional broker; neither may be presented as real
  regulation or a real firm, and no metric may be fabricated.
- Scope: single-user and local, no authentication or multi-tenancy
  (*repository*, README "Data and limitations"; not re-confirmed as a binding
  commitment).
- Findings are review aids, not legal advice (*repository*, README and policy
  pack; not re-confirmed as a binding commitment).
- Terminology the UI must keep distinct: *quote status* (VERIFIED, FAILED,
  NOT_APPLICABLE), *impact type* (NEW_REQUIREMENT, MODIFIED, CONFLICT,
  ALREADY_COVERED, NO_MATCH), *analyst decision* (PENDING, ACCEPTED,
  REJECTED), *model confidence* (the model's own uncalibrated score), and
  *refusal* (retrieval declining to answer below the relevance threshold).
- Settled 2026-10-15: the real-source corpus is fetched through a manifest
  of URLs and checksums (`data/real_sources/manifest.jsonl`); its PDFs are
  not redistributed. Undecided: whether human-reviewed annotations will
  exist.

## Evidence on Hand

- Synthetic corpus manifest: `data/synthetic/manifest.jsonl` (300 generated
  circulars); fictional policy pack:
  `data/policy_packs/internal_compliance_manual_v1.md`.
- Evaluation datasets: `evaluation/datasets/` (citation-derived gold set,
  generator-derived extraction labels, hand-written refusal cases).
- Historical evaluation reports under `evaluation/results/historical/` carry
  commit `unknown`; they are history, not current results.
- Absent, and not to be fabricated: customers, testimonials, human relevance
  or support annotations, calibrated confidence. Real regulator documents
  exist only as a separate research corpus (`data/real_sources/`), never in the
  demo.

## Product Principles

1. **Evidence before interpretation.** Show the source text a claim rests on
   before, and visibly apart from, what the machine concluded about it.
2. **Unknown is unknown.** Missing cost, missing labels, unresolved
   references, and unavailable providers are stated, never rendered as zero
   or as success.
3. **The analyst decides.** Machine output is a proposal; acceptance is a
   human act that is recorded and survives a refresh.
4. **Measured, with provenance.** Every number shown traces to a stored run
   with its dataset, code identity, and configuration.
