"""Contract for the frozen real-noise injection parameter evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPORT = Path(
    "validation_runs/v1_injection_recovery/real_noise_v1/parameter_recovery_report.json"
)
EXPECTED_SOURCE_SHA256 = "6dff856f848b89b17b14dca33a938ab2bc13ae5830fd25795998ed4dea199a47"
EXPECTED_REPORT_SHA256 = "65590270ee2d6a2f2e3a6e33db8895000694781c27fbf0d73230ce52728b7a38"


def test_frozen_parameter_report_contract():
    raw = REPORT.read_bytes()
    report = json.loads(raw)
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
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_REPORT_SHA256
