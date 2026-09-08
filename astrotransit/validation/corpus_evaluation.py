"""Evaluation of labelled validation corpora with explicit holdout semantics."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from astrotransit.validation.corpus import CorpusCase
from astrotransit.validation.splits import assign_split


@dataclass(frozen=True)
class CorpusEvaluation:
    split: str
    n_cases: int
    n_evaluated: int
    true_positives: int | None
    false_positives: int | None
    true_negatives: int | None
    false_negatives: int | None
    errors: int

    @property
    def precision(self) -> float | None:
        denominator = (self.true_positives or 0) + (self.false_positives or 0)
        return self.true_positives / denominator if self.true_positives is not None and denominator else None

    @property
    def recall(self) -> float | None:
        denominator = (self.true_positives or 0) + (self.false_negatives or 0)
        return self.true_positives / denominator if self.true_positives is not None and denominator else None

    def to_dict(self) -> dict[str, Any]:
        return {"split": self.split, "n_cases": self.n_cases, "n_evaluated": self.n_evaluated,
                "true_positives": self.true_positives, "false_positives": self.false_positives,
                "true_negatives": self.true_negatives, "false_negatives": self.false_negatives,
                "errors": self.errors, "precision": self.precision, "recall": self.recall}


def evaluate_corpus(
    cases: Iterable[CorpusCase],
    detector: Callable[[CorpusCase], bool],
    *,
    split: str = "blind_test",
    seed: int = 0,
) -> CorpusEvaluation:
    """Evaluate only one deterministic split; detector exceptions remain errors."""
    if split not in {"development", "validation", "blind_test", "all"}:
        raise ValueError("split development, validation, blind_test veya all olmalıdır")
    selected = [case for case in cases if split == "all" or assign_split(case.target_id, seed=seed) == split]
    tp = fp = tn = fn = errors = evaluated = 0
    for case in selected:
        try:
            detected = bool(detector(case))
            evaluated += 1
        except Exception:
            errors += 1
            continue
        positive = case.label == "planet"
        if positive and detected:
            tp += 1
        elif positive:
            fn += 1
        elif detected:
            fp += 1
        else:
            tn += 1
    return CorpusEvaluation(split, len(selected), evaluated, tp, fp, tn, fn, errors)


__all__ = ["CorpusEvaluation", "evaluate_corpus"]
