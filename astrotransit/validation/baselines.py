"""Independent baseline comparison contracts.

Baselines are injected as callables so TLS-only/BLS-only implementations can
be compared without coupling validation code to a detector implementation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping


@dataclass(frozen=True)
class BaselineMeasurement:
    name: str
    n_cases: int
    detected: int
    true_positives: int | None = None
    false_positives: int | None = None
    runtime_seconds: float | None = None

    @property
    def recall(self) -> float | None:
        return self.true_positives / self.n_cases if self.true_positives is not None and self.n_cases else None

    @property
    def false_positive_rate(self) -> float | None:
        return self.false_positives / self.n_cases if self.false_positives is not None and self.n_cases else None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "n_cases": self.n_cases, "detected": self.detected,
                "true_positives": self.true_positives, "false_positives": self.false_positives,
                "recall": self.recall, "false_positive_rate": self.false_positive_rate,
                "runtime_seconds": self.runtime_seconds}


@dataclass(frozen=True)
class BaselineComparison:
    measurements: tuple[BaselineMeasurement, ...]
    reference: str

    def delta(self, metric: str, baseline: str, other: str) -> float | None:
        values = {item.name: getattr(item, metric, None) for item in self.measurements}
        left, right = values.get(baseline), values.get(other)
        return None if left is None or right is None else float(right - left)

    def to_dict(self) -> dict[str, Any]:
        return {"reference": self.reference, "measurements": [item.to_dict() for item in self.measurements]}


def compare_baselines(
    cases: Iterable[Mapping[str, Any]],
    detectors: Mapping[str, Callable[[Mapping[str, Any]], Any]],
    *,
    reference: str = "astrotransit",
) -> BaselineComparison:
    """Evaluate independent detector callables on the exact same cases."""
    rows = list(cases)
    measurements = []
    for name, detector in detectors.items():
        detected = tp = fp = 0
        for case in rows:
            result = bool(detector(case))
            label = case.get("label")
            detected += result
            if label == "planet":
                tp += int(result)
            elif label in {"false_positive", "quiet_star"}:
                fp += int(result)
        negative_count = sum(case.get("label") in {"false_positive", "quiet_star"} for case in rows)
        measurements.append(BaselineMeasurement(name, len(rows), detected, tp, fp if negative_count else None))
    return BaselineComparison(tuple(measurements), reference)


__all__ = ["BaselineComparison", "BaselineMeasurement", "compare_baselines"]
