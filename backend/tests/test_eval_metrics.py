"""Stage 11 tests: extraction, refusal, groundedness, and performance metrics."""

from __future__ import annotations

import pytest
from evaluation.metrics.extraction import (
    ExtractionMetrics,
    LabelledObligation,
    PredictedObligation,
    actors_match,
    normalise_actor,
    spans_overlap,
)
from evaluation.metrics.extraction import (
    compute as compute_extraction,
)
from evaluation.metrics.groundedness import (
    JudgeLabel,
    Layer1Result,
    calibration_agreement,
    compute_layer1,
)
from evaluation.metrics.performance import StepSample, node_breakdown, percentile
from evaluation.metrics.refusal import (
    RefusalCase,
    RefusalOutcome,
    load_cases,
)
from evaluation.metrics.refusal import (
    compute as compute_refusal,
)

# --- extraction ---------------------------------------------------------


def _label(start: int, end: int, actor: str = "stock brokers") -> LabelledObligation:
    return LabelledObligation("C/1", "text", actor, start, end)


def _pred(start: int, end: int, actor: str | None = "stock brokers") -> PredictedObligation:
    return PredictedObligation("C/1", "text", actor, start, end)


def test_overlapping_span_and_matching_actor_is_a_match() -> None:
    metrics = compute_extraction([_pred(10, 60)], [_label(0, 50)])
    assert metrics.true_positives == 1
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0


def test_disjoint_spans_do_not_match() -> None:
    metrics = compute_extraction([_pred(100, 150)], [_label(0, 50)])
    assert metrics.true_positives == 0
    assert metrics.false_positives == 1
    assert metrics.false_negatives == 1


def test_overlap_alone_is_not_enough_when_actors_differ() -> None:
    """A sentence binding two parties holds two obligations, not one."""
    metrics = compute_extraction(
        [_pred(0, 50, "the compliance officer")], [_label(0, 50, "stock brokers")]
    )
    assert metrics.true_positives == 0


def test_each_label_is_claimed_at_most_once() -> None:
    """Five near-duplicate predictions score one TP and four FPs."""
    metrics = compute_extraction([_pred(0, 50) for _ in range(5)], [_label(0, 50)])
    assert metrics.true_positives == 1
    assert metrics.false_positives == 4


def test_predictions_in_another_circular_never_match() -> None:
    other = PredictedObligation("C/2", "text", "stock brokers", 0, 50)
    metrics = compute_extraction([other], [_label(0, 50)])
    assert metrics.true_positives == 0


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("Stock brokers", "stock broker", True),
        ("registered stock brokers", "stock brokers", True),
        ("The intermediary", "intermediaries", True),
        ("stock brokers", "compliance officer", False),
        (None, "stock brokers", False),
    ],
)
def test_actor_matching_normalises_plurality_and_articles(a, b, expected) -> None:
    assert actors_match(a, b) is expected


def test_normalise_actor_strips_articles() -> None:
    assert normalise_actor("The Stock Brokers") == "stock broker"
    assert normalise_actor(None) == ""


def test_spans_overlap_boundaries_are_exclusive() -> None:
    assert not spans_overlap(0, 10, 10, 20), "touching spans do not overlap"
    assert spans_overlap(0, 11, 10, 20)


def test_f1_is_zero_when_nothing_matches() -> None:
    metrics = ExtractionMetrics(0, 3, 4, 4, 3)
    assert metrics.f1 == 0.0


# --- refusal ------------------------------------------------------------


def _case(cid: str, should_refuse: bool) -> RefusalCase:
    return RefusalCase(cid, "q", should_refuse)


