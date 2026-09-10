"""Deterministic benchmark rerun gate tests."""
from __future__ import annotations

import csv
import json

from astrotransit.validation.determinism import compare_benchmark_artifacts, output_hash
from astrotransit.validation.provenance import build_manifest, sha256_file


def _write_run(root, *, order=("TIC 1", "TIC 2"), recall=1.0, timestamp="a"):
    root.mkdir()
    payload = {
        "metadata": {"generated_at_utc": timestamp},
        "metrics": {"detection_recall": recall, "n_targets": 2},
        "targets": [{"target_id": target_id, "detected": True} for target_id in order],
        "provenance": {"run_timestamp_utc": timestamp, "output_hash": "volatile"},
    }
    json_path = root / "benchmark.json"
    csv_path = root / "targets.csv"
    json_path.write_text(json.dumps(payload), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["target_id", "detected"])
        writer.writeheader()
        for target_id in order:
            writer.writerow({"target_id": target_id, "detected": True})
    return json_path, csv_path


def test_rerun_gate_passes_when_only_timestamps_change(tmp_path):
    json_a, csv_a = _write_run(tmp_path / "a", timestamp="2026-01-01T00:00:00Z")
    json_b, csv_b = _write_run(tmp_path / "b", timestamp="2026-01-02T00:00:00Z")

    report = compare_benchmark_artifacts(json_a, csv_a, json_b, csv_b)

    assert report.passed
    assert report.to_dict()["status"] == "PASS"


def test_rerun_gate_reports_metric_difference(tmp_path):
    json_a, csv_a = _write_run(tmp_path / "a", recall=1.0)
    json_b, csv_b = _write_run(tmp_path / "b", recall=0.5)

    report = compare_benchmark_artifacts(json_a, csv_a, json_b, csv_b)

    assert not report.passed
    assert "metrics_mismatch" in report.differences
    assert "json_hash_mismatch" in report.differences


def test_rerun_gate_reports_target_order_difference(tmp_path):
    json_a, csv_a = _write_run(tmp_path / "a", order=("TIC 1", "TIC 2"))
    json_b, csv_b = _write_run(tmp_path / "b", order=("TIC 2", "TIC 1"))

    report = compare_benchmark_artifacts(json_a, csv_a, json_b, csv_b)

    assert not report.passed
    assert "target_order_mismatch" in report.differences


def test_output_hash_ignores_embedded_hash_and_timestamps():
    first = {"value": 1, "provenance": {"output_hash": "a", "run_timestamp_utc": "a"}}
    second = {"value": 1, "provenance": {"output_hash": "b", "run_timestamp_utc": "b"}}
    assert output_hash(first) == output_hash(second)


def test_manifest_captures_runtime_and_environment_hash(tmp_path):
    environment = tmp_path / "environment.json"
    environment.write_text('{"python":"3.11"}', encoding="utf-8")

    manifest = build_manifest(
        config={"seed": 42},
        seed=42,
        environment_manifest_path=environment,
        packages=("definitely-not-installed-astrotransit-test-package",),
    )

    assert manifest["python_version"]
    assert manifest["environment_manifest_hash"] == sha256_file(environment)
    assert manifest["package_versions"] == {
        "definitely-not-installed-astrotransit-test-package": None
    }
