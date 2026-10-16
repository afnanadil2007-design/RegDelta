"""Groundedness scoring, in two layers.

**Layer 1 — programmatic.** Every finding's spans must resolve against the
source text, and the span text must appear in what the retriever actually put
in front of the model. This layer is deterministic, free, and runs over stored
findings; it is also enforced live in the graph, so a violation here means
something bypassed `verify_grounding`.

**Layer 2 — support.** Layer 1 proves a quote exists; it cannot prove the
*rationale* follows from it. A finding can quote faithfully and still reason
badly. Whether it does is judged by a person reading the evidence
(`evaluation/support_review.py`). No model judge is implemented; if one is
added, its labels are compared with those human labels here, because an
unvalidated judge is an opinion, not a measurement.

`calibration_agreement` makes that comparison: Cohen's kappa alongside raw
agreement, because raw agreement is misleading when one label dominates — a
judge that says "supported" every time scores ~90% raw agreement on a corpus
that is 90% supported, while contributing nothing. Empty comparisons and the
degenerate case where kappa is 0/0 are reported as undefined, never as a
number.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Layer1Result:
    """One finding's programmatic grounding check."""

    finding_id: int
    circular_span_resolves: bool
    clause_span_resolves: bool
    span_in_retrieved_context: bool
    problems: list[str] = field(default_factory=list)

    @property
    def grounded(self) -> bool:
        return not self.problems


@dataclass
class Layer1Metrics:
    n_findings: int
    n_grounded: int
    unresolved_circular_spans: int
    unresolved_clause_spans: int
    spans_outside_context: int
    failing_ids: list[int] = field(default_factory=list)

    @property
    def grounded_rate(self) -> float | None:
        """None when there are no findings: unmeasured, not 0% grounded."""
        return self.n_grounded / self.n_findings if self.n_findings else None


def compute_layer1(results: list[Layer1Result]) -> Layer1Metrics:
    return Layer1Metrics(
        n_findings=len(results),
        n_grounded=sum(1 for r in results if r.grounded),
        unresolved_circular_spans=sum(1 for r in results if not r.circular_span_resolves),
        unresolved_clause_spans=sum(1 for r in results if not r.clause_span_resolves),
        spans_outside_context=sum(1 for r in results if not r.span_in_retrieved_context),
        failing_ids=[r.finding_id for r in results if not r.grounded][:20],
    )


@dataclass
class JudgeLabel:
    """One judged rationale, against a human label where one exists."""

    finding_id: int
    judge_supported: bool
    human_supported: bool | None = None


@dataclass
class CalibrationMetrics:
    """Agreement between judge and human labels, over the pairs that have both.

    Every rate is None when nothing was compared. ``cohens_kappa`` is also None
    when it is 0/0, with the reason in ``kappa_undefined``.
    """

    n_compared: int
    raw_agreement: float | None
    cohens_kappa: float | None
    judge_positive_rate: float | None
    human_positive_rate: float | None
    kappa_undefined: str | None = None

    @property
    def interpretation(self) -> str:
        """Landis & Koch bands, so a bare kappa is never reported alone."""
        k = self.cohens_kappa
        if k is None:
            return f"undefined: {self.kappa_undefined}"
        if k < 0.0:
            return "worse than chance"
        if k < 0.20:
            return "slight"
        if k < 0.40:
            return "fair"
        if k < 0.60:
            return "moderate"
        if k < 0.80:
            return "substantial"
        return "almost perfect"


def calibration_agreement(labels: list[JudgeLabel]) -> CalibrationMetrics:
    """Compare judge labels with human labels.

    Cohen's kappa corrects for the agreement two raters would reach by chance
    given their marginal rates, which is exactly the failure mode a raw
    agreement percentage hides.
    """
    paired = [label for label in labels if label.human_supported is not None]
    n = len(paired)
    if n == 0:
        return CalibrationMetrics(0, None, None, None, None, "no pairs to compare")

    agree = sum(1 for label in paired if label.judge_supported == label.human_supported)
    p_observed = agree / n

    judge_pos = sum(1 for label in paired if label.judge_supported) / n
    human_pos = sum(1 for label in paired if label.human_supported) / n
    # Probability the two raters agree purely by chance.
    p_chance = judge_pos * human_pos + (1 - judge_pos) * (1 - human_pos)

    if p_chance >= 1.0:
        # Both raters gave every pair the same single label: chance agreement
        # is 1 and kappa is 0/0. Calling that 1.0 would credit a judge that
        # never varies on a set that never varies.
        return CalibrationMetrics(
            n,
            p_observed,
            None,
            judge_pos,
            human_pos,
            "both raters gave every pair the same label, so chance agreement is 1",
        )

    return CalibrationMetrics(
        n_compared=n,
        raw_agreement=p_observed,
        cohens_kappa=(p_observed - p_chance) / (1 - p_chance),
        judge_positive_rate=judge_pos,
        human_positive_rate=human_pos,
    )
