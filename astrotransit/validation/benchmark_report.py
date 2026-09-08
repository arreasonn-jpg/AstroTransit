"""Ölçülmüş benchmark sonuçlarını standart bir performans raporuna çevirir.

``benchmarks/verified_targets.json`` yalnızca ground-truth bilgisidir. Bu modül
onu pipeline çıktılarıyla birleştirerek hedef bazında ve toplu ölçümler üretir.
Pipeline hiç çalıştırılmamışsa metrikler ``None`` kalır; bilinmeyen bir FPP veya
recovery değeri hiçbir zaman sessizce ``0.0`` ile doldurulmaz.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable, Mapping, Optional


DEFAULT_PERIOD_TOLERANCE = 0.02
DEFAULT_RADIUS_TOLERANCE = 0.20


def normalize_target_id(value: Any) -> str:
    """TIC kimliğini karşılaştırılabilir ``TIC <id>`` biçimine getirir."""

    text = str(value or "").strip()
    if text.upper().startswith("TIC"):
        text = text[3:].strip()
    try:
        return f"TIC {int(float(text))}"
    except (TypeError, ValueError):
        return str(value or "").strip()


@dataclass(frozen=True)
class VerifiedTarget:
    """Bir bilinen gezegen benchmark hedefinin ground-truth kaydı."""

    tic_id: str
    name: str
    expected_period_days: float
    expected_radius_rearth: Optional[float]
    difficulty: str
    sector: Optional[int] = None
    available_sectors: tuple[int, ...] = ()
    reference: str = ""

    @property
    def target_id(self) -> str:
        return normalize_target_id(self.tic_id)

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "VerifiedTarget":
        period = float(row.get("period", row.get("expected_period_days")))
        if not math.isfinite(period) or period <= 0:
            raise ValueError("verified target period pozitif ve sonlu olmalıdır")
        raw_radius = row.get("rp_rearth", row.get("expected_radius_rearth"))
        radius = None if raw_radius in (None, "") else float(raw_radius)
        if radius is not None and (not math.isfinite(radius) or radius <= 0):
            raise ValueError("verified target radius pozitif ve sonlu olmalıdır")
        raw_sector = row.get("sector")
        sector = None if raw_sector in (None, "") else int(raw_sector)
        sectors = tuple(int(item) for item in (row.get("available_sectors") or ()))
        return cls(
            tic_id=str(row.get("tic_id", row.get("source_id", ""))),
            name=str(row.get("name", row.get("target_id", ""))),
            expected_period_days=period,
            expected_radius_rearth=radius,
            difficulty=str(row.get("difficulty", "unknown")).lower(),
            sector=sector,
            available_sectors=sectors,
            reference=str(row.get("reference", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tic_id": self.tic_id,
            "target_id": self.target_id,
            "name": self.name,
            "difficulty": self.difficulty,
            "sector": self.sector,
            "available_sectors": list(self.available_sectors),
            "reference": self.reference,
            "expected_period_days": self.expected_period_days,
            "expected_radius_rearth": self.expected_radius_rearth,
        }


def load_verified_targets(path: str | Path) -> list[VerifiedTarget]:
    """JSON ground-truth dosyasını doğrulayarak yükler."""

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Verified target dosyası bulunamadı: {source}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    rows = payload.get("targets", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("verified target JSON'u liste veya {targets: [...]} olmalıdır")
    return [VerifiedTarget.from_mapping(row) for row in rows]


@dataclass(frozen=True)
class BenchmarkTargetMeasurement:
    """Tek benchmark hedefinin expected/recovered karşılaştırması."""

    target_id: str
    name: str
    difficulty: str
    expected_period_days: float
    recovered_period_days: Optional[float]
    expected_radius_rearth: Optional[float]
    recovered_radius_rearth: Optional[float]
    detected: bool
    period_recovered: bool
    radius_recovered: bool
    correct: bool
    period_error_days: Optional[float]
    period_error_fraction: Optional[float]
    radius_error_rearth: Optional[float]
    radius_error_fraction: Optional[float]
    sector_consistent: Optional[bool]
    n_sectors_evaluated: int
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "name": self.name,
            "difficulty": self.difficulty,
            "expected_period_days": self.expected_period_days,
            "recovered_period_days": self.recovered_period_days,
            "expected_radius_rearth": self.expected_radius_rearth,
            "recovered_radius_rearth": self.recovered_radius_rearth,
            "detected": self.detected,
            "period_recovered": self.period_recovered,
            "radius_recovered": self.radius_recovered,
            "correct": self.correct,
            "period_error_days": self.period_error_days,
            "period_error_fraction": self.period_error_fraction,
            "radius_error_rearth": self.radius_error_rearth,
            "radius_error_fraction": self.radius_error_fraction,
            "sector_consistent": self.sector_consistent,
            "n_sectors_evaluated": self.n_sectors_evaluated,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class BenchmarkPerformanceReport:
    """Bilinen hedef benchmark'ının ölçülebilir performans özeti."""

    pipeline_version: str
    generated_at_utc: str
    period_tolerance_fraction: float
    radius_tolerance_fraction: float
    targets: tuple[BenchmarkTargetMeasurement, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": {
                "report_type": "known_target_benchmark_performance",
                "pipeline_version": self.pipeline_version,
                "generated_at_utc": self.generated_at_utc,
                "period_tolerance_fraction": self.period_tolerance_fraction,
                "radius_tolerance_fraction": self.radius_tolerance_fraction,
            },
            "metrics": self.metrics,
            "targets": [target.to_dict() for target in self.targets],
            "limitations": list(self.limitations),
            "provenance": self.provenance,
        }

    def summary(self) -> str:
        metrics = self.metrics
        return (
            "Benchmark performance: "
            f"targets={metrics.get('n_targets', 0)}, "
            f"detected={metrics.get('detection_recall')}, "
            f"period_error={metrics.get('period_recovery_error_median_fraction')}, "
            f"radius_error={metrics.get('radius_recovery_error_median_fraction')}, "
            f"false_positive_rejection={metrics.get('false_positive_rejection')}"
        )

    def write_json(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return destination

    def write_csv(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        rows = [target.to_dict() for target in self.targets]
        fieldnames = list(BenchmarkTargetMeasurement.__dataclass_fields__)
        with destination.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                row = dict(row)
                row["notes"] = "; ".join(row["notes"])
                writer.writerow(row)
        return destination


def evaluate_benchmark_results(
    verified_targets: Iterable[VerifiedTarget],
    pipeline_results: Iterable[Any],
    *,
    period_tolerance_fraction: float = DEFAULT_PERIOD_TOLERANCE,
    radius_tolerance_fraction: float = DEFAULT_RADIUS_TOLERANCE,
    pipeline_version: Optional[str] = None,
    provenance: Optional[dict[str, Any]] = None,
) -> BenchmarkPerformanceReport:
    """Pipeline sonuçlarını known-target ground truth ile karşılaştırır.

    Aday yokluğu, period/radius ölçümünün yokluğu ve false-positive veri setinin
    yokluğu farklı durumlar olarak raporlanır. Özellikle ``false_positive_rejection``
    negatif etiketli veri yoksa ``None`` olur; bu durum başarısızlık değil,
    *ölçülmedi* anlamına gelir.
    """

    if not 0.0 < period_tolerance_fraction <= 1.0:
        raise ValueError("period_tolerance_fraction 0 ile 1 arasında olmalıdır")
    if not 0.0 < radius_tolerance_fraction <= 1.0:
        raise ValueError("radius_tolerance_fraction 0 ile 1 arasında olmalıdır")

    specs = list(verified_targets)
    result_map = {
        normalize_target_id(_value(result, "target_id", "")): result
        for result in pipeline_results
    }
    measurements: list[BenchmarkTargetMeasurement] = []

    for spec in specs:
        result = result_map.get(spec.target_id)
        observations = _confirmed_observations(result)
        detected = bool(observations) or bool(_value(result, "candidates_confirmed", 0) or 0)
        best = _best_observation(observations, spec.expected_period_days)
        recovered_period = _positive_float(best.get("period")) if best else None
        recovered_radius = _positive_float(best.get("radius")) if best else None

        period_error_days = (
            abs(recovered_period - spec.expected_period_days)
            if recovered_period is not None
            else None
        )
        period_error_fraction = (
            period_error_days / spec.expected_period_days
            if period_error_days is not None
            else None
        )
        period_recovered = (
            period_error_fraction is not None
            and period_error_fraction <= period_tolerance_fraction
        )

        radius_error_rearth = None
        radius_error_fraction = None
        if recovered_radius is not None and spec.expected_radius_rearth is not None:
            radius_error_rearth = abs(recovered_radius - spec.expected_radius_rearth)
            radius_error_fraction = radius_error_rearth / spec.expected_radius_rearth
        radius_recovered = (
            spec.expected_radius_rearth is not None
            and radius_error_fraction is not None
            and radius_error_fraction <= radius_tolerance_fraction
        )

        periods = [
            value for value in (_positive_float(item.get("period")) for item in observations)
            if value is not None
        ]
        sector_consistent = _sector_consistency(periods, period_tolerance_fraction)
        notes: list[str] = []
        if result is None:
            notes.append("no_pipeline_result")
        if detected and not period_recovered:
            notes.append("period_not_recovered")
        if detected and spec.expected_radius_rearth is not None and not radius_recovered:
            notes.append("radius_not_recovered")
        if sector_consistent is None:
            notes.append("sector_consistency_not_evaluated")

        measurements.append(
            BenchmarkTargetMeasurement(
                target_id=spec.target_id,
                name=spec.name,
                difficulty=spec.difficulty,
                expected_period_days=spec.expected_period_days,
                recovered_period_days=recovered_period,
                expected_radius_rearth=spec.expected_radius_rearth,
                recovered_radius_rearth=recovered_radius,
                detected=detected,
                period_recovered=period_recovered,
                radius_recovered=radius_recovered,
                correct=period_recovered and radius_recovered,
                period_error_days=period_error_days,
                period_error_fraction=period_error_fraction,
                radius_error_rearth=radius_error_rearth,
                radius_error_fraction=radius_error_fraction,
                sector_consistent=sector_consistent,
                n_sectors_evaluated=len(observations),
                notes=tuple(notes),
            )
        )

    detected_items = [item for item in measurements if item.detected]
    period_items = [item for item in measurements if item.period_error_fraction is not None]
    radius_items = [item for item in measurements if item.radius_error_fraction is not None]
    consistency_items = [item for item in measurements if item.sector_consistent is not None]
    metrics: dict[str, Any] = {
        "n_targets": len(measurements),
        "n_detected": len(detected_items),
        "detection_recall": _ratio(len(detected_items), len(measurements)),
        "n_correct": sum(item.correct for item in measurements),
        "correct_recovery_rate": _ratio(
            sum(item.correct for item in measurements), len(measurements)
        ),
        "n_period_recovered": sum(item.period_recovered for item in measurements),
        "period_recovery_rate": _ratio(
            sum(item.period_recovered for item in measurements), len(measurements)
        ),
        "period_recovery_error_mean_days": _mean(item.period_error_days for item in period_items),
        "period_recovery_error_median_days": _median(
            item.period_error_days for item in period_items
        ),
        "period_recovery_error_mean_fraction": _mean(
            item.period_error_fraction for item in period_items
        ),
        "period_recovery_error_median_fraction": _median(
            item.period_error_fraction for item in period_items
        ),
        "n_radius_recovered": sum(item.radius_recovered for item in measurements),
        "radius_recovery_rate": _ratio(
            sum(item.radius_recovered for item in measurements), len(measurements)
        ),
        "radius_recovery_error_mean_rearth": _mean(
            item.radius_error_rearth for item in radius_items
        ),
        "radius_recovery_error_median_rearth": _median(
            item.radius_error_rearth for item in radius_items
        ),
        "radius_recovery_error_mean_fraction": _mean(
            item.radius_error_fraction for item in radius_items
        ),
        "radius_recovery_error_median_fraction": _median(
            item.radius_error_fraction for item in radius_items
        ),
        "n_sector_consistency_evaluated": len(consistency_items),
        "sector_consistency_rate": _ratio(
            sum(bool(item.sector_consistent) for item in consistency_items),
            len(consistency_items),
        ),
        "false_positive_rejection": None,
        "false_positive_rejection_status": "not_evaluated_no_labeled_false_positive_set",
        "n_false_positive_targets": 0,
    }

    limitations: list[str] = [
        "Known-target recovery is not injection-recovery completeness.",
        "False-positive rejection is not measured because no labeled FP set was supplied.",
    ]
    if not measurements or not detected_items:
        limitations.append("No successful pipeline target result was available for measurement.")
    if any(item.expected_radius_rearth is not None for item in measurements) and not radius_items:
        limitations.append("Radius recovery is unavailable for all evaluated targets.")

    if pipeline_version is None:
        try:
            from astrotransit.version import __version__

            pipeline_version = __version__
        except ImportError:  # pragma: no cover
            pipeline_version = "unknown"

    return BenchmarkPerformanceReport(
        pipeline_version=pipeline_version,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        period_tolerance_fraction=period_tolerance_fraction,
        radius_tolerance_fraction=radius_tolerance_fraction,
        targets=tuple(measurements),
        metrics=metrics,
        limitations=tuple(limitations),
        provenance=provenance or {},
    )


def _confirmed_observations(result: Any) -> list[dict[str, Any]]:
    if result is None:
        return []
    observations: list[dict[str, Any]] = []
    for sector_result in _value(result, "sector_results", []) or []:
        if not bool(_value(sector_result, "candidate_confirmed", False)):
            continue
        record = _value(sector_result, "record")
        candidate = _value(sector_result, "candidate")
        fit_result = _value(sector_result, "fit_result")
        period = _first_positive(
            _value(record, "period"),
            _value(candidate, "period"),
            _value(fit_result, "period"),
        )
        radius = _first_positive(
            _value(record, "planet_radius_rearth"),
            _value(fit_result, "planet_radius_rearth"),
            _value(_value(fit_result, "derived"), "planet_radius_rearth"),
        )
        observations.append(
            {
                "sector": _value(sector_result, "sector"),
                "period": period,
                "radius": radius,
            }
        )
    return observations


def _best_observation(observations: list[dict[str, Any]], expected_period: float) -> Optional[dict[str, Any]]:
    if not observations:
        return None
    with_period = [item for item in observations if _positive_float(item.get("period")) is not None]
    if not with_period:
        return observations[0]
    return min(
        with_period,
        key=lambda item: abs(float(item["period"]) - expected_period) / expected_period,
    )


def _sector_consistency(periods: list[float], tolerance: float) -> Optional[bool]:
    if len(periods) < 2:
        return None
    reference = median(periods)
    if reference <= 0:
        return False
    return all(abs(period - reference) / reference <= tolerance for period in periods)


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _positive_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _first_positive(*values: Any) -> Optional[float]:
    for value in values:
        parsed = _positive_float(value)
        if parsed is not None:
            return parsed
    return None


def _ratio(numerator: int, denominator: int) -> Optional[float]:
    return round(numerator / denominator, 6) if denominator else None


def _mean(values: Iterable[Optional[float]]) -> Optional[float]:
    materialized = [float(value) for value in values if value is not None]
    return round(mean(materialized), 8) if materialized else None


def _median(values: Iterable[Optional[float]]) -> Optional[float]:
    materialized = [float(value) for value in values if value is not None]
    return round(median(materialized), 8) if materialized else None


__all__ = [
    "BenchmarkPerformanceReport",
    "BenchmarkTargetMeasurement",
    "DEFAULT_PERIOD_TOLERANCE",
    "DEFAULT_RADIUS_TOLERANCE",
    "VerifiedTarget",
    "evaluate_benchmark_results",
    "load_verified_targets",
    "normalize_target_id",
]
