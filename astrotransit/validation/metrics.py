"""Parameter recovery and uncertainty coverage metrics.

These functions deliberately return ``None`` for empty measurements. Missing
science is not silently converted into a perfect or failed score.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np


@dataclass(frozen=True)
class RecoveryMetric:
    n: int
    bias: Optional[float]
    scatter: Optional[float]
    rmse: Optional[float]
    coverage: Optional[float] = None

    def to_dict(self) -> dict[str, Optional[float] | int]:
        return {"n": self.n, "bias": self.bias, "scatter": self.scatter,
                "rmse": self.rmse, "coverage": self.coverage}


def parameter_recovery(
    truth: Iterable[float], recovered: Iterable[float],
    *, intervals: Optional[Iterable[tuple[float, float]]] = None,
) -> RecoveryMetric:
    """Calculate bias, population scatter, RMSE and optional interval coverage."""
    expected = np.asarray(list(truth), dtype=float)
    measured = np.asarray(list(recovered), dtype=float)
    if expected.shape != measured.shape:
        raise ValueError("truth ve recovered aynı uzunlukta olmalıdır.")
    valid = np.isfinite(expected) & np.isfinite(measured)
    expected, measured = expected[valid], measured[valid]
    if not len(expected):
        return RecoveryMetric(0, None, None, None, None)
    errors = measured - expected
    interval_values = None
    if intervals is not None:
        bounds = list(intervals)
        if len(bounds) != len(expected):
            raise ValueError("intervals truth/recovered ile aynı uzunlukta olmalıdır.")
        interval_values = [lo <= value <= hi for value, (lo, hi) in zip(measured, [item for item, ok in zip(bounds, valid) if ok])]
    return RecoveryMetric(
        n=int(len(errors)),
        bias=float(np.mean(errors)),
        scatter=float(np.std(errors)),
        rmse=float(np.sqrt(np.mean(errors ** 2))),
        coverage=float(np.mean(interval_values)) if interval_values is not None else None,
    )


def interval_coverage(
    truth: Iterable[float], intervals: Iterable[tuple[float, float]],
) -> Optional[float]:
    """Fraction of finite truths inside finite credible intervals."""
    values = list(truth)
    bounds = list(intervals)
    if len(values) != len(bounds):
        raise ValueError("truth ve intervals aynı uzunlukta olmalıdır.")
    valid = [(float(value), float(lo), float(hi)) for value, (lo, hi) in zip(values, bounds)
             if np.isfinite(value) and np.isfinite(lo) and np.isfinite(hi)]
    return float(np.mean([lo <= value <= hi for value, lo, hi in valid])) if valid else None


__all__ = ["RecoveryMetric", "interval_coverage", "parameter_recovery"]
