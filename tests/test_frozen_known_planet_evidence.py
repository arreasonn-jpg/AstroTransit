"""Contracts for frozen N=1 and N=5 known-planet evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
N1 = ROOT / "validation_runs" / "v1_known_planets" / "determinism_n1_v1"
N5 = ROOT / "validation_runs" / "v1_known_planets" / "known_planets_5_v1"


def _load(path: Path) -> dict:
    assert path.is_file(), f"Frozen evidence missing: {path.relative_to(ROOT)}"
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_n1_determinism_gate_is_frozen_pass() -> None:
    report = _load(N1 / "determinism.json")
    assert report["status"] == "PASS"
    assert report["differences"] == []
    assert report["json_equal"] is True
    assert report["csv_equal"] is True
    assert report["metrics_equal"] is True
    assert report["target_order_equal"] is True
    assert report["json_hash_a"] == report["json_hash_b"]
    assert report["csv_hash_a"] == report["csv_hash_b"]
    assert report["metrics_hash_a"] == report["metrics_hash_b"]


def test_n5_measured_metrics_remain_explicit() -> None:
    report = _load(N5 / "results" / "benchmark.json")
    metrics = report["metrics"]
    assert metrics["n_targets"] == 5
    assert metrics["n_detected"] == 5
    assert metrics["n_correct"] == 2
    assert metrics["n_period_recovered"] == 3
    assert metrics["n_radius_recovered"] == 3
    assert metrics["n_sector_consistency_evaluated"] == 4
    assert metrics["sector_consistency_rate"] == 0.25
    assert metrics["false_positive_rejection"] is None
    assert len(report["targets"]) == 5
    assert len({row["target_id"] for row in report["targets"]}) == 5


def test_n5_manifest_matches_frozen_artifacts() -> None:
    manifest = _load(N5 / "manifest.json")
    assert manifest["campaign"] == "known_planets_5_v1"
    assert manifest["random_seed"] == 42
    assert len(manifest["git_commit"]) == 40
    assert len(manifest["input_hash"]) == 64
    assert len(manifest["config_hash"]) == 64
    assert len(manifest["environment_manifest_hash"]) == 64
    assert len(manifest["target_ids"]) == 5
    for relative_path, expected_hash in manifest["artifacts"].items():
        artifact = N5 / relative_path
        assert artifact.is_file(), relative_path
        assert _sha256(artifact) == expected_hash, relative_path


def test_n5_environment_was_clean_and_versioned() -> None:
    environment = _load(N5 / "environment" / "env_manifest.json")
    assert environment["git"]["dirty"] is False
    assert environment["git"]["commit"] == "5987f798fdd36ef97eb61c4494482a6c2062a8cd"
    assert environment["python_version"] == "3.11.16"
    assert environment["package"]["version"] == "0.3.0"