def test_refusal_rates_are_reported_separately() -> None:
    outcomes = [
        RefusalOutcome(_case("a", True), refused=True, top_score=0.1),    # correct
        RefusalOutcome(_case("b", True), refused=False, top_score=0.9),   # missed
        RefusalOutcome(_case("c", False), refused=False, top_score=0.8),  # correct
        RefusalOutcome(_case("d", False), refused=True, top_score=0.2),   # false refusal
    ]
    metrics = compute_refusal(outcomes)
    assert metrics.correct_refusal_rate == pytest.approx(0.5)
    assert metrics.false_refusal_rate == pytest.approx(0.5)
    assert metrics.missed_refusals == ["b"]
    assert metrics.false_refusals == ["d"]


def test_refusal_overall_accuracy_combines_both_sides() -> None:
    outcomes = [
        RefusalOutcome(_case("a", True), refused=True, top_score=None),
        RefusalOutcome(_case("b", False), refused=False, top_score=0.9),
    ]
    assert compute_refusal(outcomes).overall_accuracy == pytest.approx(1.0)


def test_refusal_dataset_has_both_classes() -> None:
    """A dataset of only-refusals would make the false-refusal rate vacuous."""
    cases = load_cases()
    assert cases, "out_of_scope.jsonl should ship with the repo"
    assert any(c.should_refuse for c in cases)
    assert any(not c.should_refuse for c in cases)


# --- groundedness -------------------------------------------------------


def test_layer1_counts_each_failure_mode() -> None:
    results = [
        Layer1Result(1, True, True, True),
        Layer1Result(2, False, True, True, ["circular span does not resolve"]),
        Layer1Result(3, True, False, True, ["clause span does not resolve"]),
    ]
    metrics = compute_layer1(results)
    assert metrics.n_findings == 3
    assert metrics.n_grounded == 1
    assert metrics.unresolved_circular_spans == 1
    assert metrics.unresolved_clause_spans == 1
    assert metrics.failing_ids == [2, 3]


def test_kappa_is_zero_for_a_judge_that_always_agrees_by_chance() -> None:
    """A judge that says 'supported' every time earns no credit."""
    labels = [JudgeLabel(i, True, True) for i in range(9)] + [JudgeLabel(9, True, False)]
    metrics = calibration_agreement(labels)
    assert metrics.raw_agreement == pytest.approx(0.9)
    # High raw agreement, but no better than chance given the marginals.
    assert metrics.cohens_kappa == pytest.approx(0.0, abs=1e-9)
    assert metrics.interpretation in {"slight", "worse than chance"}


def test_kappa_rewards_genuine_agreement() -> None:
    labels = [JudgeLabel(i, True, True) for i in range(5)] + [
        JudgeLabel(i, False, False) for i in range(5, 10)
    ]
    metrics = calibration_agreement(labels)
    assert metrics.cohens_kappa == pytest.approx(1.0)
    assert metrics.interpretation == "almost perfect"


def test_calibration_ignores_unlabelled_rows() -> None:
    labels = [JudgeLabel(1, True, None), JudgeLabel(2, True, True)]
    assert calibration_agreement(labels).n_compared == 1


def test_calibration_with_no_human_labels_is_empty_not_a_crash() -> None:
    assert calibration_agreement([JudgeLabel(1, True, None)]).n_compared == 0


# --- performance --------------------------------------------------------


def test_percentile_interpolates() -> None:
    assert percentile([10, 20], 0.5) == pytest.approx(15.0)
    assert percentile([10], 0.95) == 10.0
    assert percentile([], 0.5) == 0.0


def test_node_breakdown_orders_by_total_time() -> None:
    steps = [
        StepSample("judge_impact", 1000, 500, 0.02),
        StepSample("judge_impact", 3000, 700, 0.03),
        StepSample("plan_assessment", 50, 0, 0.0),
    ]
    breakdown = node_breakdown(steps)
    assert breakdown[0].node == "judge_impact"
    assert breakdown[0].calls == 2
    assert breakdown[0].total_tokens == 1200
    assert breakdown[0].mean_cost_per_call == pytest.approx(0.025)
    assert breakdown[-1].node == "plan_assessment"
