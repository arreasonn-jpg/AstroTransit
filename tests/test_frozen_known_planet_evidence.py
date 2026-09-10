"""Contracts for frozen N=1, N=5 and N=10 known-planet evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
N1 = ROOT / "validation_runs" / "v1_known_planets" / "determinism_n1_v1"
N5 = ROOT / "validation_runs" / "v1_known_planets" / "known_planets_5_v1"
N10 = ROOT / "validation_runs" / "v1_known_planets" / "known_planets_10_v1"
N10_SOURCE_COMMIT = "f68b24faa7b55a1938067875ff84aee200edb41d"


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


def test_n10_measured_metrics_remain_explicit() -> None:
    report = _load(N10 / "aggregate" / "benchmark.json")
    metrics = report["metrics"]
    assert report["metadata"]["aggregation_method"] == "deterministic_target_row_merge_v1"
    assert report["metadata"]["n_shards"] == 10
    assert metrics["n_targets"] == 10
    assert metrics["n_detected"] == 10
    assert metrics["n_correct"] == 5
    assert metrics["n_period_recovered"] == 7
    assert metrics["n_radius_recovered"] == 6
    assert metrics["n_sector_consistency_evaluated"] == 9
    assert metrics["sector_consistency_rate"] == 0.555556
    assert metrics["false_positive_rejection"] is None
    assert len(report["targets"]) == 10
    assert len({row["target_id"] for row in report["targets"]}) == 10
    assert report["provenance"]["source_shard_count"] == 10
    assert report["provenance"]["source_git_commits"] == [N10_SOURCE_COMMIT]
    assert len(report["provenance"]["source_output_hashes"]) == 10
    assert report["provenance"]["output_hash"] == (
        "cd96087d2ec78d5c32f5dbc40b83a4315dac0b67f1d39edc2fd4e90e842fe08e"
    )


def test_n10_manifest_matches_every_frozen_artifact() -> None:
    manifest = _load(N10 / "manifest.json")
    assert manifest["campaign"] == "known_planets_10_v1"
    assert manifest["scope"] == "ten_known_planets_sharded_real_tess_data"
    assert manifest["git_commit"] == N10_SOURCE_COMMIT
    assert manifest["random_seed"] == 42
    assert manifest["source_shard_count"] == 10
    assert len(manifest["target_ids"]) == 10
    assert len(manifest["shard_environment_hashes"]) == 10
    assert manifest["artifacts"]["aggregate/benchmark.json"] == (
        "d9fe187ff2e2ad04ffb218fb2f9a6e63e29a94475db5a8feeec39d6b26d710f3"
    )
    assert "manifest.json" not in manifest["artifacts"]
    for relative_path, expected_hash in manifest["artifacts"].items():
        artifact = N10 / relative_path
        assert artifact.is_file(), relative_path
        assert _sha256(artifact) == expected_hash, relative_path


def test_n10_all_shard_environments_were_clean_and_locked() -> None:
    paths = sorted(N10.glob("shards/TIC-*/environment/env_manifest.json"))
    assert len(paths) == 10
    lock_hashes = set()
    for path in paths:
        environment = _load(path)
        assert environment["git"]["dirty"] is False, path
        assert environment["git"]["commit"] == N10_SOURCE_COMMIT, path
        assert environment["python_version"] == "3.11.16", path
        assert environment["package"]["version"] == "0.3.0", path
        lock_hashes.add(environment["dependency_lock"]["sha256"])
    assert lock_hashes == {
        "d781e44e52132f8619925403282be3cf69d9945c2d571802d8ca2913b9f60e41"
    }
