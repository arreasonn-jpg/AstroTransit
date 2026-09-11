"""Contracts for frozen availability-aware N=50 evidence."""

import hashlib
import json
from pathlib import Path

ROOT = Path("validation_runs/v1_known_planets/known_planets_50_v1")
UNAVAILABLE = {"TIC 4610830", "TIC 8348911", "TIC 14570099", "TIC 17307715"}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_n50_availability_accounting_is_explicit() -> None:
    availability = _load(ROOT / "data_availability.json")
    assert availability["selected_target_count"] == 50
    assert availability["evaluated_target_count"] == 46
    assert availability["not_evaluated_target_count"] == 4
    assert {row["target_id"] for row in availability["not_evaluated"]} == UNAVAILABLE
    assert {row["reason"] for row in availability["not_evaluated"]} == {"no_measured_sector"}


def test_n50_measured_metrics_use_only_evaluable_targets() -> None:
    report = _load(ROOT / "aggregate/benchmark.json")
    metrics = report["metrics"]
    assert report["metadata"]["n_shards"] == 46
    assert metrics["n_targets"] == 46
    assert metrics["n_detected"] == 46
    assert metrics["n_correct"] == 21
    assert metrics["correct_recovery_rate"] == 0.456522
    assert metrics["n_period_recovered"] == 32
    assert metrics["period_recovery_rate"] == 0.695652
    assert metrics["n_radius_recovered"] == 23
    assert metrics["radius_recovery_rate"] == 0.5
    assert metrics["n_sector_consistency_evaluated"] == 38
    assert metrics["sector_consistency_rate"] == 0.526316
    assert metrics["false_positive_rejection"] is None
    assert len(report["targets"]) == 46
    assert report["provenance"]["output_hash"] == "6efcb7834f8e310744a76c7ffec0c8b46fc20622b49e7d9203a0c1d123e889d0"


def test_n50_manifest_covers_canonical_artifacts() -> None:
    manifest = _load(ROOT / "manifest.json")
    assert manifest["campaign"] == "known_planets_50_v1"
    assert manifest["scope"] == "fifty_selected_known_planets_real_tess_data_46_evaluated"
    assert manifest["input_hash"] == "c90de0ff053026f16781a8b8ffcc3e35088cae1385a2138a62e6f93afd54673a"
    assert manifest["selected_target_count"] == 50
    assert manifest["evaluated_target_count"] == 46
    assert manifest["not_evaluated_target_count"] == 4
    assert manifest["source_shard_count"] == 50
    assert set(manifest["source_git_commits"]) == {
        "7fa285925b68f486388c74695f1093900748a042",
        "25791b5fdc18759fe4096e8f8ba11564db522b52",
    }
    for relative in (
        "input/targets.json",
        "data_availability.json",
        "aggregate/benchmark.json",
        "aggregate/benchmark.manifest.json",
        "aggregate/targets.csv",
    ):
        assert manifest["artifacts"][relative] == _sha256(ROOT / relative)
