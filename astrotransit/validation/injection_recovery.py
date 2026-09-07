"""Sentetik transit injection-recovery ve completeness ölçümleri."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

import numpy as np


@dataclass(frozen=True)
class InjectionScenario:
    """Tek bir sentetik transit enjeksiyonu."""

    period_days: float
    depth: float
    duration_days: float
    t0: float
    label: str = "default"

    def validate(self) -> None:
        if self.period_days <= 0 or self.duration_days <= 0:
            raise ValueError("Injection period ve duration pozitif olmalıdır.")
        if not 0 < self.depth < 1:
            raise ValueError("Injection depth 0 ile 1 arasında olmalıdır.")


@dataclass(frozen=True)
class RecoveryTrial:
    scenario: InjectionScenario
    detected: bool
    detected_period_days: Optional[float] = None
    period_error_fraction: Optional[float] = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": {
                "period_days": self.scenario.period_days,
                "depth": self.scenario.depth,
                "duration_days": self.scenario.duration_days,
                "t0": self.scenario.t0,
                "label": self.scenario.label,
            },
            "detected": self.detected,
            "detected_period_days": self.detected_period_days,
            "period_error_fraction": self.period_error_fraction,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class InjectionRecoveryReport:
    """Injection-recovery completeness özeti."""

    trials: tuple[RecoveryTrial, ...]
    completeness: float
    completeness_by_label: dict[str, float] = field(default_factory=dict)
    n_trials: int = 0
    n_recovered: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_trials": self.n_trials,
            "n_recovered": self.n_recovered,
            "completeness": self.completeness,
            "completeness_by_label": self.completeness_by_label,
            "trials": [trial.to_dict() for trial in self.trials],
        }


def inject_box_transit(
    time: np.ndarray,
    flux: np.ndarray,
    scenario: InjectionScenario,
) -> np.ndarray:
    """Light curve'e periyodik kutu transit ekler."""

    scenario.validate()
    time_array = np.asarray(time, dtype=float)
    flux_array = np.asarray(flux, dtype=float).copy()
    if time_array.shape != flux_array.shape:
        raise ValueError("time ve flux aynı şekle sahip olmalıdır.")
    phase = np.mod(time_array - scenario.t0 + 0.5 * scenario.period_days, scenario.period_days)
    phase = phase - 0.5 * scenario.period_days
    in_transit = np.abs(phase) <= 0.5 * scenario.duration_days
    flux_array[in_transit] *= 1.0 - scenario.depth
    return flux_array


def run_injection_recovery(
    time: np.ndarray,
    flux: np.ndarray,
    scenarios: Iterable[InjectionScenario],
    detector: Callable[[np.ndarray, np.ndarray], Any],
    *,
    period_tolerance: float = 0.02,
) -> InjectionRecoveryReport:
    """Detektör callable'ı ile sentetik sinyal completeness'ı ölçer.

    ``detector`` iki dizi alır ve period bilgisini şu biçimlerden biriyle
    döndürebilir: pozitif sayı, ``{"period": ...}``, ``{"period_days": ...}``
    veya ``result.best.period``/``result.period`` niteliği taşıyan bir nesne.
    """

    if period_tolerance <= 0:
        raise ValueError("period_tolerance pozitif olmalıdır.")
    trials: list[RecoveryTrial] = []
    for scenario in scenarios:
        scenario.validate()
        injected = inject_box_transit(time, flux, scenario)
        try:
            raw_result = detector(np.asarray(time, dtype=float), injected)
            detected_period = _extract_period(raw_result)
        except Exception as exc:
            trials.append(RecoveryTrial(scenario, False, reason=f"detector_error: {exc}"))
            continue
        if detected_period is None or detected_period <= 0:
            trials.append(RecoveryTrial(scenario, False, reason="no_period"))
            continue
        error_fraction = abs(detected_period - scenario.period_days) / scenario.period_days
        recovered = error_fraction <= period_tolerance
        trials.append(
            RecoveryTrial(
                scenario,
                recovered,
                detected_period_days=float(detected_period),
                period_error_fraction=float(error_fraction),
                reason="period_match" if recovered else "period_mismatch",
            )
        )

    by_label: dict[str, list[bool]] = {}
    for trial in trials:
        by_label.setdefault(trial.scenario.label, []).append(trial.detected)
    completeness_by_label = {
        label: float(np.mean(values)) for label, values in by_label.items() if values
    }
    recovered = sum(trial.detected for trial in trials)
    return InjectionRecoveryReport(
        trials=tuple(trials),
        completeness=float(recovered / len(trials)) if trials else 0.0,
        completeness_by_label=completeness_by_label,
        n_trials=len(trials),
        n_recovered=recovered,
    )


def _extract_period(result: Any) -> Optional[float]:
    if result is None or result is False:
        return None
    if isinstance(result, (int, float, np.number)):
        value = float(result)
        return value if np.isfinite(value) else None
    if isinstance(result, dict):
        if result.get("has_candidate") is False or result.get("detected") is False:
            return None
        for key in ("period_days", "period", "best_period"):
            if key in result:
                return _extract_period(result[key])
    if getattr(result, "detected", True) is False:
        return None
    for attr in ("period_days", "period"):
        value = getattr(result, attr, None)
        if value is not None:
            if hasattr(value, "value"):
                value = value.value
            return _extract_period(value)
    best = getattr(result, "best", None)
    if best is not None:
        return _extract_period(best)
    return None


__all__ = [
    "InjectionRecoveryReport",
    "InjectionScenario",
    "RecoveryTrial",
    "inject_box_transit",
    "run_injection_recovery",
]
