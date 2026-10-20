"""Cadence-impact robustness contracts.

Matches the ``detrending_cadence_impact_robustness`` acceptance gate in
``validation_runs/final_acceptance_v1/program.json``. Detectors and
perturbations are injected as callables so this validation stays decoupled
from the TESS pipeline implementation.

Epistemik not: buradan çıkan "recall düşüşü" gerçek bir uzay sınırlaması
değildir; belirtilen gürültü/kadans pertürbasyonlarına karşı duyarlılıktır.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

Detector = Callable[[Mapping[str, Any]], bool]
Perturbation = Callable[[Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True)
class RobustnessMeasurement:
    name: str
    n_cases: int
    detected: int
    recall: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "n_cases": self.n_cases, "detected": self.detected,
                "recall": self.recall}


@dataclass(frozen=True)
class RobustnessCampaign:
    baseline: RobustnessMeasurement
    measurements: tuple[RobustnessMeasurement, ...]

    @property
    def max_recall_drop(self) -> float | None:
        """Pertürbasyonlarda en büyük recall düşüşü (pozitif = kötüleşme)."""

        baseline_recall = self.baseline.recall
        if baseline_recall is None:
            return None
        drops = [
            baseline_recall - item.recall
            for item in self.measurements
            if item.recall is not None
        ]
        return max(drops) if drops else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline": self.baseline.to_dict(),
            "measurements": [item.to_dict() for item in self.measurements],
            "max_recall_drop": self.max_recall_drop,
        }


def measure_cadence_robustness(
    cases: Iterable[Mapping[str, Any]],
    detector: Detector,
    perturbations: Mapping[str, Perturbation],
) -> RobustnessCampaign:
    """Aynı vakalar küresinde, pertürbasyonların algılama etkisini ölçer.

    Parameters
    ----------
    cases:
        En az ``label`` alanı içeren vakalar.
    detector:
        Vaka başına bool döndüren algılayıcı (injektif — sözleşme pipeline'a
        bağlı değildir).
    perturbations:
        isim -> (vaka -> dönüştürülmüş vaka) callable'ları; örn.
        "cadence_50pct", "detrend_window_x2".
    """

    rows = list(cases)
    if not rows:
        raise ValueError("cases boş olamaz.")

    baseline_detected = sum(bool(detector(case)) for case in rows)
    baseline = RobustnessMeasurement(
        name="unperturbed",
        n_cases=len(rows),
        detected=baseline_detected,
        recall=baseline_detected / len(rows),
    )

    measurements = []
    for name, perturb in perturbations.items():
        detected = sum(bool(detector(perturb(case))) for case in rows)
        measurements.append(
            RobustnessMeasurement(
                name=name,
                n_cases=len(rows),
                detected=detected,
                recall=detected / len(rows),
            )
        )

    return RobustnessCampaign(baseline=baseline, measurements=tuple(measurements))


@dataclass(frozen=True)
class RobustnessGateResult:
    campaign: RobustnessCampaign
    min_cases: int
    declared_max_recall_drop: float
    status: str              # "measured" | "measured_fail" | "pending_run"
    blocking_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign": self.campaign.to_dict(),
            "min_cases": self.min_cases,
            "declared_max_recall_drop": self.declared_max_recall_drop,
            "status": self.status,
            "blocking_reasons": list(self.blocking_reasons),
        }


def evaluate_cadence_robustness_gate(
    campaign: RobustnessCampaign | None,
    *,
    min_cases: int = 100,
    declared_max_recall_drop: float = 0.05,
) -> RobustnessGateResult:
    """Önceden ilan edilmiş eşiklerle kapı sonucu üretir.

    - Kampanya yok / n_cases < min_cases → ``pending_run``
    - ``max_recall_drop <= declared_max_recall_drop`` → ``measured``
      (denetim sözleşmesi CLOSED = {"measured","pass"} ile hizalı)
    - değil → ``measured_fail``
    """

    if campaign is None or campaign.baseline.n_cases < min_cases:
        return RobustnessGateResult(
            campaign=RobustnessCampaign(
                baseline=RobustnessMeasurement("unperturbed", 0, 0, None),
                measurements=(),
            ),
            min_cases=min_cases,
            declared_max_recall_drop=declared_max_recall_drop,
            status="pending_run",
            blocking_reasons=("campaign missing or n_cases below floor",),
        )
    drop = campaign.max_recall_drop
    reasons: tuple[str, ...]
    if drop is None:
        status, reasons = "measured_fail", ("recall could not be measured",)
    elif drop <= declared_max_recall_drop:
        status, reasons = "measured", ()
    else:
        status = "measured_fail"
        reasons = (
            f"max_recall_drop {drop:.4f} exceeds declared floor {declared_max_recall_drop:.4f}",
        )
    return RobustnessGateResult(
        campaign=campaign,
        min_cases=min_cases,
        declared_max_recall_drop=declared_max_recall_drop,
        status=status,
        blocking_reasons=reasons,
    )


__all__ = [
    "RobustnessCampaign",
    "RobustnessGateResult",
    "RobustnessMeasurement",
    "evaluate_cadence_robustness_gate",
    "measure_cadence_robustness",
]
