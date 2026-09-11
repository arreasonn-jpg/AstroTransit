#!/usr/bin/env python3
"""Run and aggregate frozen real-noise injection-recovery v1 shards."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from astrotransit.data.tess_client import TESSClient
from astrotransit.detection.cascade import CascadeDetector
from astrotransit.detection.long_period import LongPeriodTransitSearch
from astrotransit.preprocessing.pipeline import TESSPreprocessingPipeline
from astrotransit.preprocessing.stitching import stitch_detrended_light_curves
from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve
from astrotransit.settings import get_settings
from astrotransit.validation.injection_recovery import InjectionScenario, inject_box_transit

FIELDS = [
    "injection_id", "host_id", "host_index", "scenario_index", "lane", "sector_ids", "seed",
    "period_bin", "stellar_type", "host_noise_bin", "injected_period_days", "injected_depth_ppm",
    "injected_duration_days", "injected_t0", "injected_rp_rs", "phase_fraction",
    "n_observed_injected_events", "n_injected_cadences", "evaluable", "outcome",
    "pipeline_candidate", "detector_confirmed", "recovered_period_days", "period_ratio",
    "period_error_days", "period_error_fraction", "harmonic_class", "strict_recovery",
    "harmonic_aware_recovery", "recovered_depth_ppm", "depth_error_ppm",
    "depth_error_fraction", "recovered_duration_days", "duration_error_days", "recovered_t0",
    "t0_error_days", "recovered_rp_rs", "rp_rs_error", "detector_status", "failure_detail",
]
HARMONICS = ((1 / 3, "1/3x"), (1 / 2, "1/2x"), (1.0, "1x"), (2.0, "2x"), (3.0, "3x"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expand_grid(contract: dict[str, Any]) -> list[dict[str, Any]]:
    axes = contract["grid"]["axes"]
    rows = []
    for period, depth, duration, phase in itertools.product(
        axes["period_days"], axes["depth_ppm"], axes["duration_days"], axes["phase_fraction"]
    ):
        rows.append({
            "period_days": float(period), "depth_ppm": int(depth), "duration_days": float(duration),
            "phase_fraction": float(phase),
            "period_bin": "short" if period < 5 else ("mid" if period <= 20 else "long"),
            "lane": "cascade_single_sector" if period <= 20 else "long_period_stitched",
        })
    return rows


def injection_id(host_index: int, scenario_index: int, scenarios_per_host: int = 96) -> str:
    return f"IRV1-{host_index * scenarios_per_host + scenario_index + 1:06d}"


def harmonic_match(recovered: float | None, injected: float, tolerance: float) -> tuple[str, bool, bool]:
    if recovered is None or not math.isfinite(recovered) or recovered <= 0:
        return "none", False, False
    ratio = recovered / injected
    error, label = min((abs(ratio - factor) / factor, label) for factor, label in HARMONICS)
    return (label if error <= tolerance else "other", abs(ratio - 1.0) <= tolerance, error <= tolerance)


def stellar_type(teff: float) -> str:
    return "M" if teff < 3900 else ("K" if teff < 5200 else ("G" if teff < 6000 else "F_or_hotter"))


def noise_bins(hosts: list[dict[str, Any]]) -> dict[str, str]:
    ordered = sorted(hosts, key=lambda row: (float(row["median_noise_ppm"]), row["tic_id"]))
    result = {}
    for index, host in enumerate(ordered):
        result[host["tic_id"]] = "low" if index < len(ordered) / 3 else ("medium" if index < 2 * len(ordered) / 3 else "high")
    return result


def observed_injection(time: np.ndarray, scenario: InjectionScenario) -> tuple[int, int]:
    phase = np.mod(time - scenario.t0 + 0.5 * scenario.period_days, scenario.period_days) - 0.5 * scenario.period_days
    indices = np.flatnonzero(np.abs(phase) <= 0.5 * scenario.duration_days)
    if not indices.size:
        return 0, 0
    gaps = np.diff(time[indices]) > max(2 * np.nanmedian(np.diff(time)), scenario.duration_days)
    return int(1 + np.count_nonzero(gaps)), int(indices.size)


def injected_curve(curve: DetrendedLightCurve, scenario: InjectionScenario) -> DetrendedLightCurve:
    return DetrendedLightCurve(
        target_id=curve.target_id, sector=curve.sector, time=np.asarray(curve.time).copy(),
        flux=inject_box_transit(curve.time, curve.flux, scenario),
        flux_err=np.asarray(curve.flux_err).copy(), trend=np.asarray(curve.trend).copy(),
        raw_flux=np.asarray(curve.raw_flux).copy(), method=f"{curve.method}+post_detrending_box_injection_v1",
        window_length=curve.window_length, break_tolerance=curve.break_tolerance,
        meta={**curve.meta, "injection_id": scenario.label},
    )


def base_record(host, host_index, grid_index, grid, seed, noise_bin):
    return {
        "injection_id": injection_id(host_index, grid_index), "host_id": host["target_id"],
        "host_index": host_index, "scenario_index": grid_index, "lane": grid["lane"],
        "sector_ids": json.dumps(host["sectors"]), "seed": seed, "period_bin": grid["period_bin"],
        "stellar_type": stellar_type(float(host["stellar"]["teff_k"])), "host_noise_bin": noise_bin,
        "injected_period_days": grid["period_days"], "injected_depth_ppm": grid["depth_ppm"],
        "injected_duration_days": grid["duration_days"], "phase_fraction": grid["phase_fraction"],
        "injected_rp_rs": math.sqrt(grid["depth_ppm"] / 1e6), "injected_t0": None,
        "n_observed_injected_events": 0, "n_injected_cadences": 0, "evaluable": False,
        "outcome": "not_run", "pipeline_candidate": False, "detector_confirmed": False,
        "recovered_period_days": None, "period_ratio": None, "period_error_days": None,
        "period_error_fraction": None, "harmonic_class": "none", "strict_recovery": False,
        "harmonic_aware_recovery": False, "recovered_depth_ppm": None, "depth_error_ppm": None,
        "depth_error_fraction": None, "recovered_duration_days": None, "duration_error_days": None,
        "recovered_t0": None, "t0_error_days": None, "recovered_rp_rs": None, "rp_rs_error": None,
        "detector_status": "not_run", "failure_detail": "",
    }


def set_recovery(record, recovered, tolerance):
    period = recovered.get("period")
    period = float(period) if period is not None and float(period) > 0 else None
    record["recovered_period_days"] = period
    if period is not None:
        injected = float(record["injected_period_days"])
        record["period_ratio"] = period / injected
        record["period_error_days"] = period - injected
        record["period_error_fraction"] = abs(period - injected) / injected
    label, strict, harmonic = harmonic_match(period, float(record["injected_period_days"]), tolerance)
    record["harmonic_class"] = label
    record["strict_recovery"] = bool(record["detector_confirmed"] and strict)
    record["harmonic_aware_recovery"] = bool(record["detector_confirmed"] and harmonic)
    mapping = {"depth_ppm": "recovered_depth_ppm", "duration_days": "recovered_duration_days", "t0": "recovered_t0", "rp_rs": "recovered_rp_rs"}
    for key, output in mapping.items():
        record[output] = recovered.get(key)
    for recovered_key, injected_key, error_key in (
        ("recovered_depth_ppm", "injected_depth_ppm", "depth_error_ppm"),
        ("recovered_duration_days", "injected_duration_days", "duration_error_days"),
        ("recovered_t0", "injected_t0", "t0_error_days"),
        ("recovered_rp_rs", "injected_rp_rs", "rp_rs_error"),
    ):
        if record[recovered_key] is not None:
            record[error_key] = float(record[recovered_key]) - float(record[injected_key])
    if record["recovered_depth_ppm"] is not None:
        record["depth_error_fraction"] = abs(record["depth_error_ppm"]) / float(record["injected_depth_ppm"])


def unavailable_rows(host, host_index, grids, lane, seed, noise_bin, detail):
    rows = []
    for index, grid in enumerate(grids):
        if grid["lane"] == lane:
            row = base_record(host, host_index, index, grid, seed, noise_bin)
            row["outcome"], row["failure_detail"] = "data_access_failure", detail
            rows.append(row)
    return rows


def write_shard(output, rows, host, lane, available):
    output.mkdir(parents=True, exist_ok=True)
    with (output / "trials.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
    (output / "availability.json").write_text(json.dumps({"host_id": host["target_id"], "lane": lane, "available": available, "trial_rows": len(rows)}, indent=2, sort_keys=True) + "\n")
    return 0


def run_shard(args):
    contract = json.loads(args.contract.read_text())
    corpus = json.loads(args.hosts.read_text())
    hosts = corpus["hosts"]
    if contract["status"] != "pending_run" or len(hosts) != 10:
        raise SystemExit("Campaign requires frozen ten-host corpus in pending_run state")
    if sha256_file(args.hosts) != contract["host_corpus"]["sha256"]:
        raise SystemExit("Frozen host-corpus SHA-256 mismatch")
    host, grids, lane, seed = hosts[args.host_index], expand_grid(contract), args.lane, int(contract["seed"])
    noise_bin = noise_bins(hosts)[host["tic_id"]]
    settings = get_settings()
    tess = TESSClient(author=settings.tess.author, exptime=settings.tess.exptime,
                      quality_bitmask=settings.tess.quality_bitmask, cache_dir=str(args.cache_dir),
                      cache_ttl_hours=settings.tess.cache_ttl_hours, use_cache=True)
    preprocessing = TESSPreprocessingPipeline(settings=settings)
    try:
        curves = [preprocessing.run(tess.get_lightcurve(host["target_id"], sector=int(sector))).detrended for sector in host["sectors"]]
        source = curves[0] if lane == "cascade_single_sector" else stitch_detrended_light_curves(curves).as_detrended()
    except Exception as exc:
        return write_shard(args.output, unavailable_rows(host, args.host_index, grids, lane, seed, noise_bin, f"{type(exc).__name__}:{exc}"), host, lane, False)
    detector = (CascadeDetector(settings=settings, stellar_radius=float(host["stellar"]["radius_rsun"]), stellar_mass=float(host["stellar"]["mass_msun"]))
                if lane == "cascade_single_sector" else LongPeriodTransitSearch(stellar_radius_rsun=float(host["stellar"]["radius_rsun"]), stellar_mass_msun=float(host["stellar"]["mass_msun"])))
    rows, tolerance = [], float(contract["recovery_contract"]["strict_period_tolerance_fraction"])
    for index, grid in enumerate(grids):
        if grid["lane"] != lane:
            continue
        row = base_record(host, args.host_index, index, grid, seed, noise_bin)
        scenario = InjectionScenario(grid["period_days"], grid["depth_ppm"] / 1e6, grid["duration_days"], float(source.time[0]) + grid["phase_fraction"] * grid["period_days"], label=row["injection_id"])
        row["injected_t0"] = scenario.t0
        events, cadences = observed_injection(np.asarray(source.time), scenario)
        row["n_observed_injected_events"], row["n_injected_cadences"] = events, cadences
        if cadences == 0:
            row["outcome"] = "not_evaluated_no_observed_injection"; rows.append(row); continue
        row["evaluable"] = True
        try:
            result = detector.detect(injected_curve(source, scenario)) if lane == "cascade_single_sector" else detector.search(injected_curve(source, scenario))
            if lane == "cascade_single_sector":
                row["pipeline_candidate"] = bool(result.has_candidate and result.status.value != "error")
                row["detector_confirmed"], row["detector_status"] = bool(result.confirmed), result.status.value
                if result.status.value == "error":
                    row["outcome"], row["failure_detail"] = "detector_error", " | ".join(result.decision_log)
                    rows.append(row); continue
                recovered = {"period": result.period or None, "depth_ppm": result.depth * 1e6 if result.depth else None, "duration_days": result.duration or None, "t0": result.t0 or None, "rp_rs": result.rp_rs or None}
            else:
                best = result.best
                row["pipeline_candidate"] = bool(result.has_candidate)
                row["detector_confirmed"], row["detector_status"] = bool(result.has_candidate), best.identifiability if best else "no_candidate"
                recovered = {"period": best.period if best else None, "depth_ppm": best.depth * 1e6 if best else None, "duration_days": best.duration if best else None, "t0": best.t0 if best else None, "rp_rs": math.sqrt(best.depth) if best and best.depth > 0 else None}
            set_recovery(row, recovered, tolerance)
            row["outcome"] = "strict_recovery" if row["strict_recovery"] else ("harmonic_only_recovery" if row["harmonic_aware_recovery"] else ("period_mismatch" if row["pipeline_candidate"] else "no_candidate"))
        except Exception as exc:
            row["outcome"], row["detector_status"], row["failure_detail"] = "detector_error", "error", f"{type(exc).__name__}:{exc}"
        rows.append(row)
    return write_shard(args.output, rows, host, lane, True)


def as_bool(value):
    return str(value).lower() == "true"


def wilson(successes, total, z=1.959963984540054):
    if total == 0:
        return None
    p, denominator = successes / total, 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, center - radius), min(1.0, center + radius)]


def aggregate(args):
    contract = json.loads(args.contract.read_text())
    rows = []
    for path in sorted(args.shards.glob("**/trials.csv")):
        with path.open(newline="", encoding="utf-8") as handle:
            rows.extend(csv.DictReader(handle))
    expected, ids = int(contract["grid"]["planned_total_trials"]), [row["injection_id"] for row in rows]
    if len(rows) != expected or len(set(ids)) != expected:
        raise SystemExit(f"Expected {expected} unique trials, got rows={len(rows)} unique={len(set(ids))}")
    rows.sort(key=lambda row: row["injection_id"]); args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "trials.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
    evaluable = [row for row in rows if as_bool(row["evaluable"])]
    strict = sum(as_bool(row["strict_recovery"]) for row in evaluable)
    harmonic = sum(as_bool(row["harmonic_aware_recovery"]) for row in evaluable)
    def grouped(field):
        result = {}
        for value in sorted({row[field] for row in rows}):
            subset = [row for row in evaluable if row[field] == value]
            s = sum(as_bool(row["strict_recovery"]) for row in subset); h = sum(as_bool(row["harmonic_aware_recovery"]) for row in subset)
            result[value] = {"planned": sum(row[field] == value for row in rows), "evaluable": len(subset), "strict_recovered": s, "strict_completeness": s / len(subset) if subset else None, "harmonic_recovered": h, "harmonic_aware_completeness": h / len(subset) if subset else None}
        return result
    outcomes = {value: sum(row["outcome"] == value for row in rows) for value in sorted({row["outcome"] for row in rows})}
    report = {"schema_version": "1.0", "campaign": contract["campaign"], "status": "measured", "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "claim_scope": contract["claim_scope"], "planned_trials": expected, "recorded_trials": len(rows), "evaluable_trials": len(evaluable), "not_evaluated_trials": len(rows) - len(evaluable), "strict_recovered": strict, "strict_completeness": strict / len(evaluable) if evaluable else None, "strict_completeness_95pct_wilson": wilson(strict, len(evaluable)), "harmonic_aware_recovered": harmonic, "harmonic_aware_completeness": harmonic / len(evaluable) if evaluable else None, "harmonic_aware_95pct_wilson": wilson(harmonic, len(evaluable)), "harmonic_confusion_trials": harmonic - strict, "outcomes": outcomes, "by_lane": grouped("lane"), "by_period_bin": grouped("period_bin"), "by_depth_ppm": grouped("injected_depth_ppm"), "by_duration_days": grouped("injected_duration_days"), "by_host_noise_bin": grouped("host_noise_bin"), "by_stellar_type": grouped("stellar_type"), "claim_boundary": "Measured detection-stage completeness on frozen selected real-noise hosts; not population or end-to-end preprocessing completeness.", "uncertainty_coverage": {"status": "not_evaluated_no_intervals"}}
    (args.output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    availability = {"planned_trials": len(rows), "evaluable_trials": len(evaluable), "excluded_from_denominator": len(rows) - len(evaluable), "outcomes": outcomes}
    (args.output / "data_availability.json").write_text(json.dumps(availability, indent=2, sort_keys=True) + "\n")
    output_hash = hashlib.sha256((args.output / "trials.csv").read_bytes() + (args.output / "report.json").read_bytes() + (args.output / "data_availability.json").read_bytes()).hexdigest()
    environment = json.loads(args.environment.read_text())
    import subprocess
    manifest = {"schema_version": "1.0", "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "dirty_state": True, "dirty_state_reason": "artifacts downloaded/generated after clean environment snapshot", "python_version": environment.get("python_version"), "seed": contract["seed"], "config_sha256": sha256_file(args.config), "host_corpus_sha256": sha256_file(args.hosts), "expanded_grid_sha256": contract["grid"]["expanded_grid_sha256"], "dependency_lock_sha256": sha256_file(args.lock), "environment_manifest_sha256": sha256_file(args.environment), "trials_sha256": sha256_file(args.output / "trials.csv"), "report_sha256": sha256_file(args.output / "report.json"), "output_sha256": output_hash}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    contract["status"], contract["status_reason"] = "measured", "immutable_measured_report_frozen"
    contract["measured_report"] = {"path": str(args.output / "report.json"), "trials_sha256": manifest["trials_sha256"], "report_sha256": manifest["report_sha256"], "output_sha256": output_hash}
    args.contract.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    return 0


def parser():
    root = argparse.ArgumentParser(description=__doc__); sub = root.add_subparsers(dest="command", required=True)
    shard = sub.add_parser("run-shard"); shard.add_argument("--contract", type=Path, required=True); shard.add_argument("--hosts", type=Path, required=True); shard.add_argument("--host-index", type=int, choices=range(10), required=True); shard.add_argument("--lane", choices=("cascade_single_sector", "long_period_stitched"), required=True); shard.add_argument("--cache-dir", type=Path, required=True); shard.add_argument("--output", type=Path, required=True)
    agg = sub.add_parser("aggregate"); agg.add_argument("--contract", type=Path, required=True); agg.add_argument("--hosts", type=Path, required=True); agg.add_argument("--shards", type=Path, required=True); agg.add_argument("--output", type=Path, required=True); agg.add_argument("--config", type=Path, required=True); agg.add_argument("--lock", type=Path, required=True); agg.add_argument("--environment", type=Path, required=True)
    return root


def main():
    args = parser().parse_args()
    return run_shard(args) if args.command == "run-shard" else aggregate(args)


if __name__ == "__main__":
    raise SystemExit(main())
