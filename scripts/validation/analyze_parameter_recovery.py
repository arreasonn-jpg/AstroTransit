#!/usr/bin/env python3
"""Freeze parameter-recovery statistics from a known-target aggregate CSV."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


def _rounded(value: float) -> float:
    return round(float(value), 12)


def _stats(rows: list[dict[str, object]], parameter: str) -> dict[str, float]:
    truth = np.asarray([row[f"expected_{parameter}"] for row in rows], dtype=float)
    recovered = np.asarray([row[f"recovered_{parameter}"] for row in rows], dtype=float)
    error = recovered - truth
    relative_error = error / truth
    log_ratio = np.log(recovered / truth)
    values = {
        "bias": np.mean(error),
        "scatter": np.std(error, ddof=0),
        "rmse": np.sqrt(np.mean(error**2)),
        "mae": np.mean(np.abs(error)),
        "median_error": np.median(error),
        "median_absolute_error": np.median(np.abs(error)),
        "relative_bias": np.mean(relative_error),
        "relative_scatter": np.std(relative_error, ddof=0),
        "relative_rmse": np.sqrt(np.mean(relative_error**2)),
        "relative_mae": np.mean(np.abs(relative_error)),
        "median_relative_error": np.median(relative_error),
        "median_absolute_relative_error": np.median(np.abs(relative_error)),
        "log_ratio_bias": np.mean(log_ratio),
        "log_ratio_scatter": np.std(log_ratio, ddof=0),
        "log_ratio_rmse": np.sqrt(np.mean(log_ratio**2)),
    }
    return {name: _rounded(value) for name, value in values.items()}


def _scope(rows: list[dict[str, object]]) -> dict[str, object]:
    return {"n": len(rows), "period": _stats(rows, "period"), "radius": _stats(rows, "radius")}


def _load_rows(path: Path) -> list[dict[str, object]]:
    required = {
        "target_id", "difficulty", "expected_period_days", "recovered_period_days",
        "expected_radius_rearth", "recovered_radius_rearth", "period_recovered",
        "radius_recovered",
    }
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required columns: {sorted(missing)}")
        rows = []
        for row in reader:
            rows.append({
                "target_id": row["target_id"],
                "difficulty": row["difficulty"],
                "expected_period": float(row["expected_period_days"]),
                "recovered_period": float(row["recovered_period_days"]),
                "expected_radius": float(row["expected_radius_rearth"]),
                "recovered_radius": float(row["recovered_radius_rearth"]),
                "period_recovered": row["period_recovered"].strip().lower() == "true",
                "radius_recovered": row["radius_recovered"].strip().lower() == "true",
            })
    if not rows:
        raise ValueError("No parameter-recovery rows found")
    if len({row["target_id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate target_id in aggregate CSV")
    return rows


def build_report(source: Path) -> dict[str, object]:
    rows = _load_rows(source)
    period_rows = [row for row in rows if row["period_recovered"]]
    radius_rows = [row for row in rows if row["radius_recovered"]]
    difficulties = sorted({str(row["difficulty"]) for row in rows})
    report: dict[str, object] = {
        "schema_version": "1.0",
        "campaign": "known_planets_50_v1_parameter_recovery",
        "source": "validation_runs/v1_known_planets/known_planets_50_v1/aggregate/targets.csv",
        "selected_targets": 50,
        "evaluated_targets": len(rows),
        "not_evaluated_targets": 50 - len(rows),
        "coverage": None,
        "coverage_status": "not_evaluated_no_intervals",
        "all_evaluable": _scope(rows),
        "conditional_recovery": {
            "period": {"n": len(period_rows), **_stats(period_rows, "period")},
            "radius": {"n": len(radius_rows), **_stats(radius_rows, "radius")},
        },
        "by_difficulty": {},
        "limitations": [
            "All-evaluable metrics include alias and catastrophic recovery failures.",
            "Conditional metrics describe only rows within the frozen tolerance and are not completeness estimates.",
            "Credible-interval coverage is unavailable because the frozen aggregate contains point estimates without intervals.",
            "Radius reliability status is absent from this aggregate; reliability-stratified analysis requires a dedicated diagnostic artifact.",
        ],
    }
    by_difficulty: dict[str, object] = {}
    for difficulty in difficulties:
        subset = [row for row in rows if row["difficulty"] == difficulty]
        by_difficulty[difficulty] = {
            **_scope(subset),
            "period_within_tolerance": sum(bool(row["period_recovered"]) for row in subset),
            "radius_within_tolerance": sum(bool(row["radius_recovered"]) for row in subset),
        }
    report["by_difficulty"] = by_difficulty
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    report["canonical_output_hash"] = hashlib.sha256(canonical).hexdigest()
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
