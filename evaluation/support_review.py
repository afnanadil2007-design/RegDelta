"""Semantic-support review: does a finding's evidence support its rationale?

This is a different question from ``evaluation/annotation.py``, which labels
whether a passage answers a *search question* (retrieval relevance). Here a
person reads one assessment finding (its impact classification, its exact
rationale, the circular quotation and the policy quotation, each in context)
and records one of three outcomes:

* ``supported``: read in context, the quotations support the impact and the
  rationale;
* ``unsupported``: they do not, or they contradict it;
* ``insufficient``: the evidence shown is not enough to decide, or the case
  is ambiguous.

Two files, beside each other in ``datasets/support/``:

* ``candidates.jsonl``: snapshots of findings whose quotations were located,
  exported from a database. ``snapshot_sha256`` covers everything a reviewer
  is shown, so any later change to the evidence or the rationale changes it.
* ``reviews.jsonl``: append-only human reviews. Each names its reviewer and
  time and the snapshot hash it judged; a review whose hash no longer matches
  its candidate is stale and never counts. Earlier reviews of a record stay in
  the file as its history.

Only valid, current reviews by a named human count towards a report. Export
writes candidates, never reviews, and nothing here labels a finding itself.
The analyst's accept/reject decision is not exported: it is a workflow record,
and showing it would anchor the reviewer.

    python -m evaluation.support_review export --run <run_id> [--run <run_id> ...]
    python -m evaluation.support_review status
    python -m evaluation.support_review validate [--db]   # --db re-checks offsets
    python -m evaluation.support_review show <record_id>
    python -m evaluation.support_review review --reviewer "Full Name"
    python -m evaluation.support_review report [--judge labels.jsonl] [--out report.md]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evaluation.metrics.groundedness import JudgeLabel, calibration_agreement
from evaluation.stats import wilson

DATASET_DIR = Path(__file__).resolve().parent / "datasets" / "support"
CANDIDATES = DATASET_DIR / "candidates.jsonl"
REVIEWS = DATASET_DIR / "reviews.jsonl"

LABELS: tuple[str, ...] = ("supported", "unsupported", "insufficient")
# What the snapshot hash covers: everything shown to the reviewer.
SNAPSHOT_FIELDS = ("kind", "assessment", "generator", "finding", "circular", "policy")
CONTEXT_CHARS = 300
SYNTHETIC_SCHEME = "synthetic://"


# --- records -------------------------------------------------------------------


def snapshot_hash(candidate: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON of the reviewed fields."""
    payload = {key: candidate.get(key) for key in SNAPSHOT_FIELDS}
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Rows of a JSON-lines file, and a problem for each line that is not an object."""
    rows: list[dict[str, Any]] = []
    problems: list[str] = []
    if not path.is_file():
        return rows, problems
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(f"{path.name}:{number}: not JSON ({exc.msg})")
            continue
        if not isinstance(row, dict):
            problems.append(f"{path.name}:{number}: not a JSON object")
            continue
        row["_line"] = number
        rows.append(row)
    return rows, problems


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            handle.write(json.dumps(clean, ensure_ascii=False) + "\n")


def candidate_problems(candidate: dict[str, Any]) -> list[str]:
    """Everything that makes a candidate unusable."""
    where = candidate.get("record_id") or f"candidates.jsonl:{candidate.get('_line')}"
    found = [
        f"{where}: missing {key}" for key in ("record_id", *SNAPSHOT_FIELDS) if key not in candidate
    ]
    if found:
        return found
    if candidate.get("snapshot_sha256") != snapshot_hash(candidate):
        found.append(f"{where}: snapshot_sha256 does not match its content (edited after export?)")
    if not str((candidate["circular"] or {}).get("quote") or "").strip():
        found.append(f"{where}: no circular quotation")
    policy = candidate["policy"] or {}
    if not str(policy.get("clause_text") or "").strip():
        found.append(f"{where}: no clause text")
    # A NO_MATCH verdict quotes no clause: by definition no clause text supports it.
    no_match = (candidate["finding"] or {}).get("impact_type") == "NO_MATCH"
    if not no_match and not str(policy.get("quote") or "").strip():
        found.append(f"{where}: no policy quotation")
    if not str((candidate["finding"] or {}).get("rationale", "")).strip():
        found.append(f"{where}: no rationale")
    return found


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


@dataclass
class Ledger:
    """Candidates and reviews, sorted into what counts and why the rest does not."""

    candidates: dict[str, dict[str, Any]] = field(default_factory=dict)
    current: dict[str, dict[str, Any]] = field(default_factory=dict)  # record_id -> review
    history: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    stale: list[dict[str, Any]] = field(default_factory=list)
    candidate_problems: list[str] = field(default_factory=list)
    review_problems: list[str] = field(default_factory=list)

    @property
    def problems(self) -> list[str]:
        return self.candidate_problems + self.review_problems

    @property
    def pending(self) -> list[dict[str, Any]]:
        return [c for rid, c in self.candidates.items() if rid not in self.current]


def review_problem(review: dict[str, Any]) -> str | None:
    """Why a review row can never count (stale reviews are handled separately)."""
    where = f"reviews.jsonl:{review.get('_line')}"
    if not isinstance(review.get("record_id"), str):
        return f"{where}: no record_id"
    if review.get("label") not in LABELS:
        return f"{where}: label {review.get('label')!r} is not one of {LABELS}"
    reviewer = review.get("reviewer")
    if not isinstance(reviewer, dict) or reviewer.get("type") != "human":
        return f"{where}: the reviewer is not recorded as a human"
    if not str(reviewer.get("id", "")).strip():
        return f"{where}: the reviewer has no name"
    if _parse_time(review.get("reviewed_at")) is None:
        return f"{where}: reviewed_at is not an ISO time with a timezone"
    if not isinstance(review.get("snapshot_sha256"), str):
        return f"{where}: no snapshot_sha256"
    return None


def load(candidates_path: Path = CANDIDATES, reviews_path: Path = REVIEWS) -> Ledger:
    ledger = Ledger()
    rows, ledger.candidate_problems = read_jsonl(candidates_path)
    for candidate in rows:
        found = candidate_problems(candidate)
        if found:
            ledger.candidate_problems += found
            continue
        if candidate["record_id"] in ledger.candidates:
            ledger.candidate_problems.append(f"{candidate['record_id']}: exported twice")
            continue
        ledger.candidates[candidate["record_id"]] = candidate

    reviews, ledger.review_problems = read_jsonl(reviews_path)
    for review in reviews:
        if problem := review_problem(review):
            ledger.review_problems.append(problem)
            continue
        candidate = ledger.candidates.get(review["record_id"])
        if candidate is None:
            ledger.review_problems.append(
                f"reviews.jsonl:{review['_line']}: no candidate {review['record_id']}"
            )
            continue
        ledger.history[review["record_id"]].append(review)
        if review["snapshot_sha256"] != candidate["snapshot_sha256"]:
            ledger.stale.append(review)
        else:
            ledger.current[review["record_id"]] = review  # later rows replace earlier ones
    return ledger


# --- export --------------------------------------------------------------------


def _context(text: str, start: int, end: int) -> dict[str, str]:
    return {
        "before": text[max(0, start - CONTEXT_CHARS) : start],
        "after": text[end : end + CONTEXT_CHARS],
    }


async def _export_runs(run_ids: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """Candidates for every finding with located quotes, and the ids skipped."""
    from sqlalchemy import select

    from app.db.models.assessment import AgentRun, Assessment, Finding
    from app.db.models.corpus import Circular, Obligation
    from app.db.models.enums import TERMINAL_STATUSES, QuoteStatus
    from app.db.models.policy import PolicyClause, PolicyPack
    from app.db.session import get_sessionmaker

    exported: list[dict[str, Any]] = []
    skipped: list[str] = []
    async with get_sessionmaker()() as session:
        for run_id in run_ids:
            assessment = (
                await session.execute(
                    select(Assessment).where(Assessment.run_id == uuid.UUID(run_id))
                )
            ).scalar_one_or_none()
            if assessment is None:
                raise SystemExit(f"no assessment with run_id {run_id} in this database")
            if assessment.status not in TERMINAL_STATUSES:
                raise SystemExit(
                    f"run {run_id} is {assessment.status.value}; export finished runs only"
                )
            agent_run = (
                await session.execute(
                    select(AgentRun).where(AgentRun.assessment_id == assessment.id)
                )
            ).scalar_one()
            circular = await session.get(Circular, assessment.circular_id)
            pack = await session.get(PolicyPack, assessment.policy_pack_id)
            assert circular is not None and pack is not None
            findings = (
                await session.execute(
                    select(Finding)
                    .where(
                        Finding.assessment_id == assessment.id,
                        Finding.quote_status == QuoteStatus.VERIFIED,
                    )
                    .order_by(Finding.id)
                )
            ).scalars()
            deterministic = agent_run.provider == "deterministic"
            for finding in findings:
                obligation = await session.get(Obligation, finding.obligation_id)
                clause = (
                    await session.get(PolicyClause, finding.policy_clause_id)
                    if finding.policy_clause_id
                    else None
                )
                c_start, c_end = finding.circular_span_start, finding.circular_span_end
                if obligation is None or clause is None or c_start is None or c_end is None:
                    skipped.append(f"{run_id}/{finding.id}")  # no located evidence to review
                    continue
                # Clause spans index the policy pack's source; the clause's own
                # text starts at clause.char_start. A NO_MATCH verdict has none.
                p_start = p_end = None
                if finding.clause_span_start is not None and finding.clause_span_end is not None:
                    p_start = finding.clause_span_start - clause.char_start
                    p_end = finding.clause_span_end - clause.char_start
                candidate: dict[str, Any] = {
                    "record_id": f"{run_id}/{finding.id}",
                    "kind": "assessment_finding",
                    "assessment": {
                        "run_id": run_id,
                        "status": assessment.status.value,
                        "created_at": assessment.created_at.isoformat(),
                    },
                    "generator": {
                        "provider": agent_run.provider,
                        "model": agent_run.model,
                        "graph_version": agent_run.graph_version,
                        "output": "deterministic rule-based judge"
                        if deterministic
                        else "real model",
                        "deterministic": deterministic,
                    },
                    "finding": {
                        "finding_id": finding.id,
                        "impact_type": finding.impact_type.value,
                        "rationale": finding.rationale,
                        "quote_status": finding.quote_status.value,
                        "score": finding.confidence,
                        "score_kind": "rule term overlap"
                        if deterministic
                        else "model-stated, uncalibrated",
                    },
                    "circular": {
                        "circular_number": circular.circular_number,
                        "title": circular.title,
                        "corpus": "synthetic"
                        if (circular.source_url or "").startswith(SYNTHETIC_SCHEME)
                        else "real",
                        "source_url": circular.source_url,
                        "document_sha256": circular.checksum,
                        "obligation": obligation.text,
                        "char_start": c_start,
                        "char_end": c_end,
                        "quote": circular.full_text[c_start:c_end],
                        "context": _context(circular.full_text, c_start, c_end),
                    },
                    "policy": {
                        "pack": pack.name,
                        "version": pack.version,
                        "synthetic": pack.is_synthetic,
                        "clause_number": clause.clause_number,
                        "heading": clause.heading,
                        "clause_char_start": clause.char_start,
                        "clause_text": clause.text,
                        "char_start": p_start,
                        "char_end": p_end,
                        "quote": None if p_start is None else clause.text[p_start:p_end],
                        "context": None
                        if p_start is None or p_end is None
                        else _context(clause.text, p_start, p_end),
                    },
                }
                candidate["snapshot_sha256"] = snapshot_hash(candidate)
                exported.append(candidate)
    return exported, skipped


def export(run_ids: list[str], path: Path = CANDIDATES) -> tuple[int, int, list[str]]:
    """Add the runs' findings to the candidates file; (exported, replaced, skipped)."""
    rows, problems = read_jsonl(path)
    if problems:
        raise SystemExit("the candidates file is damaged:\n" + "\n".join(problems))
    by_id = {row["record_id"]: row for row in rows}
    fresh, skipped = asyncio.run(_export_runs(run_ids))
    replaced = sum(
        1
        for c in fresh
        if c["record_id"] in by_id
        and by_id[c["record_id"]]["snapshot_sha256"] != c["snapshot_sha256"]
    )
    for candidate in fresh:
        candidate["exported_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        by_id[candidate["record_id"]] = candidate
    _write_jsonl(path, list(by_id.values()))
    return len(fresh), replaced, skipped


async def _offset_problems(candidates: list[dict[str, Any]]) -> list[str]:
    """Quotations that no longer sit at their offsets in the configured database."""
    from sqlalchemy import select

    from app.db.models.corpus import Circular
    from app.db.models.policy import PolicyClause, PolicyPack
    from app.db.session import get_sessionmaker

    found: list[str] = []
    async with get_sessionmaker()() as session:
        for c in candidates:
            circ = c["circular"]
            row = (
                await session.execute(
                    select(Circular.full_text, Circular.checksum).where(
                        Circular.circular_number == circ["circular_number"]
                    )
                )
            ).one_or_none()
            if row is None:
                found.append(
                    f"{c['record_id']}: circular {circ['circular_number']} is not in this database"
                )
            elif row.checksum != circ["document_sha256"]:
                found.append(f"{c['record_id']}: the circular's file checksum differs")
            elif row.full_text[circ["char_start"] : circ["char_end"]] != circ["quote"]:
                found.append(f"{c['record_id']}: circular offsets no longer point at the quotation")
            pol = c["policy"]
            text = (
                await session.execute(
                    select(PolicyClause.text)
                    .join(PolicyPack, PolicyPack.id == PolicyClause.policy_pack_id)
                    .where(
                        PolicyPack.name == pol["pack"],
                        PolicyPack.version == pol["version"],
                        PolicyClause.clause_number == pol["clause_number"],
                    )
                )
            ).scalar_one_or_none()
            if text is None:
                found.append(
                    f"{c['record_id']}: clause {pol['clause_number']} is not in this database"
                )
            elif text != pol["clause_text"]:
                found.append(f"{c['record_id']}: the clause text has changed")
            elif (
                pol["quote"] is not None
                and text[pol["char_start"] : pol["char_end"]] != pol["quote"]
            ):
                found.append(f"{c['record_id']}: clause offsets no longer point at the quotation")
    return found


# --- showing and reviewing -----------------------------------------------------


def describe(candidate: dict[str, Any]) -> str:
    """Everything a reviewer needs to judge one record, and to find the originals."""
    finding, circ, pol, gen = (
        candidate["finding"],
        candidate["circular"],
        candidate["policy"],
        candidate["generator"],
    )
    labels = []
    if candidate["kind"] != "assessment_finding":
        labels.append("SYNTHETIC FIXTURE, constructed for a test, not an observed finding")
    if circ["corpus"] == "synthetic":
        labels.append("synthetic circular (generated demo corpus, not a real SEBI document)")
    if pol.get("synthetic"):
        labels.append("fictional policy manual")

    def in_context(evidence: dict[str, Any]) -> str:
        before, after = evidence["context"]["before"][-160:], evidence["context"]["after"][:160]
        return f"  ...{before}[[{evidence['quote']}]]{after}..."

    lines = [
        "=" * 78,
        candidate["record_id"],
        *([f"  {'; '.join(labels)}"] if labels else []),
        f"Generated by: {gen['output']} ({gen['provider']} / {gen['model']}, "
        f"graph {gen['graph_version']})",
        f"Impact: {finding['impact_type']}    score: {finding['score']} ({finding['score_kind']})",
        f"Rationale: {finding['rationale']}",
        "",
        f"Circular {circ['circular_number']}: {circ['title']}",
        f"  file sha256 {circ['document_sha256']}, "
        f"characters {circ['char_start']}-{circ['char_end']}",
        f"  obligation: {circ['obligation']}",
        in_context(circ),
        "",
        f"Policy: {pol['pack']} v{pol['version']}, clause {pol['clause_number']} "
        f"{pol['heading'] or ''}",
        *(
            [
                f"  clause characters {pol['char_start']}-{pol['char_end']} "
                f"(the clause starts at {pol['clause_char_start']} in the pack)",
                in_context(pol),
            ]
            if pol["quote"]
            else [
                "  no clause quotation (a NO_MATCH verdict quotes none); the whole clause is below"
            ]
        ),
        f"  clause text: {pol['clause_text']}",
    ]
    return "\n".join(lines)


def _append_review(review: dict[str, Any], path: Path = REVIEWS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(review, ensure_ascii=False) + "\n")


ANSWERS = {"s": "supported", "u": "unsupported", "i": "insufficient"}


def review(reviewer: str, ledger: Ledger) -> int:
    """Walk the pending records in a terminal; each answer is saved at once."""
    if not sys.stdin.isatty():
        raise SystemExit("review is interactive; run it in a terminal")
    if not reviewer.strip():
        raise SystemExit("--reviewer must be your name")
    pending = ledger.pending
    print(
        f"{len(pending)} records to review. Enter skips one; q quits. Nothing is saved for a skip."
    )
    saved = 0
    for candidate in pending:
        print(describe(candidate))
        answer = (
            input(
                "Does the evidence support the rationale? [s]upported / [u]nsupported / "
                "[i]nsufficient or ambiguous / Enter skips / q quits: "
            )
            .strip()
            .lower()
        )
        if answer == "q":
            break
        if answer not in ANSWERS:
            if answer:
                print(f"{answer!r} is not one of s, u, i: skipped, nothing saved.")
            continue
        notes = input("Notes (optional, Enter for none): ").strip() or None
        _append_review(
            {
                "record_id": candidate["record_id"],
                "snapshot_sha256": candidate["snapshot_sha256"],
                "label": ANSWERS[answer],
                "reviewer": {"id": reviewer.strip(), "type": "human"},
                "reviewed_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "notes": notes,
            }
        )
        saved += 1
    print(f"{saved} review(s) saved to {REVIEWS}")
    return saved


# --- reporting -----------------------------------------------------------------


def _group(candidate: dict[str, Any]) -> str:
    return f"{candidate['generator']['output']}, {candidate['circular']['corpus']} corpus"


def summarise(ledger: Ledger) -> dict[str, dict[str, Any]]:
    """Per generator and corpus: candidates, reviewed counts and the supported share."""
    groups: dict[str, dict[str, Any]] = {}
    for record_id, candidate in ledger.candidates.items():
        group = groups.setdefault(_group(candidate), {"candidates": 0, "labels": Counter()})
        group["candidates"] += 1
        if record_id in ledger.current:
            group["labels"][ledger.current[record_id]["label"]] += 1
    for group in groups.values():
        labels = group["labels"]
        decisive = labels["supported"] + labels["unsupported"]
        group["reviewed"] = sum(labels.values())
        group["decisive"] = decisive
        group["supported_share"] = labels["supported"] / decisive if decisive else None
        group["interval"] = wilson(labels["supported"], decisive)
    return groups


def judge_comparison(ledger: Ledger, path: Path) -> dict[str, Any]:
    """A model judge's labels against current human labels, on decisive pairs only."""
    rows, problems = read_jsonl(path)
    pairs: list[JudgeLabel] = []
    excluded = Counter()
    for row in rows:
        record_id = row.get("record_id")
        human = ledger.current.get(record_id) if isinstance(record_id, str) else None
        candidate = ledger.candidates.get(record_id) if isinstance(record_id, str) else None
        if candidate is None:
            excluded["unknown record"] += 1
        elif row.get("snapshot_sha256") != candidate["snapshot_sha256"]:
            excluded["judged another snapshot"] += 1
        elif row.get("label") not in LABELS:
            excluded["judge label not recognised"] += 1
        elif human is None:
            excluded["no current human review"] += 1
        elif "insufficient" in (row["label"], human["label"]):
            excluded["insufficient or ambiguous"] += 1
        else:
            pairs.append(
                JudgeLabel(
                    candidate["finding"]["finding_id"],
                    row["label"] == "supported",
                    human["label"] == "supported",
                )
            )
    return {
        "metrics": calibration_agreement(pairs),
        "excluded": dict(excluded),
        "problems": problems,
    }


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def report(ledger: Ledger, judge: Path | None = None) -> str:
    """A Markdown report built only from valid, current, human reviews."""
    reviewed = len(ledger.current)
    lines = [
        "# Semantic-support review",
        "",
        f"Prepared {datetime.now(UTC).isoformat(timespec='seconds')} from "
        f"`{CANDIDATES.name}` and `{REVIEWS.name}`.",
        "",
        f"- Candidates: {len(ledger.candidates)}; with a current human review: {reviewed}; "
        f"pending: {len(ledger.pending)}.",
        f"- Not counted: {len(ledger.stale)} stale review(s) (the candidate changed after "
        f"review), {len(ledger.review_problems)} invalid review row(s); "
        f"{len(ledger.candidate_problems)} candidate(s) rejected by validation.",
        "",
    ]
    if reviewed == 0:
        lines += [
            "**No valid human review exists, so nothing is measured.** The table lists "
            "the candidates awaiting review; it is not a result.",
            "",
        ]
    lines += [
        "| Group | Candidates | Reviewed | Supported | Unsupported | Insufficient | "
        "Supported share of decisive (95% CI) |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, group in sorted(summarise(ledger).items()):
        labels = group["labels"]
        interval = group["interval"]
        share = (
            "—"
            if group["supported_share"] is None
            else f"{group['supported_share']:.3f} ({interval[0]:.3f}–{interval[1]:.3f}), "
            f"n = {group['decisive']}"
        )
        lines.append(
            f"| {name} | {group['candidates']} | {group['reviewed']} | {labels['supported']} | "
            f"{labels['unsupported']} | {labels['insufficient']} | {share} |"
        )
    lines += [
        "",
        "The supported share counts only decisive reviews (supported or unsupported); "
        "insufficient-or-ambiguous reviews are reported beside it, never folded in. It "
        "measures agreement between these assessment explanations and one set of human "
        "evidence reviews, on these records only.",
    ]
    if judge is not None:
        result = judge_comparison(ledger, judge)
        metrics = result["metrics"]
        lines += [
            "",
            f"## Model judge against human reviews (`{judge.name}`)",
            "",
            f"- Pairs compared: {metrics.n_compared}; excluded: {result['excluded'] or 'none'}.",
            f"- Raw agreement: {_fmt(metrics.raw_agreement)}; Cohen's kappa: "
            f"{_fmt(metrics.cohens_kappa)} ({metrics.interpretation}).",
            "- Agreement on this set only; it is not a general calibration of the judge.",
        ]
    return "\n".join(lines) + "\n"


# --- command line --------------------------------------------------------------


def status(ledger: Ledger) -> None:
    by_group = Counter(_group(c) for c in ledger.candidates.values())
    by_kind = Counter(c["kind"] for c in ledger.candidates.values())
    print(f"{len(ledger.candidates)} candidates in {CANDIDATES}")
    print("  by generator and corpus:", dict(by_group))
    print("  by kind:", dict(by_kind))
    print(f"  rejected by validation: {len(ledger.candidate_problems)}")
    print(
        f"reviews: {len(ledger.current)} current, {len(ledger.stale)} stale, "
        f"{len(ledger.review_problems)} invalid; pending {len(ledger.pending)}"
    )
    labels = Counter(r["label"] for r in ledger.current.values())
    print("  current labels:", dict(labels) or "none")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Semantic-support review of assessment findings.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser(
        "export", help="add finished runs' findings (from the configured database)"
    )
    run.add_argument("--run", action="append", required=True, dest="runs", metavar="RUN_ID")
    sub.add_parser("status")
    check = sub.add_parser("validate")
    check.add_argument(
        "--db", action="store_true", help="re-check offsets in the configured database"
    )
    show = sub.add_parser("show")
    show.add_argument("record_id")
    walk = sub.add_parser("review")
    walk.add_argument("--reviewer", required=True, help="your name, recorded on every review")
    out = sub.add_parser("report")
    out.add_argument("--judge", type=Path, help="JSONL of model-judge labels to compare")
    out.add_argument("--out", type=Path, help="also write the report here")
    args = parser.parse_args(argv)

    if args.command == "export":
        exported, replaced, skipped = export(args.runs)
        if skipped:
            print(f"skipped {len(skipped)} finding(s) with no located evidence: {skipped}")
        print(
            f"{exported} candidates exported ({replaced} replaced a changed snapshot) "
            f"to {CANDIDATES}"
        )
        return 0
    ledger = load()
    if args.command == "status":
        status(ledger)
        return 0
    if args.command == "show":
        candidate = ledger.candidates.get(args.record_id)
        if candidate is None:
            print(f"no candidate {args.record_id}")
            return 1
        print(describe(candidate))
        for past in ledger.history.get(args.record_id, []):
            mark = (
                "current" if ledger.current.get(args.record_id) is past else "superseded or stale"
            )
            print(
                f"  review {past['label']} by {past['reviewer']['id']} "
                f"at {past['reviewed_at']} ({mark})"
            )
        return 0
    if args.command == "review":
        review(args.reviewer, ledger)
        return 0
    if args.command == "report":
        text = report(ledger, args.judge)
        print(text)
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        return 0
    found = list(ledger.problems)
    if args.db:
        found += asyncio.run(_offset_problems(list(ledger.candidates.values())))
    for line in found:
        print(line)
    print(f"{len(ledger.candidates)} candidates, {len(found)} problems")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
