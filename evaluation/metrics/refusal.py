"""Refusal accuracy: does the pipeline decline when it should, and only then?

Two rates, reported separately, because they trade off against each other and
a single "accuracy" number hides which way the threshold is wrong:

* **correct-refusal rate** — of the queries that *should* be refused, how many
  were. Low means the system answers questions it has no basis for.
* **false-refusal rate** — of the queries that should be *answered*, how many
  were refused anyway. High means the threshold is strangling recall.

A refusal here is the pipeline's explicit ``below_threshold`` signal (or an
empty result set), not a model saying "I don't know" in prose.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DATASET = Path(__file__).resolve().parents[1] / "datasets" / "out_of_scope.jsonl"


@dataclass
class RefusalCase:
    id: str
    query: str
    should_refuse: bool
    reason: str = ""


@dataclass
class RefusalOutcome:
    case: RefusalCase
    refused: bool
    top_score: float | None

    @property
    def correct(self) -> bool:
        return self.refused == self.case.should_refuse


@dataclass
class RefusalMetrics:
    n_should_refuse: int
    n_should_answer: int
    correct_refusal_rate: float
    false_refusal_rate: float
    # Cases the system got wrong, for inspection rather than a bare number.
    missed_refusals: list[str]
    false_refusals: list[str]

    @property
    def overall_accuracy(self) -> float:
        total = self.n_should_refuse + self.n_should_answer
        if not total:
            return 0.0
        correct = self.correct_refusal_rate * self.n_should_refuse + (
            1 - self.false_refusal_rate
        ) * self.n_should_answer
        return correct / total


def load_cases(path: Path = DATASET) -> list[RefusalCase]:
    if not path.is_file():
        return []
    cases: list[RefusalCase] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                cases.append(RefusalCase(**json.loads(line)))
    return cases


def compute(outcomes: list[RefusalOutcome]) -> RefusalMetrics:
    should_refuse = [o for o in outcomes if o.case.should_refuse]
    should_answer = [o for o in outcomes if not o.case.should_refuse]

    correct_refusals = sum(1 for o in should_refuse if o.refused)
    false_refusals = sum(1 for o in should_answer if o.refused)

    return RefusalMetrics(
        n_should_refuse=len(should_refuse),
        n_should_answer=len(should_answer),
        correct_refusal_rate=(
            correct_refusals / len(should_refuse) if should_refuse else 0.0
        ),
        false_refusal_rate=(false_refusals / len(should_answer) if should_answer else 0.0),
        missed_refusals=[o.case.id for o in should_refuse if not o.refused],
        false_refusals=[o.case.id for o in should_answer if o.refused],
    )
