"""astrotransit/outputs/writers.py OutputManager için testler."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from astrotransit.outputs.schemas import TransitCandidateRecord
from astrotransit.outputs.writers import OutputManager
from astrotransit.validation.followup import FollowupEvidence

# ═══════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════

@pytest.fixture
def tmp_output(tmp_path, monkeypatch):
    """OutputManager'ı geçici dizinde çalıştır."""
    settings = MagicMock()
    settings.general.output_dir = str(tmp_path / "outputs")
    settings.general.temp_dir = str(tmp_path / "temp")
    settings.quality.earth_similarity_profile = "photometric_earth_analog"
    return tmp_path


@pytest.fixture
def manager(tmp_output):
    import contextlib
    m = OutputManager(output_dir=str(tmp_output / "out"))
    yield m
    with contextlib.suppress(Exception):
        m.close()


def _min_candidate(target="TIC 123", sector=1):
    return SimpleNamespace(
        target_id=target, sector=sector,
        period=3.5, period_err=0.01, t0=100.0,
        rp_rs=0.1, depth=0.001, duration=0.1,
        confirmed=True, status="confirmed", snr=15.0,
        transit_times=np.array([100.0, 103.5]),
    )


def _fake_followup_confirmed():
    return FollowupEvidence(
        source="JWST",
        observation_type="jwst_transit",
        observation_ids=("obs1",),
        confirmed=True,
        mass_mearth=10.0,
        mass_err_mearth=1.0,
        false_positive_probability=0.02,
    )


# ═══════════════════════════════════════════════════════
# records + parquet_path + __enter__/__exit__
# ═══════════════════════════════════════════════════════

def test_records_property_empty(manager):
    assert manager.records == []


def test_parquet_path_exists(manager):
    assert manager.parquet_path is not None


def test_context_manager(tmp_output):
    with OutputManager(output_dir=str(tmp_output / "out")) as m:
        assert m is not None
    # close called → _closed True
    assert m._closed is True


# ═══════════════════════════════════════════════════════
# write()
# ═══════════════════════════════════════════════════════

def test_write_returns_record(manager):
    r = manager.write(_min_candidate())
    assert isinstance(r, TransitCandidateRecord)
    assert r.source_id == "TIC 123"


def test_write_appends_to_records(manager):
    manager.write(_min_candidate())
    manager.write(_min_candidate(target="TIC 456"))
    assert len(manager.records) == 2


def test_write_after_close_raises(tmp_output):
    m = OutputManager(output_dir=str(tmp_output / "out"))
    m.close()
    with pytest.raises(RuntimeError, match="Kapatılmış"):
        m.write(_min_candidate())


def test_write_with_followup(manager):
    r = manager.write(
        _min_candidate(),
        followup_result=_fake_followup_confirmed(),
    )
    assert r.followup_confirmed is True
    assert r.followup_status == "followup_confirmed"


# ═══════════════════════════════════════════════════════
# write_long_period()
# ═══════════════════════════════════════════════════════

def test_write_long_period_no_peak(manager):
    lp = SimpleNamespace(best=None)
    assert manager.write_long_period(lp) is None


def test_write_long_period_happy(manager):
    peak = SimpleNamespace(
        period=100.0, period_err=2.0, t0=1000.0, duration=0.1,
        depth=1e-3, transit_times=np.array([1000.0, 1100.0]),
        n_observed_transits=2, identifiability="multi_transit",
    )
    lp = SimpleNamespace(
        target_id="TIC 1", best=peak, coverage_baseline_days=200.0,
        observed_days=180.0, source_sectors=[1, 2], notes=[],
    )
    r = manager.write_long_period(lp)
    assert r is not None
    assert r.search_channel == "long_period"
    assert r.long_period_screening is True


def test_write_long_period_after_close_raises(tmp_output):
    m = OutputManager(output_dir=str(tmp_output / "out"))
    m.close()
    peak = SimpleNamespace(best=None)
    # önce None kontrolü yapılmadan closed kontrol edilir
    with pytest.raises(RuntimeError, match="Kapatılmış"):
        m.write_long_period(peak)


# ═══════════════════════════════════════════════════════
# append()
# ═══════════════════════════════════════════════════════

def test_append_valid_record(manager):
    rec = TransitCandidateRecord(source_id="TIC 999", sector=3)
    result = manager.append(rec)
    assert result is rec
    assert len(manager.records) == 1


def test_append_invalid_type_raises(manager):
    with pytest.raises(TypeError, match="TransitCandidateRecord"):
        manager.append({"not": "record"})


