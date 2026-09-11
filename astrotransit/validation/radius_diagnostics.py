"""Measured TLS-versus-fit radius diagnostics for validation campaigns.

This module records the quantities needed to investigate radius disagreement.
It does not classify a fit as correct and does not define a scientific gate.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np

RADIUS_DIAGNOSTIC_SCHEMA_VERSION = "1.1"


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _finite(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def estimate_detrended_depth(
    detrended: Any,
    *,
    period: Any,
    t0: Any,
    duration: Any,
) -> tuple[Optional[float], int, int]:
    """Estimate local median transit depth from the detrended light curve."""

    period_value = _finite(period)
    t0_value = _finite(t0)
    duration_value = _finite(duration)
    if not period_value or t0_value is None or not duration_value:
        return None, 0, 0
    if period_value <= 0 or duration_value <= 0 or duration_value >= period_value:
        return None, 0, 0

    time = np.asarray(_get(detrended, "time", []), dtype=float)
    flux = np.asarray(_get(detrended, "flux", []), dtype=float)
    if time.shape != flux.shape or time.size == 0:
        return None, 0, 0

    finite = np.isfinite(time) & np.isfinite(flux)
    phase = ((time - t0_value + 0.5 * period_value) % period_value) - 0.5 * period_value
    in_transit = finite & (np.abs(phase) <= 0.5 * duration_value)
    local_baseline = finite & (np.abs(phase) >= duration_value) & (
        np.abs(phase) <= 2.5 * duration_value
    )
    if int(local_baseline.sum()) < 5:
        local_baseline = finite & ~in_transit

    n_in = int(in_transit.sum())
    n_baseline = int(local_baseline.sum())
    if n_in < 2 or n_baseline < 5:
        return None, n_in, n_baseline

    depth = float(np.nanmedian(flux[local_baseline]) - np.nanmedian(flux[in_transit]))
    if not math.isfinite(depth):
        return None, n_in, n_baseline
    return max(0.0, depth), n_in, n_baseline


@dataclass(frozen=True)
class RadiusDiagnosticRow:
    target_id: str
    sector: int
    comparison_status: str
    fit_method: str
    fit_optimizer_boundary_hit: bool
    fit_optimizer_boundary_hits: tuple[str, ...]
    limb_darkening_parameterization: str
    cascade_status: str
    tls_period_days: Optional[float]
    tls_duration_hours: Optional[float]
    tls_depth_ppm: Optional[float]
    tls_rp_rs: Optional[float]
    fit_rp_rs: Optional[float]
    rp_rs_delta_fit_minus_tls: Optional[float]
    rp_rs_fractional_delta_vs_tls: Optional[float]
    stellar_radius_rsun: Optional[float]
    stellar_radius_source: str
    fit_planet_radius_rearth: Optional[float]
    detrended_depth_ppm: Optional[float]
    detrended_depth_rp_rs_sqrt: Optional[float]
    detrend_method: str
    detrend_window_days: Optional[float]
    limb_darkening_u1: Optional[float]
    limb_darkening_u2: Optional[float]
    impact_parameter: Optional[float]
    a_over_rs: Optional[float]
    baseline: Optional[float]
    log_jitter: Optional[float]
    residual_rms_ppm: Optional[float]
    configured_cadence_seconds: Optional[float]
    observed_median_cadence_seconds: Optional[float]
    n_points: int
    n_in_transit_points: int
    n_local_baseline_points: int
    tls_transit_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RadiusDiagnosticReport:
    rows: list[RadiusDiagnosticRow] = field(default_factory=list)
    schema_version: str = RADIUS_DIAGNOSTIC_SCHEMA_VERSION
    interpretation: str = (
        "Measured diagnostic only; no discrepancy threshold or scientific PASS/FAIL is implied."
    )

    def to_dict(self) -> dict[str, Any]:
        evaluated = [
            row.rp_rs_fractional_delta_vs_tls
            for row in self.rows
            if row.comparison_status == "evaluated"
            and row.rp_rs_fractional_delta_vs_tls is not None
        ]
        absolute = [abs(value) for value in evaluated]
        summary = {
            "n_rows": len(self.rows),
            "n_evaluated": len(evaluated),
            "n_not_evaluated": len(self.rows) - len(evaluated),
            "median_fractional_delta_fit_minus_tls": (
                float(np.median(evaluated)) if evaluated else None
            ),
            "median_absolute_fractional_delta": (
                float(np.median(absolute)) if absolute else None
            ),
        }
        return {
            "schema_version": self.schema_version,
            "interpretation": self.interpretation,
            "summary": summary,
            "rows": [row.to_dict() for row in self.rows],
        }


def _observed_cadence_seconds(detrended: Any) -> Optional[float]:
    time = np.asarray(_get(detrended, "time", []), dtype=float)
    finite = np.sort(time[np.isfinite(time)])
    if finite.size < 2:
        return None
    positive_steps = np.diff(finite)
    positive_steps = positive_steps[positive_steps > 0]
    if positive_steps.size == 0:
        return None
    return float(np.median(positive_steps) * 86400.0)


def build_radius_diagnostic_row(
    target_result: Any,
    sector_result: Any,
    *,
    configured_cadence_seconds: Any = None,
) -> RadiusDiagnosticRow:
    """Build one provenance-rich sector diagnostic without inventing values."""

    candidate = _get(sector_result, "candidate")
    tls = _get(candidate, "tls_result")
    fit = _get(sector_result, "fit_result")
    detrended = _get(sector_result, "detrended")
    stellar = _get(target_result, "stellar_props")

    tls_rp_rs = _finite(_get(tls, "rp_rs"))
    fit_rp_rs = _finite(_get(fit, "rp_rs"))
    fit_success = bool(_get(fit, "success", False))
    if tls is None:
        status = "not_evaluated_missing_tls"
    elif not fit_success or fit_rp_rs is None:
        status = "not_evaluated_missing_fit"
    elif tls_rp_rs is None or tls_rp_rs <= 0:
        status = "not_evaluated_invalid_tls_rp_rs"
    else:
        status = "evaluated"

    delta = None
    fractional_delta = None
    if status == "evaluated" and fit_rp_rs is not None and tls_rp_rs is not None:
        delta = fit_rp_rs - tls_rp_rs
        fractional_delta = delta / tls_rp_rs

    tls_depth = _finite(_get(tls, "depth"))
    period = _get(tls, "period")
    t0 = _get(tls, "t0")
    duration = _get(tls, "duration")
    measured_depth, n_in, n_baseline = estimate_detrended_depth(
        detrended, period=period, t0=t0, duration=duration
    )
    measured_depth_sqrt = math.sqrt(measured_depth) if measured_depth is not None else None

    derived = _get(fit, "derived")
    stellar_source = str(_get(stellar, "source", "") or "")
    cascade_status = _get(candidate, "status", "")
    cascade_status = str(getattr(cascade_status, "value", cascade_status) or "")

    return RadiusDiagnosticRow(
        target_id=str(_get(target_result, "target_id", _get(sector_result, "target_id", ""))),
        sector=int(_get(sector_result, "sector", -1)),
        comparison_status=status,
        fit_method=str(_get(fit, "fit_method", "") or ""),
        fit_optimizer_boundary_hit=bool(
            _get(fit, "optimizer_boundary_hit", False)
        ),
        fit_optimizer_boundary_hits=tuple(
            str(item) for item in (_get(fit, "optimizer_boundary_hits", ()) or ())
        ),
        limb_darkening_parameterization=str(
            _get(fit, "limb_darkening_parameterization", "") or ""
        ),
        cascade_status=cascade_status,
        tls_period_days=_finite(period),
        tls_duration_hours=(None if _finite(duration) is None else _finite(duration) * 24.0),
        tls_depth_ppm=(None if tls_depth is None else tls_depth * 1e6),
        tls_rp_rs=tls_rp_rs,
        fit_rp_rs=fit_rp_rs,
        rp_rs_delta_fit_minus_tls=delta,
        rp_rs_fractional_delta_vs_tls=fractional_delta,
        stellar_radius_rsun=_finite(_get(stellar, "radius")),
        stellar_radius_source=stellar_source,
        fit_planet_radius_rearth=_finite(
            _get(derived, "planet_radius_rearth", _get(fit, "planet_radius_rearth"))
        ),
        detrended_depth_ppm=(None if measured_depth is None else measured_depth * 1e6),
        detrended_depth_rp_rs_sqrt=measured_depth_sqrt,
        detrend_method=str(_get(detrended, "method", "") or ""),
        detrend_window_days=_finite(_get(detrended, "window_length")),
        limb_darkening_u1=_finite(_get(fit, "u1")),
        limb_darkening_u2=_finite(_get(fit, "u2")),
        impact_parameter=_finite(_get(fit, "impact_parameter")),
        a_over_rs=_finite(_get(fit, "a_over_rs")),
        baseline=_finite(_get(fit, "baseline")),
        log_jitter=_finite(_get(fit, "log_jitter")),
        residual_rms_ppm=(
            None
            if _finite(_get(fit, "residual_rms")) is None
            else _finite(_get(fit, "residual_rms")) * 1e6
        ),
        configured_cadence_seconds=_finite(configured_cadence_seconds),
        observed_median_cadence_seconds=_observed_cadence_seconds(detrended),
        n_points=int(_get(detrended, "n_points", len(_get(detrended, "time", []))) or 0),
        n_in_transit_points=n_in,
        n_local_baseline_points=n_baseline,
        tls_transit_count=int(_get(tls, "transit_count", 0) or 0),
    )


def build_radius_diagnostic_report(
    target_results: Iterable[Any],
    *,
    configured_cadence_seconds: Any = None,
) -> RadiusDiagnosticReport:
    rows = [
        build_radius_diagnostic_row(
            target_result,
            sector_result,
            configured_cadence_seconds=configured_cadence_seconds,
        )
        for target_result in target_results
        for sector_result in _get(target_result, "sector_results", [])
        if _get(sector_result, "candidate") is not None
    ]
    rows.sort(key=lambda row: (row.target_id, row.sector))
    return RadiusDiagnosticReport(rows=rows)


def write_radius_diagnostic_report(
    report: RadiusDiagnosticReport,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Write deterministic JSON and CSV artifacts."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "radius_diagnostics.json"
    csv_path = destination / "radius_diagnostics.csv"
    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    fieldnames = list(RadiusDiagnosticRow.__dataclass_fields__)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(row.to_dict() for row in report.rows)
    return json_path, csv_path
