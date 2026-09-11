"""Contracts for the measured real-noise injection runner."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np

SCRIPT = Path("scripts/validation/run_real_noise_injection_campaign.py")
spec = importlib.util.spec_from_file_location("real_noise_runner", SCRIPT)
runner = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(runner)


def test_expanded_grid_and_ids_are_exact_and_unique():
    contract = json.loads(Path("validation_runs/v1_injection_recovery/real_noise_v1/contract.json").read_text())
    grid = runner.expand_grid(contract)
    assert len(grid) == 96
    assert sum(row["lane"] == "cascade_single_sector" for row in grid) == 80
    assert sum(row["lane"] == "long_period_stitched" for row in grid) == 16
    ids = {runner.injection_id(host, scenario) for host in range(10) for scenario in range(96)}
    assert len(ids) == 960
    assert min(ids) == "IRV1-000001"
    assert max(ids) == "IRV1-000960"


def test_strict_and_harmonic_period_matching_are_separate():
    assert runner.harmonic_match(5.0, 10.0, 0.02) == ("1/2x", False, True)
    assert runner.harmonic_match(10.1, 10.0, 0.02) == ("1x", True, True)
    assert runner.harmonic_match(None, 10.0, 0.02) == ("none", False, False)


def test_observed_injection_distinguishes_sampling_availability():
    scenario = runner.InjectionScenario(50.0, 500e-6, 0.15, 35.0, label="IRV1-test")
    assert runner.observed_injection(np.arange(0.0, 27.0, 0.01), scenario) == (0, 0)
    events, cadences = runner.observed_injection(np.arange(0.0, 27.0, 0.01), runner.InjectionScenario(50.0, 500e-6, 0.15, 10.0))
    assert events == 1 and cadences > 0


def test_wilson_interval_preserves_empty_denominator():
    assert runner.wilson(0, 0) is None
    low, high = runner.wilson(5, 10)
    assert 0.0 < low < 0.5 < high < 1.0
