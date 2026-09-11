"""Contracts for the frozen N=50 known-planet input corpus."""

import hashlib
import json
from pathlib import Path

ROOT = Path("validation_runs/v1_known_planets/known_planets_50_v1")


def test_known_planets_50_input_contract() -> None:
    targets = json.loads((ROOT / "input/targets.json").read_text())
    assert len(targets) == 50
    assert len({row["tic_id"] for row in targets}) == 50
    assert all(float(row["expected_period_days"]) > 0 for row in targets)
    assert all(float(row["expected_radius_rearth"]) > 0 for row in targets)
    assert all(row["reference"] for row in targets)
    assert all(row["reference_status"] in {"catalog_snapshot", "inherited_curated"} for row in targets)

    n10 = json.loads(Path("validation_runs/v1_known_planets/known_planets_10_v1/input/targets.json").read_text())
    assert [row["tic_id"] for row in targets[:10]] == [row["tic_id"] for row in n10]


def test_known_planets_50_manifest_contract() -> None:
    manifest = json.loads((ROOT / "corpus_manifest.json").read_text())
    payload = (ROOT / "input/targets.json").read_bytes()
    assert manifest["target_count"] == 50
    assert manifest["unique_tic_count"] == 50
    assert manifest["selected_corpus_sha256"] == hashlib.sha256(payload).hexdigest()
    assert manifest["selection_policy"] == "frozen_n10_then_registry_order_to_50_v1"
    assert manifest["selection_lineage_counts"] == {
        "frozen_n10_prefix": 10,
        "verified_registry_order": 40,
    }
    assert sum(manifest["difficulty_counts"].values()) == 50
    assert sum(manifest["reference_status_counts"].values()) == 50
