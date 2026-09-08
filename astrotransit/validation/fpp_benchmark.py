"""FPP proxy kalibrasyonu için etiketli benchmark yardımcıları."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

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
    brier_score: Optional[float]
    false_positive_recall: Optional[float]
    planet_precision: Optional[float]
    threshold: float
    confusion_matrix: dict[str, int]
    expected_calibration_error: Optional[float] = None
    calibration_curve: tuple[dict[str, Any], ...] = ()
    roc_auc: Optional[float] = None
    pr_auc: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_cases": self.n_cases,
            "brier_score": self.brier_score,
            "false_positive_recall": self.false_positive_recall,
            "planet_precision": self.planet_precision,
            "threshold": self.threshold,
            "confusion_matrix": self.confusion_matrix,
            "expected_calibration_error": self.expected_calibration_error,
            "calibration_curve": list(self.calibration_curve),
            "roc_auc": self.roc_auc,
            "pr_auc": self.pr_auc,
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
        return FPPBenchmarkReport(0, None, None, None, threshold, {})
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
    calibration_curve = _calibration_curve(probabilities, labels)
    ece = float(sum(item["weight"] * abs(item["mean_predicted"] - item["observed_rate"]) for item in calibration_curve)) if calibration_curve else None
    return FPPBenchmarkReport(
        n_cases=len(materialized),
        brier_score=float(np.mean((probabilities - labels) ** 2)),
        false_positive_recall=float(tp / (tp + fn)) if tp + fn else None,
        planet_precision=float(tn / planet_predictions) if planet_predictions else None,
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
        expected_calibration_error=ece,
        calibration_curve=tuple(calibration_curve),
        roc_auc=_rank_auc(probabilities, labels),
        pr_auc=_pr_auc(probabilities, labels),
    )


def _calibration_curve(probabilities: np.ndarray, labels: np.ndarray, bins: int = 10) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lower, upper in zip(np.linspace(0, 1, bins, endpoint=False), np.linspace(0, 1, bins + 1)[1:]):
        mask = (probabilities >= lower) & (probabilities <= upper if upper == 1 else probabilities < upper)
        if np.any(mask):
            rows.append({"lower": float(lower), "upper": float(upper), "n": int(mask.sum()),
                         "weight": float(mask.mean()), "mean_predicted": float(probabilities[mask].mean()),
                         "observed_rate": float(labels[mask].mean())})
    return rows


def _rank_auc(scores: np.ndarray, labels: np.ndarray) -> Optional[float]:
    positives = scores[labels == 1]
    negatives = scores[labels == 0]
    if not len(positives) or not len(negatives):
        return None
    return float((sum(float(p > n) + 0.5 * float(p == n) for p in positives for n in negatives)) / (len(positives) * len(negatives)))


def _pr_auc(scores: np.ndarray, labels: np.ndarray) -> Optional[float]:
    if not np.any(labels == 1):
        return None
    order = np.argsort(-scores, kind="stable")
    sorted_labels = labels[order]
    tp = np.cumsum(sorted_labels == 1)
    fp = np.cumsum(sorted_labels == 0)
    precision = tp / np.maximum(tp + fp, 1)
    recall = tp / tp[-1]
    return float(np.sum(np.diff(np.r_[0.0, recall]) * precision))


__all__ = ["FPPBenchmarkCase", "FPPBenchmarkReport", "evaluate_fpp_benchmark"]
