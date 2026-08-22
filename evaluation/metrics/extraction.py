"""Obligation extraction scoring: precision, recall, F1.

MATCH RULE (as specified): a predicted obligation matches a labelled one when
their character spans **overlap** and their **actors match**.

Overlap rather than exact equality, because two annotators — or a model and an
annotator — routinely disagree about whether the trailing clause belongs to
the obligation, while agreeing completely about which requirement is meant.
Requiring exact spans would score that disagreement as both a false positive
and a false negative, which tells you nothing useful.

Actor matching is what stops overlap alone from being too generous: a sentence
imposing duties on two different parties contains two obligations, and a
prediction that merges them should not score as a match for either.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

DATASET = Path(__file__).resolve().parents[1] / "datasets" / "obligations_labeled.jsonl"

# Actors are compared after normalisation: "Stock brokers" and "stock broker"
# are the same party, and a labelling that differs only in plurality or article
# should not be scored as a miss.
_ARTICLES = re.compile(r"^(the|a|an|every|all|any)\s+", re.I)


@dataclass
class LabelledObligation:
    circular_number: str
    text: str
    actor: str
    char_start: int
    char_end: int


@dataclass
class PredictedObligation:
    circular_number: str
    text: str
    actor: str | None
    char_start: int
    char_end: int


@dataclass
class ExtractionMetrics:
    true_positives: int
    false_positives: int
    false_negatives: int
    n_labelled: int
    n_predicted: int
    n_circulars: int = 0
    unmatched_labels: list[str] = field(default_factory=list)

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


def normalise_actor(actor: str | None) -> str:
    """Lowercase, drop the leading article, and singularise the head noun.

    Singularisation handles the ``-ies`` form explicitly: "intermediaries" is
    the most common actor in this domain, and a rule that only strips a
    trailing "s" would leave it as "intermediarie" and never match
    "intermediary".
    """
    if not actor:
        return ""
    text = _ARTICLES.sub("", actor.strip().lower())
    if text.endswith("ies") and len(text) > 4:
        return text[:-3] + "y"
    if text.endswith("s") and not text.endswith("ss"):
        return text[:-1]
    return text


def spans_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def actors_match(predicted: str | None, labelled: str) -> bool:
    """One actor string contains the other, after normalisation.

    Containment rather than equality because a model may name the party more
    fully than the label ("registered stock brokers" vs "stock brokers").
    """
    left, right = normalise_actor(predicted), normalise_actor(labelled)
    if not left or not right:
        return False
    return left in right or right in left


def load_labels(path: Path = DATASET) -> list[LabelledObligation]:
    if not path.is_file():
        return []
    out: list[LabelledObligation] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                out.append(LabelledObligation(**json.loads(line)))
    return out


def compute(
    predicted: list[PredictedObligation], labelled: list[LabelledObligation]
) -> ExtractionMetrics:
    """Greedy one-to-one matching within each circular.

    Each label may be claimed by at most one prediction, so a model that emits
    five near-duplicates of one obligation scores one true positive and four
    false positives rather than five true positives.
    """
    by_circular: dict[str, list[LabelledObligation]] = {}
    for label in labelled:
        by_circular.setdefault(label.circular_number, []).append(label)

    claimed: set[int] = set()
    true_positives = 0
    false_positives = 0

    for prediction in predicted:
        candidates = by_circular.get(prediction.circular_number, [])
        hit = None
        for index, label in enumerate(candidates):
            key = id(label)
            if key in claimed:
                continue
            if spans_overlap(
                prediction.char_start, prediction.char_end, label.char_start, label.char_end
            ) and actors_match(prediction.actor, label.actor):
                hit = (key, index)
                break
        if hit is None:
            false_positives += 1
        else:
            claimed.add(hit[0])
            true_positives += 1

    unmatched = [
        f"{label.circular_number}:{label.char_start}"
        for label in labelled
        if id(label) not in claimed
    ]

    return ExtractionMetrics(
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=len(unmatched),
        n_labelled=len(labelled),
        n_predicted=len(predicted),
        n_circulars=len(by_circular),
        unmatched_labels=unmatched[:20],
    )
