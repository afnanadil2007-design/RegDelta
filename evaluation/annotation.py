"""Relevance annotations for the real-source corpus, and their review workflow.

A record pairs a question with one passage of one official document and says
whether the passage answers it. Every record names who labelled it and how
far it has been reviewed:

* ``annotator.type`` is ``agent`` for candidates drafted by a model (this
  repository's starting set) and ``human`` for a person's own labels.
* ``review_status`` is ``provisional`` until a named human reviewer confirms
  or corrects the label (``reviewed``), or flags it (``disputed``).

Only ``reviewed`` records may feed a reported metric; a provisional label is
preparation, not evidence. ``validate`` enforces that a reviewed record has a
human reviewer, that its passage offsets still match the ingested text, and
that every question sits in its document family's split. Families (a
document and its later versions, e.g. the 2025 and 2026 master circulars for
investment advisers) are split, not questions, so the same passage in two
versions cannot leak between dev and test.

    python -m evaluation.annotation status
    python -m evaluation.annotation validate            # offsets checked against the database
    python -m evaluation.annotation review --reviewer "Full Name"
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

DATASET = Path(__file__).resolve().parent / "datasets" / "real" / "annotations.jsonl"

Relevance = Literal["relevant", "partial", "not_relevant"]
Ambiguity = Literal["none", "minor", "major"]
ReviewStatus = Literal["provisional", "reviewed", "disputed"]
RELEVANCE: tuple[str, ...] = ("relevant", "partial", "not_relevant")
AMBIGUITY: tuple[str, ...] = ("none", "minor", "major")


@dataclass
class Person:
    id: str
    type: Literal["human", "agent"]


@dataclass
class Passage:
    circular_number: str
    document_sha256: str
    char_start: int  # code-point offsets into the ingested full text
    char_end: int
    quote: str  # the passage itself, kept short; re-checked against the source
    quote_sha256: str


@dataclass
class Annotation:
    question_id: str
    question: str
    topic: str
    family: str  # the document's title without its year: versions share a family
    passage: Passage
    relevance: Relevance
    ambiguity: Ambiguity
    annotator: Person
    review_status: ReviewStatus = "provisional"
    reviewer: Person | None = None
    reviewed_at: str | None = None
    split: Literal["dev", "test"] = "dev"
    notes: str | None = None
    history: list[dict] = field(default_factory=list)

    @staticmethod
    def from_json(row: dict) -> Annotation:
        row = dict(row)
        row["passage"] = Passage(**row["passage"])
        row["annotator"] = Person(**row["annotator"])
        row["reviewer"] = Person(**row["reviewer"]) if row.get("reviewer") else None
        return Annotation(**row)


def family_of(title: str) -> str:
    """'Master Circular for Investment Advisers' for every year's version."""
    return re.sub(r"\s+", " ", re.sub(r"[\d()]+", " ", title)).strip().lower()


def split_for(family: str) -> Literal["dev", "test"]:
    """A family's split, fixed by its name: about a third go to dev."""
    digest = int(hashlib.sha256(family.encode()).hexdigest(), 16)
    return "dev" if digest % 3 == 0 else "test"


def quote_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def read(path: Path = DATASET) -> list[Annotation]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as handle:
        return [Annotation.from_json(json.loads(line)) for line in handle if line.strip()]


def write(records: list[Annotation], path: Path = DATASET) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


def problems(records: list[Annotation], texts: dict[str, str] | None = None) -> list[str]:
    """Everything that would make a record unusable as evidence."""
    found: list[str] = []
    seen: set[str] = set()
    for r in records:
        where = r.question_id
        if where in seen:
            found.append(f"{where}: duplicate question id")
        seen.add(where)
        if r.relevance not in RELEVANCE:
            found.append(f"{where}: relevance {r.relevance!r} is not one of {RELEVANCE}")
        if r.ambiguity not in AMBIGUITY:
            found.append(f"{where}: ambiguity {r.ambiguity!r} is not one of {AMBIGUITY}")
        if r.review_status == "reviewed" and (r.reviewer is None or r.reviewer.type != "human"):
            found.append(f"{where}: marked reviewed without a human reviewer")
        if r.review_status == "reviewed" and not r.reviewed_at:
            found.append(f"{where}: marked reviewed without a review time")
        if r.split != split_for(r.family):
            found.append(f"{where}: split {r.split} disagrees with its family's split")
        if quote_hash(r.passage.quote) != r.passage.quote_sha256:
            found.append(f"{where}: quote text does not match its recorded hash")
        if texts is not None:
            text = texts.get(r.passage.circular_number)
            if text is None:
                found.append(f"{where}: document {r.passage.circular_number} is not ingested")
            elif text[r.passage.char_start : r.passage.char_end] != r.passage.quote:
                found.append(f"{where}: offsets no longer point at the quoted passage")
    return found


async def _ingested_texts() -> dict[str, str]:
    from sqlalchemy import select

    from app.db.models.corpus import Circular
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        rows = await session.execute(select(Circular.circular_number, Circular.full_text))
        return dict(rows.all())


Retriever = Callable[[str], Awaitable[list[str]]]


