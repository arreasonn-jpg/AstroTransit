"""L1 hedef havuzu (l1_target_pool) testleri."""

from __future__ import annotations

import json
from typing import ClassVar

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
    assert data["metadata"]["schema_version"] == "1.0"
    assert data["metadata"]["kind"] == "l1_target_pool"
    records = data["targets"]
    assert len(records) == 1
    assert records[0]["target_id"] == "TIC 100"
    assert records[0]["l1_assessed"] is True
    assert "l1_earth_twin" in records[0]
    assert "l1_structure" in records[0]
    assert records[0]["l1_claim_label"] is not None


def test_claim_label_inferred_for_eligible_row():
    builder = L1TargetPoolBuilder()
    entry = builder.build_from_row(_row())
    assert entry.l1_claim_label is not None
    assert entry.l1_claim_label in {
        "L1_REGION_ASSESSED",
        "L1_HABITABLE_REGION_CANDIDATE",
        "L1_STATIONKEEPING_REVIEW",
        "L1_CONTROLLED_STRUCTURE_CANDIDATE",
    }


def test_claim_label_none_when_not_assessed():
    builder = L1TargetPoolBuilder()
    entry = builder.build_from_row({"tic_id": "TIC 200"})
    assert entry.l1_claim_label is None


def test_outputs_layer_l1_pool_payload(tmp_path):
    from astrotransit.outputs.l1_pool import (
        L1_POOL_SCHEMA_VERSION,
        build_l1_pool_payload,
        write_l1_pool_json,
    )

    builder = L1TargetPoolBuilder()
    entries = builder.build_from_rows([_row(), _row(tic_id="TIC 2", host_in_habitable_zone=False)])
    payload = build_l1_pool_payload(entries, branch="both")
    assert payload["metadata"]["schema_version"] == L1_POOL_SCHEMA_VERSION
    assert len(payload["targets"]) == 2
    out = write_l1_pool_json(entries, tmp_path / "pool.json", branch="kol1")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["metadata"]["branch"] == "kol1"
    assert data["targets"][0]["l1_distance_from_star_au"] is not None


def test_mass_msun_and_mearth_conversions():
    builder = L1TargetPoolBuilder()
    entry = builder.build_from_row(_row(mass_msun=None, stellar_mass_msun=1.0, planet_mass_mearth=None, m_planet_mearth=1.0))
    assert entry.l1_assessed is True


class _FakeCatalogRow:
    colnames: ClassVar[list[str]] = ["ID", "mass", "lum", "Teff", "rad"]

    def __getitem__(self, key):
        return {"ID": 100, "mass": 1.0, "lum": 1.0, "Teff": 5778.0, "rad": 1.0}[key]


class _FakeCatalog(list):
    pass


class _FakeMASTClient:
    def __init__(self, catalog=None, error=None):
        self._catalog = catalog if catalog is not None else _FakeCatalog([_FakeCatalogRow()])
        self._error = error
        self.calls = 0

    def query_tic_catalog(self, tic_id=None, coordinates=None, radius="0.02 deg"):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._catalog


def test_query_mast_enriches_missing_fields():
    builder = L1TargetPoolBuilder(mast_client=_FakeMASTClient())
    row = _row(mass_msun=None, luminosity_lsun=None, teff_k=None, radius_rsun=None)
    entry = builder.build_from_row(row, query_mast=True)
    assert builder._mast_client.calls == 1
    assert entry.l1_assessed is True
    assert entry.l1_earth_twin["eligible"] is True


def test_query_mast_failure_keeps_row_unassessed():
    builder = L1TargetPoolBuilder(mast_client=_FakeMASTClient(error=RuntimeError("ag yok")))
    entry = builder.build_from_row({"tic_id": "TIC 100"}, query_mast=True)
    assert entry.l1_assessed is False
    assert entry.l1_distance_from_planet_au is None


def test_query_mast_not_called_when_disabled():
    client = _FakeMASTClient()
    builder = L1TargetPoolBuilder(mast_client=client)
    builder.build_from_row({"tic_id": "TIC 100"}, query_mast=False)
    assert client.calls == 0


def test_query_mast_keeps_existing_values():
    builder = L1TargetPoolBuilder(mast_client=_FakeMASTClient())
    row = _row(mass_msun=0.5, luminosity_lsun=0.25)
    entry = builder.build_from_row(row, query_mast=True)
    assert entry.l1_assessed is True
    # mevcut degerler MAST ile ezilmez; 0.5 msun ile L1 mesafesi degisir
    assert entry.l1_distance_from_planet_au is not None
