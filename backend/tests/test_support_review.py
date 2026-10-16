"""Semantic-support review: only valid, current, human reviews ever count.

The candidates and reviews below are SYNTHETIC FIXTURES built for these tests
(kind ``synthetic_fixture``); they are not observed findings or real reviews.
The last test exports a real deterministic run from the test database.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from evaluation import support_review as sr


def fixture_candidate(
    record_id: str, rationale: str = "Clause 4.2 permits what the circular bars."
) -> dict:
    candidate = {
        "record_id": record_id,
        "kind": "synthetic_fixture",
        "assessment": {
            "run_id": "fixture",
            "status": "COMPLETED",
            "created_at": "2026-10-16T00:00:00+00:00",
        },
        "generator": {
            "provider": "deterministic",
            "model": "regdelta-rules-v1",
            "graph_version": "v3",
            "output": "deterministic rule-based judge",
            "deterministic": True,
        },
        "finding": {
            "finding_id": int(record_id.rsplit("/", 1)[-1]),
            "impact_type": "CONFLICT",
            "rationale": rationale,
            "quote_status": "VERIFIED",
            "score": 0.5,
            "score_kind": "rule term overlap",
        },
        "circular": {
            "circular_number": "FIXTURE/1",
            "title": "A constructed circular",
            "corpus": "synthetic",
            "source_url": "synthetic://fixture",
            "document_sha256": "0" * 64,
            "obligation": "Brokers shall collect margin before trading.",
            "char_start": 0,
            "char_end": 7,
            "quote": "Brokers",
            "context": {"before": "", "after": " shall collect margin"},
        },
        "policy": {
            "pack": "Fixture manual",
            "version": "1.0",
            "synthetic": True,
            "clause_number": "4.2",
            "heading": "Margin",
            "clause_char_start": 100,
            "clause_text": "Margin may be collected later.",
            "char_start": 0,
            "char_end": 6,
            "quote": "Margin",
            "context": {"before": "", "after": " may be collected later"},
        },
    }
    candidate["snapshot_sha256"] = sr.snapshot_hash(candidate)
    return candidate


def human_review(
    candidate: dict, label: str, at: str = "2026-10-16T10:00:00+00:00", **extra
) -> dict:
    review = {
        "record_id": candidate["record_id"],
        "snapshot_sha256": candidate["snapshot_sha256"],
        "label": label,
        "reviewer": {"id": "A. Reviewer", "type": "human"},
        "reviewed_at": at,
        "notes": None,
    }
    review.update(extra)
    return review


def write(path: Path, rows: list) -> Path:
    path.write_text(
        "".join((row if isinstance(row, str) else json.dumps(row)) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def files(tmp_path: Path):
    def make(candidates: list, reviews: list) -> sr.Ledger:
        return sr.load(
            write(tmp_path / "c.jsonl", candidates), write(tmp_path / "r.jsonl", reviews)
        )

    return make


def test_supported_unsupported_and_ambiguous_reviews_are_counted_separately(files) -> None:
    a, b, c = (fixture_candidate(f"fx/{i}") for i in (1, 2, 3))
    ledger = files(
        [a, b, c],
        [
            human_review(a, "supported"),
            human_review(b, "unsupported"),
            human_review(c, "insufficient"),
        ],
    )
    assert ledger.problems == [] and len(ledger.current) == 3
    group = sr.summarise(ledger)["deterministic rule-based judge, synthetic corpus"]
    assert dict(group["labels"]) == {"supported": 1, "unsupported": 1, "insufficient": 1}
    # The supported share counts decisive reviews only; the ambiguous one is beside it.
    assert group["decisive"] == 2 and group["supported_share"] == pytest.approx(0.5)


def test_a_record_without_a_review_is_pending_and_never_counts(files) -> None:
    a, b = fixture_candidate("fx/1"), fixture_candidate("fx/2")
    ledger = files([a, b], [human_review(a, "supported")])
    assert [c["record_id"] for c in ledger.pending] == ["fx/2"]
    assert sr.summarise(ledger)["deterministic rule-based judge, synthetic corpus"]["reviewed"] == 1


def test_a_review_of_an_earlier_snapshot_is_stale_after_the_evidence_changes(files) -> None:
    old = fixture_candidate("fx/1")
    review = human_review(old, "supported")
    edited = fixture_candidate("fx/1", rationale="A different rationale after re-export.")
    ledger = files([edited], [review])
    assert ledger.current == {}
    assert ledger.stale == [{**review, "_line": 1}]
    assert [c["record_id"] for c in ledger.pending] == ["fx/1"]


def test_a_candidate_edited_by_hand_after_export_is_rejected(files) -> None:
    candidate = fixture_candidate("fx/1")
    candidate["finding"]["rationale"] = "Quietly edited."  # hash left as exported
    ledger = files([candidate], [human_review(candidate, "supported")])
    assert ledger.candidates == {}
    assert any("does not match its content" in p for p in ledger.problems)


@pytest.mark.parametrize(
    ("row", "problem"),
    [
        ("{not json", "not JSON"),
        ('["a", "list"]', "not a JSON object"),
        ({"label": "supported"}, "no record_id"),
        ("label=approved", "not JSON"),
    ],
)
def test_malformed_review_lines_are_problems_not_approvals(files, row, problem) -> None:
    candidate = fixture_candidate("fx/1")
    ledger = files([candidate], [row])
    assert ledger.current == {}
    assert any(problem in p for p in ledger.problems)


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"label": "approved"}, "is not one of"),
        ({"label": None}, "is not one of"),
        ({"reviewer": {"id": "gpt-judge", "type": "agent"}}, "not recorded as a human"),
        ({"reviewer": {"id": " ", "type": "human"}}, "has no name"),
        ({"reviewed_at": "yesterday"}, "not an ISO time"),
        ({"reviewed_at": "2026-10-16T10:00:00"}, "not an ISO time with a timezone"),
        ({"snapshot_sha256": None}, "no snapshot_sha256"),
        ({"record_id": "fx/404"}, "no candidate fx/404"),
    ],
)
def test_invalid_reviews_never_count(files, change, problem) -> None:
    candidate = fixture_candidate("fx/1")
    ledger = files([candidate], [{**human_review(candidate, "supported"), **change}])
    assert ledger.current == {}
    assert any(problem in p for p in ledger.problems), ledger.problems


def test_a_later_review_replaces_the_earlier_one_and_both_stay_in_history(files) -> None:
    candidate = fixture_candidate("fx/1")
    first = human_review(candidate, "supported")
    second = human_review(candidate, "unsupported", at="2026-10-17T09:00:00+00:00")
    ledger = files([candidate], [first, second])
    assert ledger.current["fx/1"]["label"] == "unsupported"
    assert [r["label"] for r in ledger.history["fx/1"]] == ["supported", "unsupported"]


def test_a_report_with_no_valid_review_measures_nothing(files) -> None:
    candidate = fixture_candidate("fx/1")
    ledger = files(
        [candidate], [human_review(candidate, "supported", reviewer={"id": "x", "type": "agent"})]
    )
    text = sr.report(ledger)
    assert "No valid human review exists, so nothing is measured" in text
    assert "| deterministic rule-based judge, synthetic corpus | 1 | 0 | 0 | 0 | 0 | — |" in text
    assert "0.000" not in text


def test_a_report_counts_only_current_human_reviews(files) -> None:
    a, b = fixture_candidate("fx/1"), fixture_candidate("fx/2")
    stale = human_review(fixture_candidate("fx/2", rationale="before re-export"), "unsupported")
    ledger = files([a, b], [human_review(a, "supported"), stale, '{"broken"'])
    text = sr.report(ledger)
    assert "with a current human review: 1; pending: 1" in text
    assert "1 stale review(s)" in text and "1 invalid review row(s)" in text
    assert "| 2 | 1 | 1 | 0 | 0 | 1.000 (0.207–1.000), n = 1 |" in text


def test_judge_comparison_uses_decisive_current_pairs_and_reports_degenerate_kappa(
    files, tmp_path: Path
) -> None:
    candidates = [fixture_candidate(f"fx/{i}") for i in range(1, 5)]
    reviews = [human_review(c, "supported") for c in candidates[:3]] + [
        human_review(candidates[3], "insufficient")
    ]
    ledger = files(candidates, reviews)
    judge = write(
        tmp_path / "judge.jsonl",
        [
            {
                "record_id": c["record_id"],
                "snapshot_sha256": c["snapshot_sha256"],
                "label": "supported",
            }
            for c in candidates
        ]
        + [{"record_id": "fx/1", "snapshot_sha256": "0" * 64, "label": "supported"}],
    )
    result = sr.judge_comparison(ledger, judge)
    metrics = result["metrics"]
    assert metrics.n_compared == 3
    assert result["excluded"] == {"insufficient or ambiguous": 1, "judged another snapshot": 1}
    # Judge and humans both said "supported" every time: kappa is 0/0, not 1.0.
    assert metrics.raw_agreement == pytest.approx(1.0)
    assert metrics.cohens_kappa is None
    assert "undefined" in sr.report(ledger, judge)


def test_a_no_match_verdict_needs_no_clause_quotation_but_others_do(files) -> None:
    no_match = fixture_candidate("fx/1")
    no_match["finding"]["impact_type"] = "NO_MATCH"
    no_match["policy"].update(char_start=None, char_end=None, quote=None, context=None)
    no_match["snapshot_sha256"] = sr.snapshot_hash(no_match)
    conflict = fixture_candidate("fx/2")
    conflict["policy"].update(quote=None, context=None)
    conflict["snapshot_sha256"] = sr.snapshot_hash(conflict)
    ledger = files([no_match, conflict], [])
    assert list(ledger.candidates) == ["fx/1"]
    assert ledger.candidate_problems == ["fx/2: no policy quotation"]
    assert "a NO_MATCH verdict quotes none" in sr.describe(no_match)


def test_describe_labels_fixtures_and_the_synthetic_corpus() -> None:
    text = sr.describe(fixture_candidate("fx/1"))
    assert "SYNTHETIC FIXTURE" in text
    assert "synthetic circular" in text and "fictional policy manual" in text
    assert "[[Brokers]]" in text and "[[Margin]]" in text


def test_export_of_a_real_run_carries_located_evidence_and_provenance(corpus) -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())
    response = client.post(
        "/api/assessments",
        json={
            "circular_id": corpus.id_of("SEBI/HO/MIRSD/MIRSD-PoD/CIR/P/2024/17"),
            "policy_pack_id": corpus.policy_pack_id,
        },
    )
    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]
    exported, _skipped = asyncio.run(sr._export_runs([run_id]))
    assert exported, "the run produced no finding with located quotations"
    for candidate in exported:
        assert sr.candidate_problems(candidate) == []
        assert candidate["kind"] == "assessment_finding"
        assert candidate["generator"]["deterministic"] is True
        assert candidate["circular"]["corpus"] == "synthetic"
        assert candidate["finding"]["quote_status"] == "VERIFIED"
    # Every quotation is still at its offsets in the database it came from.
    assert asyncio.run(sr._offset_problems(exported)) == []
