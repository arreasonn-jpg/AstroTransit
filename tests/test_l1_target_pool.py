"""L1 hedef havuzu (l1_target_pool) testleri."""

from __future__ import annotations

import json

from astrotransit.discovery.l1_target_pool import L1PoolEntry, L1TargetPoolBuilder


def _row(**overrides):
    row = {
        "tic_id": "TIC 100",
        "mass_msun": 1.0,
        "planet_mass_mearth": 1.0,
        "separation_au": 1.0,
        "luminosity_lsun": 1.0,
        "teff_k": 5778.0,
        "radius_rsun": 1.0,
        "host_in_habitable_zone": True,
        "candidate_radius_rearth": 1.0,
        "candidate_mass_mearth": 1.0,
        "candidate_equilibrium_temperature_k": 255.0,
        "timing_rms_min": 45.0,
        "transit_symmetry": 1.0,
        "residual_rms_ppm": 10.0,
        "pre_post_dip_score": 95.0,
        "shoulder_score": 90.0,
        "folded_multipeak_score": 85.0,
        "trojan_signal_score": 95.0,
        "n_transits": 10,
    }
    row.update(overrides)
    return row


def test_build_from_row_assessed():
    builder = L1TargetPoolBuilder()
    entry = builder.build_from_row(_row())
    assert isinstance(entry, L1PoolEntry)
    assert entry.target_id == "TIC 100"
    assert entry.l1_assessed is True
    assert entry.l1_distance_from_planet_au is not None
    assert entry.l1_distance_from_planet_au > 0.0
    assert entry.l1_stability_e_folding_days is not None
    assert entry.l1_earth_twin["eligible"] is True
    assert entry.l1_structure["controllable_candidate"] is True


def test_build_from_row_missing_masses_not_assessed():
    builder = L1TargetPoolBuilder()
    entry = builder.build_from_row({"tic_id": "TIC 200"})
    assert entry.l1_assessed is False
    assert entry.l1_distance_from_planet_au is None
    assert entry.l1_earth_twin["eligible"] is False
    assert entry.l1_structure["controllable_candidate"] is False
    data = entry.to_dict()
    assert data["l1_distance_from_planet_au"] is None
    assert data["l1_stability_e_folding_days"] is None


def test_build_from_rows_multiple():
    builder = L1TargetPoolBuilder()
    entries = builder.build_from_rows([_row(tic_id="TIC 1"), _row(tic_id="TIC 2", host_in_habitable_zone=False)])
    assert len(entries) == 2
    assert entries[0].l1_earth_twin["eligible"] is True
    assert entries[1].l1_earth_twin["eligible"] is False


def test_write_json_roundtrip(tmp_path):
    builder = L1TargetPoolBuilder()
    entries = builder.build_from_rows([_row()])
    out = builder.write_json(entries, tmp_path / "l1_pool.json")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["target_id"] == "TIC 100"
    assert data[0]["l1_assessed"] is True
    assert "l1_earth_twin" in data[0]
    assert "l1_structure" in data[0]


def test_mass_msun_and_mearth_conversions():
    builder = L1TargetPoolBuilder()
    entry = builder.build_from_row(_row(mass_msun=None, stellar_mass_msun=1.0, planet_mass_mearth=None, m_planet_mearth=1.0))
    assert entry.l1_assessed is True
