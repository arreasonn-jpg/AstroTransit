"""Contracts for the frozen N=10 physical-limb-darkening comparison."""

import json
from pathlib import Path

import pytest

ROOT = Path("validation_runs/radius_diagnostics")


def test_frozen_v2_comparison_contract() -> None:
    comparison = json.loads((ROOT / "tls_map_n10_v2/comparison_v1_v2.json").read_text())
    v1 = comparison["v1"]
    v2 = comparison["v2"]

    assert (v1["n_rows"], v1["n_evaluated"], v1["n_not_evaluated"]) == (153, 133, 20)
    assert (v2["n_rows"], v2["n_evaluated"], v2["n_not_evaluated"]) == (153, 133, 20)
    assert v1["median_absolute_fractional_delta"] == pytest.approx(0.070374826670434)
    assert v2["median_absolute_fractional_delta"] == pytest.approx(0.07214598487019892)
    assert v1["limb_darkening_outside_closed_physical_count"] == 29
    assert v2["limb_darkening_outside_closed_physical_count"] == 0
    assert v2["optimizer_boundary_row_count"] == 49
    assert v2["optimizer_boundary_hits"]["log_rp_rs:lower"] == 5
    assert v2["optimizer_boundary_hits"]["log_rp_rs:upper"] == 6


def test_frozen_v2_hash_contract() -> None:
    manifest = json.loads((ROOT / "tls_map_n10_v2/manifest.json").read_text())
    assert manifest["source_commit"] == "1eea9e933b6ad93f631373f6b82d95eec1f7e234"
    assert manifest["aggregate_canonical_output_hash"] == "50d989568527c0295e628990c8a79aa2766235c2d21ae64f9d79f0e980537519"
    assert manifest["artifacts"]["aggregate/radius_diagnostics.json"] == "b30523079171e80a4ecd8c12e6f7ac1f023c1e6ad4edb92ba2f511effbce07f8"
    assert manifest["artifacts"]["aggregate/radius_diagnostics.csv"] == "18c95fbfb9ef182207fbaf5fc629dd4782ac8c2f6f884133a2f37f405bfbb5b1"
