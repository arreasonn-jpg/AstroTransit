"""Contract for the frozen real-noise injection parameter evidence."""
from __future__ import annotations

import json
from pathlib import Path

REPORT = Path(
    "validation_runs/v1_injection_recovery/real_noise_v1/parameter_recovery_report.json"
)
EXPECTED_SOURCE_SHA256 = "6dff856f848b89b17b14dca33a938ab2bc13ae5830fd25795998ed4dea199a47"


def test_frozen_parameter_report_contract():
    report = json.loads(REPORT.read_text())
    assert report["status"] == "measured"
    assert report["source"]["recorded_rows"] == 960
    assert report["source"]["sha256"] == EXPECTED_SOURCE_SHA256
    assert report["cohorts"]["strict_period_recovery"]["row_count"] == 450
    assert report["cohorts"]["all_pipeline_candidates"]["row_count"] == 643
    assert report["method"]["bootstrap_replicates"] == 10000
    assert report["method"]["bootstrap_seed"] == 42
    assert report["uncertainty_coverage"]["status"] == (
        "not_evaluated_no_per_trial_intervals"
    )
