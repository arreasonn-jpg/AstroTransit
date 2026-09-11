"""Contracts for frozen N=50 parameter-recovery evidence."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path("validation_runs/v1_known_planets/known_planets_50_v1")
REPORT = ROOT / "parameter_recovery/report.json"
SOURCE = ROOT / "aggregate/targets.csv"
SCRIPT = Path("scripts/validation/analyze_parameter_recovery.py")
EXPECTED_HASH = "6b6c12a34d3c9f3443c6b107593331c781dad8da3e327f48a7dd8d83c6de9ddd"


def test_parameter_recovery_report_is_reproducible(tmp_path: Path) -> None:
    generated = tmp_path / "report.json"
    subprocess.run(
        [sys.executable, str(SCRIPT), "--source", str(SOURCE), "--output", str(generated)],
        check=True,
    )
    assert json.loads(generated.read_text()) == json.loads(REPORT.read_text())


def test_parameter_recovery_hash_and_claim_boundary() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["canonical_output_hash"] == EXPECTED_HASH
    value = report.pop("canonical_output_hash")
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    assert hashlib.sha256(canonical).hexdigest() == value
    assert report["selected_targets"] == 50
    assert report["evaluated_targets"] == 46
    assert report["not_evaluated_targets"] == 4
    assert report["coverage"] is None
    assert report["coverage_status"] == "not_evaluated_no_intervals"


def test_parameter_recovery_measured_values_are_frozen() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    all_rows = report["all_evaluable"]
    assert all_rows["n"] == 46
    assert all_rows["period"]["bias"] == 0.307939885819
    assert all_rows["period"]["rmse"] == 2.785270673876
    assert all_rows["period"]["mae"] == 1.301592301417
    assert all_rows["radius"]["bias"] == -0.976808413043
    assert all_rows["radius"]["rmse"] == 4.33126990354
    assert all_rows["radius"]["mae"] == 2.169259108696
    assert report["conditional_recovery"]["period"]["n"] == 32
    assert report["conditional_recovery"]["radius"]["n"] == 23
    assert report["by_difficulty"]["hard"]["period_within_tolerance"] == 6
    assert report["by_difficulty"]["hard"]["radius_within_tolerance"] == 2