def test_append_after_close_raises(tmp_output):
    m = OutputManager(output_dir=str(tmp_output / "out"))
    m.close()
    rec = TransitCandidateRecord(source_id="X")
    with pytest.raises(RuntimeError, match="Kapatılmış"):
        m.append(rec)


# ═══════════════════════════════════════════════════════
# find_record()
# ═══════════════════════════════════════════════════════

def test_find_record_in_memory(manager):
    manager.write(_min_candidate(target="TIC 123", sector=1))
    found = manager.find_record("TIC 123", 1)
    assert found is not None
    assert found.source_id == "TIC 123"


def test_find_record_not_found(manager):
    assert manager.find_record("NONEXISTENT", 99) is None


def test_find_record_wrong_sector(manager):
    manager.write(_min_candidate(target="TIC 123", sector=1))
    assert manager.find_record("TIC 123", 2) is None


def test_find_record_from_parquet_rows(manager):
    # parquet_writer içine fake rows koy
    manager.parquet_writer._existing_rows = [
        {"source_id": "TIC 777", "sector": 5, "period": 4.0, "tic_id": 777}
    ]
    found = manager.find_record("TIC 777", 5)
    assert found is not None
    assert found.source_id == "TIC 777"


def test_find_record_bad_sector_in_row(manager):
    # sector string ve int'e çevrilebilir olmayan → atla
    manager.parquet_writer._existing_rows = [
        {"source_id": "TIC 1", "sector": "not-a-number"}
    ]
    assert manager.find_record("TIC 1", 1) is None


# ═══════════════════════════════════════════════════════
# update_followup()
# ═══════════════════════════════════════════════════════

def test_update_followup_valid(manager):
    rec = manager.write(_min_candidate())
    updated = manager.update_followup(rec, _fake_followup_confirmed())
    assert updated.followup_confirmed is True
    assert updated.planet_mass_mearth == 10.0
    assert updated.mass_status == "measured"
    assert updated.fpp_method == "followup_evidence_reported"


def test_update_followup_invalid_record_type(manager):
    with pytest.raises(TypeError, match="TransitCandidateRecord"):
        manager.update_followup("not-a-record", _fake_followup_confirmed())


def test_update_followup_after_close_raises(tmp_output):
    m = OutputManager(output_dir=str(tmp_output / "out"))
    rec = TransitCandidateRecord(source_id="X")
    m.close()
    with pytest.raises(RuntimeError, match="Kapatılmış"):
        m.update_followup(rec, _fake_followup_confirmed())


def test_update_followup_existing_mass(manager):
    rec = manager.write(_min_candidate())
    rec.planet_mass_mearth = 5.0  # zaten var
    updated = manager.update_followup(rec, _fake_followup_confirmed())
    # Yeni mass override edilmemeli (5.0 kalır)
    assert updated.planet_mass_mearth == 5.0
    assert updated.mass_status == "measured"


def test_update_followup_unconfirmed(manager):
    rec = manager.write(_min_candidate())
    unconfirmed = FollowupEvidence(
        source="TESS",
        observation_type="archive_validation",
        observation_ids=(),
        confirmed=False,
    )
    updated = manager.update_followup(rec, unconfirmed)
    assert updated.followup_confirmed is False


# ═══════════════════════════════════════════════════════
# flush() + close()
# ═══════════════════════════════════════════════════════

def test_flush_no_error(manager):
    manager.flush()  # raise etmemeli


def test_flush_after_close_no_error(tmp_output):
    m = OutputManager(output_dir=str(tmp_output / "out"))
    m.close()
    m.flush()  # no-op, raise etmemeli


def test_close_idempotent(tmp_output):
    m = OutputManager(output_dir=str(tmp_output / "out"))
    m.close()
    m.close()  # ikinci kez raise etmemeli
    assert m._closed is True


# ═══════════════════════════════════════════════════════
# export_csv()
# ═══════════════════════════════════════════════════════

def test_export_csv_while_open(manager):
    manager.write(_min_candidate())
    path = manager.export_csv()
    assert path is not None


def test_export_csv_after_close(tmp_output):
    m = OutputManager(output_dir=str(tmp_output / "out"))
    m.write(_min_candidate())
    m.close()
    path = m.export_csv()
    assert path is not None


def test_export_csv_custom_filename(manager):
    manager.write(_min_candidate())
    path = manager.export_csv(filename="custom.csv")
    assert "custom" in str(path)
