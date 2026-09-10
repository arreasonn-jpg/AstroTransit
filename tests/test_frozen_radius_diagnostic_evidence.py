"""Contracts for the frozen clean N=10 TLS-versus-MAP diagnostic."""

import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path("validation_runs/radius_diagnostics/tls_map_n10_v1")


def _load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def test_frozen_radius_diagnostic_provenance_and_artifacts() -> None:
    manifest = _load("manifest.json")
    report = _load("aggregate/radius_diagnostics.json")
    analysis = _load("analysis.json")

    assert manifest["campaign"] == "tls_map_n10_v1"
    assert manifest["source_commit"] == "eb413be452fb727402292873e3bc8248aa90508d"
    assert manifest["source_shard_count"] == 10
    assert manifest["aggregate_canonical_output_hash"] == (
        "469fc60c290ca33185ef62839314dd44cb408035210531c6ccd6b90666434c46"
    )
    assert _sha256(ROOT / "aggregate/radius_diagnostics.json") == (
        manifest["artifacts"]["aggregate/radius_diagnostics.json"]
    )
    assert _sha256(ROOT / "aggregate/radius_diagnostics.csv") == (
        manifest["artifacts"]["aggregate/radius_diagnostics.csv"]
    )
    assert report["summary"] == analysis["overall"]

    environment_paths = sorted(ROOT.glob("shards/TIC-*/environment/env_manifest.json"))
    assert len(environment_paths) == 10
    environments = [json.loads(path.read_text(encoding="utf-8")) for path in environment_paths]
    assert all(item["git"]["dirty"] is False for item in environments)
    assert {item["git"]["commit"] for item in environments} == {
        "eb413be452fb727402292873e3bc8248aa90508d"
    }


def test_exploratory_failure_mode_inventory_is_reproducible() -> None:
    report = _load("aggregate/radius_diagnostics.json")
    analysis = _load("analysis.json")
    rows = [row for row in report["rows"] if row["comparison_status"] == "evaluated"]
    assert len(rows) == 133

    delta = np.asarray([row["rp_rs_fractional_delta_vs_tls"] for row in rows])
    impact = np.asarray([row["impact_parameter"] for row in rows])
    u1 = np.asarray([row["limb_darkening_u1"] for row in rows])
    u2 = np.asarray([row["limb_darkening_u2"] for row in rows])
    ratio = np.asarray([row["fit_rp_rs"] / row["tls_rp_rs"] for row in rows])

    strata = analysis["exploratory_strata"]
    groups = [
        (impact < 0.5, strata["impact_parameter"]["b_lt_0_5"]),
        ((impact >= 0.5) & (impact < 0.85), strata["impact_parameter"]["b_0_5_to_0_85"]),
        (impact >= 0.85, strata["impact_parameter"]["b_ge_0_85"]),
    ]
    for mask, expected in groups:
        assert int(mask.sum()) == expected["n"]
        assert float(np.median(np.abs(delta[mask]))) == expected[
            "median_absolute_fractional_delta"
        ]

    physical = (u1 > 0) & ((u1 + u2) < 1) & ((u1 + 2 * u2) > 0)
    ld = strata["quadratic_limb_darkening"]
    assert int(physical.sum()) == ld["physical_region"]["n"]
    assert int((~physical).sum()) == ld["outside_physical_region"]["n"]
    assert np.isclose(ratio, 0.5, rtol=1e-5, atol=1e-8).sum() == 4
    assert np.isclose(ratio, 2.0, rtol=1e-5, atol=1e-8).sum() == 6
    assert int((np.abs(delta) > 0.25).sum()) == 20
    assert int((np.abs(delta) > 0.5).sum()) == 12
