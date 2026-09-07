"""FPP proxy kalibrasyonu için etiketli benchmark yardımcıları."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np


@dataclass(frozen=True)
class FPPBenchmarkCase:
    target_id: str
    is_false_positive: bool
    fpp: float

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.fpp) <= 1.0:
            raise ValueError("FPP 0 ile 1 arasında olmalıdır.")


@dataclass(frozen=True)
class FPPBenchmarkReport:
    n_cases: int
    brier_score: float
    false_positive_recall: float
    planet_precision: float
    threshold: float
    confusion_matrix: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_cases": self.n_cases,
            "brier_score": self.brier_score,
            "false_positive_recall": self.false_positive_recall,
            "planet_precision": self.planet_precision,
            "threshold": self.threshold,
            "confusion_matrix": self.confusion_matrix,
        }


def evaluate_fpp_benchmark(
    cases: Iterable[FPPBenchmarkCase],
    *,
    threshold: float = 0.5,
) -> FPPBenchmarkReport:
    """Etiketli FPP değerleri için kalibrasyon/ayırt etme metrikleri üretir.

    ``fpp >= threshold`` false-positive kararıdır. Bu metrikler FPP'nin
    formal Bayesian doğrulaması değildir; proxy'nin bilinen örneklemde nasıl
    davrandığını görünür kılar.
    """

    if not 0.0 < threshold < 1.0:
        raise ValueError("threshold 0 ile 1 arasında olmalıdır.")
    materialized = list(cases)
    if not materialized:
        return FPPBenchmarkReport(0, 0.0, 0.0, 0.0, threshold, {})
    probabilities = np.asarray([case.fpp for case in materialized], dtype=float)
    labels = np.asarray([case.is_false_positive for case in materialized], dtype=float)
    predicted = probabilities >= threshold
    actual_fp = labels == 1.0
    actual_planet = ~actual_fp
    tp = int(np.sum(predicted & actual_fp))
    fp = int(np.sum(predicted & actual_planet))
    tn = int(np.sum(~predicted & actual_planet))
    fn = int(np.sum(~predicted & actual_fp))
    planet_predictions = int(np.sum(~predicted))
    return FPPBenchmarkReport(
        n_cases=len(materialized),
        brier_score=float(np.mean((probabilities - labels) ** 2)),
        false_positive_recall=float(tp / (tp + fn)) if tp + fn else 0.0,
        planet_precision=float(tn / planet_predictions) if planet_predictions else 0.0,
        threshold=threshold,
        confusion_matrix={
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "true_positive_fp": tp,
            "false_positive_planet": fp,
            "true_negative_planet": tn,
            "false_negative_fp": fn,
        },
    )


__all__ = ["FPPBenchmarkCase", "FPPBenchmarkReport", "evaluate_fpp_benchmark"]
