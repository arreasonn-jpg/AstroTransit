"""Contracts for real-noise injection parameter analysis."""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path("scripts/validation/analyze_real_noise_injection_parameters.py")
SPEC = importlib.util.spec_from_file_location("injection_parameter_recovery", SCRIPT)
ANALYSIS = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(ANALYSIS)


def test_epoch_error_uses_nearest_equivalent_epoch():
    assert abs(ANALYSIS.wrapped_epoch_error(109.9, 100.0, 10.0) + 0.1) < 1e-12
    assert abs(ANALYSIS.wrapped_epoch_error(90.1, 100.0, 10.0) - 0.1) < 1e-12


def test_percentile_is_interpolated():
    assert ANALYSIS.percentile([0.0, 10.0], 0.25) == 2.5


def test_frozen_trial_contract_is_accepted():
    path = Path("validation_runs/v1_injection_recovery/real_noise_v1/trials.csv")
    report = ANALYSIS.analyze(path)
    assert report["source"]["recorded_rows"] == 960
    assert report["cohorts"]["strict_period_recovery"]["row_count"] == 450
    assert report["cohorts"]["all_pipeline_candidates"]["row_count"] == 643
    assert report["uncertainty_coverage"]["status"] == "not_evaluated_no_per_trial_intervals"
