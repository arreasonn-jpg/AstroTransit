#!/usr/bin/env python3
"""Measure point-estimate accuracy from frozen injection-trial evidence."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

EXPECTED_SHA = "6dff856f848b89b17b14dca33a938ab2bc13ae5830fd25795998ed4dea199a47"
EXPECTED_ROWS = 960
REPLICATES = 10_000
SEED = 42


def wrapped_epoch_error(recovered, injected, period):
    return (recovered - injected + 0.5 * period) % period - 0.5 * period


def percentile(values, probability):
    values = sorted(values)
    position = (len(values) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def number(row, key):
    value = row.get(key, "")
    return None if value == "" else float(value)


def metric_values(row):
    pairs = {
        "period_signed_fraction": ("injected_period_days", "recovered_period_days"),
        "depth_signed_fraction": ("injected_depth_ppm", "recovered_depth_ppm"),
        "duration_signed_fraction": ("injected_duration_days", "recovered_duration_days"),
        "rp_rs_signed_fraction": ("injected_rp_rs", "recovered_rp_rs"),
    }
    result = {}
    for metric, (injected_key, recovered_key) in pairs.items():
        injected, recovered = number(row, injected_key), number(row, recovered_key)
        if injected and recovered is not None:
            result[metric] = (recovered - injected) / injected
    period = number(row, "injected_period_days")
    injected_t0, recovered_t0 = number(row, "injected_t0"), number(row, "recovered_t0")
    duration = number(row, "injected_duration_days")
    if period and injected_t0 is not None and recovered_t0 is not None:
        error = wrapped_epoch_error(recovered_t0, injected_t0, period)
        result["t0_wrapped_error_days"] = error
        if duration:
            result["t0_wrapped_error_duration_units"] = error / duration
    return result


def bootstrap(by_host, statistic, seed):
    hosts, rng, estimates = sorted(by_host), random.Random(seed), []
    for _ in range(REPLICATES):
        sample = [value for _ in hosts for value in by_host[rng.choice(hosts)]]
        estimates.append(statistic(sample))
    return [percentile(estimates, 0.025), percentile(estimates, 0.975)]


def summarize(rows, seed_offset=0):
    grouped = defaultdict(lambda: defaultdict(list))
    for row in rows:
        for metric, value in metric_values(row).items():
            grouped[metric][row["host_id"]].append(value)
    parameters = {}
    for index, metric in enumerate(sorted(grouped)):
        by_host = grouped[metric]
        values = [value for host in sorted(by_host) for value in by_host[host]]
        absolute = [abs(value) for value in values]
        rmse = lambda sample: math.sqrt(statistics.fmean(v * v for v in sample))
        parameters[metric] = {
            "n_available": len(values),
            "bias": statistics.fmean(values),
            "scatter_sample_std": statistics.stdev(values),
            "rmse": rmse(values),
            "median_absolute_error": statistics.median(absolute),
            "p95_absolute_error": percentile(absolute, 0.95),
            "bias_95pct_host_block_bootstrap": bootstrap(
                by_host, statistics.fmean, SEED + seed_offset + 2 * index
            ),
            "rmse_95pct_host_block_bootstrap": bootstrap(
                by_host, rmse, SEED + seed_offset + 2 * index + 1
            ),
        }
    return {"row_count": len(rows), "host_count": len({r["host_id"] for r in rows}), "parameters": parameters}


def analyze(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA:
        raise SystemExit(f"Frozen trials SHA-256 mismatch: {digest}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    ids = [row["injection_id"] for row in rows]
    if len(rows) != EXPECTED_ROWS or len(set(ids)) != EXPECTED_ROWS:
        raise SystemExit("Expected 960 unique trial rows")
    candidate = [row for row in rows if row["pipeline_candidate"].lower() == "true"]
    strict = [row for row in rows if row["strict_recovery"].lower() == "true"]
    return {
        "schema_version": "1.0",
        "campaign": "real_noise_injection_parameter_recovery_v1",
        "status": "measured",
        "source": {"path": str(path), "sha256": digest, "recorded_rows": len(rows)},
        "method": {"primary_cohort": "strict_period_recovery", "secondary_cohort": "all_pipeline_candidates", "bootstrap_unit": "host_id", "bootstrap_replicates": REPLICATES, "bootstrap_seed": SEED, "t0_error": "nearest equivalent epoch wrapped by injected period"},
        "cohorts": {"strict_period_recovery": summarize(strict), "all_pipeline_candidates": summarize(candidate, 100)},
        "uncertainty_coverage": {"status": "not_evaluated_no_per_trial_intervals"},
        "claim_boundary": "Selection-conditioned point-estimate accuracy on recovered injections from ten selected real-noise hosts; not population accuracy or uncertainty coverage.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(analyze(args.trials), indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