async def evaluate(records: list[Annotation], retriever: Retriever, k: int = 10) -> dict:
    """Hit rate at ``k`` over *reviewed* questions only; provisional labels never count.

    A question is answered when any document holding one of its relevant
    passages is among the first ``k`` distinct documents retrieved.
    """
    reviewed = [
        r for r in records if r.review_status == "reviewed" and r.relevance != "not_relevant"
    ]
    questions: dict[str, set[str]] = {}
    text: dict[str, str] = {}
    for r in reviewed:
        key = r.question_id.split("-")[0] + "-" + r.question_id.split("-")[1]
        questions.setdefault(key, set()).add(r.passage.circular_number)
        text[key] = r.question
    hits = 0
    for key, relevant in questions.items():
        ranked = await retriever(text[key])
        hits += bool(relevant & set(ranked[:k]))
    return {
        "reviewed_records": len(reviewed),
        "questions": len(questions),
        "provisional_records_ignored": sum(r.review_status == "provisional" for r in records),
        f"hit@{k}": hits / len(questions) if questions else None,
    }


async def _hybrid_retriever(query: str) -> list[str]:
    from sqlalchemy import select

    from app.ai.retrieval.pipeline import retrieve
    from app.db.models.corpus import Circular
    from app.db.models.enums import RetrievalMode
    from app.db.session import get_sessionmaker
    from app.repositories.search import SearchFilters

    async with get_sessionmaker()() as session:
        result = await retrieve(
            session, query, mode=RetrievalMode.HYBRID, filters=SearchFilters(), top_k=20
        )
        numbers = dict((await session.execute(select(Circular.id, Circular.circular_number))).all())
    ranked: list[str] = []
    for hit in result.hits:
        number = numbers.get(hit.circular_id)
        if number and number not in ranked:
            ranked.append(number)
    return ranked


def status(records: list[Annotation]) -> None:
    print(f"{len(records)} records in {DATASET}")
    print("  review status:", dict(Counter(r.review_status for r in records)))
    print("  annotator type:", dict(Counter(r.annotator.type for r in records)))
    print("  relevance:", dict(Counter(r.relevance for r in records)))
    print("  split:", dict(Counter(r.split for r in records)))
    print("  documents:", len({r.passage.circular_number for r in records}))


def review(records: list[Annotation], reviewer: str) -> None:
    """Walk the provisional records in a terminal; every answer is saved at once."""
    if not sys.stdin.isatty():
        raise SystemExit("review is interactive; run it in a terminal")
    pending = [r for r in records if r.review_status == "provisional"]
    print(f"{len(pending)} provisional records. Enter keeps the current label; q quits.\n")
    for record in pending:
        print("=" * 78)
        print(f"{record.question_id}  [{record.topic}]  split {record.split}")
        print(f"Question: {record.question}")
        print(f"Document: {record.passage.circular_number}")
        print(f"Passage:  {record.passage.quote}")
        print(f"Draft label by {record.annotator.type} {record.annotator.id}: {record.relevance}")
        answer = input(
            "relevance [r]elevant / [p]artial / [n]ot relevant / [d]ispute / q: "
        ).strip()
        if answer == "q":
            break
        before = {"relevance": record.relevance, "status": record.review_status}
        if answer == "d":
            record.review_status = "disputed"
            record.notes = input("why disputed? ").strip() or record.notes
        else:
            record.relevance = {"r": "relevant", "p": "partial", "n": "not_relevant"}.get(
                answer, record.relevance
            )
            ambiguity = input("ambiguity [n]one / [m]inor / ma[j]or (Enter keeps): ").strip()
            record.ambiguity = {"n": "none", "m": "minor", "j": "major"}.get(
                ambiguity, record.ambiguity
            )
            record.review_status = "reviewed"
        record.reviewer = Person(id=reviewer, type="human")
        record.reviewed_at = datetime.now(UTC).isoformat(timespec="seconds")
        record.history.append({**before, "by": reviewer, "at": record.reviewed_at})
        write(records)
    status(records)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Real-source relevance annotations.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    check = sub.add_parser("validate")
    check.add_argument("--offline", action="store_true", help="skip the database offset check")
    run = sub.add_parser("review")
    run.add_argument("--reviewer", required=True, help="your name, recorded on every label")
    sub.add_parser("evaluate", help="hybrid hit@10 on reviewed questions (needs the real corpus)")
    args = parser.parse_args(argv)

    records = read()
    if args.command == "status":
        status(records)
        return 0
    if args.command == "review":
        review(records, args.reviewer)
        return 0
    if args.command == "evaluate":
        if not any(r.review_status == "reviewed" for r in records):
            print("No reviewed records: nothing to evaluate. Human review is pending;")
            print("provisional (model-drafted) labels are never used as evidence.")
            return 0
        print(json.dumps(asyncio.run(evaluate(records, _hybrid_retriever)), indent=2))
        return 0
    texts = None if args.offline else asyncio.run(_ingested_texts())
    found = problems(records, texts)
    for line in found:
        print(line)
    print(f"{len(records)} records, {len(found)} problems")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
