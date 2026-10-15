"""The annotation workflow's guarantees, on explicitly synthetic records."""

from __future__ import annotations

import asyncio

from evaluation.annotation import (
    Annotation,
    Passage,
    Person,
    evaluate,
    family_of,
    problems,
    quote_hash,
    split_for,
)

# Synthetic stand-in for an ingested document; not real regulator text.
TEXT = "SYNTHETIC. Stock brokers shall upload client KYC to a KRA within three working days."
NUMBER = "SYNTH/TEST/1"
FAMILY = "synthetic kyc circular"


def record(**changes) -> Annotation:
    quote = "upload client KYC to a KRA within three working days"
    start = TEXT.index(quote)
    base = Annotation(
        question_id="q1",
        question="How quickly must a broker upload KYC records?",
        topic="kyc",
        family=FAMILY,
        passage=Passage(NUMBER, "0" * 64, start, start + len(quote), quote, quote_hash(quote)),
        relevance="relevant",
        ambiguity="none",
        annotator=Person("draft-model", "agent"),
        split=split_for(FAMILY),
    )
    for key, value in changes.items():
        setattr(base, key, value)
    return base


def test_a_provisional_agent_label_is_valid_but_not_evidence() -> None:
    assert problems([record()], {NUMBER: TEXT}) == []


def test_reviewed_requires_a_named_human_and_a_time() -> None:
    by_agent = record(review_status="reviewed", reviewer=Person("draft-model", "agent"))
    found = problems([by_agent], {NUMBER: TEXT})
    assert any("without a human reviewer" in p for p in found)
    assert any("without a review time" in p for p in found)
    by_human = record(
        review_status="reviewed",
        reviewer=Person("A. Reviewer", "human"),
        reviewed_at="2026-10-15T10:00:00+00:00",
    )
    assert problems([by_human], {NUMBER: TEXT}) == []


def test_offsets_are_checked_against_the_ingested_text() -> None:
    moved = record()
    moved.passage.char_start += 1
    assert any("offsets" in p for p in problems([moved], {NUMBER: TEXT}))
    assert any("not ingested" in p for p in problems([record()], {}))


def test_a_question_cannot_leave_its_documents_split() -> None:
    other = "test" if split_for(FAMILY) == "dev" else "dev"
    assert any("split" in p for p in problems([record(split=other)]))


def test_an_edited_quote_is_caught_by_its_hash() -> None:
    edited = record()
    edited.passage.quote = edited.passage.quote.upper()
    assert any("hash" in p for p in problems([edited]))


def test_versions_of_one_document_share_a_family() -> None:
    assert family_of("Master Circular for Investment Advisers (2025)") == family_of(
        "Master Circular for Investment Advisers"
    )


def test_evaluation_reads_reviewed_labels_only() -> None:
    reviewed = record(
        question_id="real-001",
        review_status="reviewed",
        reviewer=Person("A. Reviewer", "human"),
        reviewed_at="2026-10-15T10:00:00+00:00",
    )
    provisional = record(question_id="real-002", question="Something else entirely?")

    async def retriever(query: str) -> list[str]:
        return [NUMBER] if "KYC" in query else ["OTHER"]

    result = asyncio.run(evaluate([reviewed, provisional], retriever))
    assert result["questions"] == 1
    assert result["provisional_records_ignored"] == 1
    assert result["hit@10"] == 1.0
    assert asyncio.run(evaluate([provisional], retriever))["hit@10"] is None
