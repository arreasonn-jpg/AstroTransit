"""astrotransit/data/tess_client.py için kapsamlı testler.

Strateji:
- Gerçek lk.LightCurve nesneleri (lightkurve kurulu) ile temizleme ve
  dönüştürme yolları test edilir.
- Ağ erişimi (lk.search_lightcurve) mocklanır.
- Cache (TempCache) gerçek geçici dizinle çalıştırılır; bozuk cache
  senaryosu ayrıca test edilir.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

lk = pytest.importorskip("lightkurve")
import astropy.units as u  # noqa: E402

from astrotransit.data.tess_client import (  # noqa: E402
    TESSClient,
    TESSDataError,
    TESSLightCurveData,
    TESSMultiSectorData,
    TESSNoDataError,
    TESSQualityError,
)

# ────────────────────────── Yardımcılar ──────────────────────────

def _make_lc(n=200, sector=14, with_err=True, with_quality=True):
    """Deterministik, temiz bir LightCurve üret."""
    rng = np.random.default_rng(42)
    time = np.arange(n, dtype=float) + 1000.0
    flux = 1.0 + rng.normal(0, 1e-4, n)
    kwargs = {"time": time * u.day, "flux": flux}
    if with_err:
        kwargs["flux_err"] = np.full(n, 1e-4)
    lc = lk.LightCurve(**kwargs)
    lc.meta["SECTOR"] = sector
    lc.meta["CAMERA"] = 1
    lc.meta["TICID"] = 123456789
    if with_quality:
        # LightCurve quality attribute is auto-generated but meta may differ
        lc.meta["TEFF"] = 5700.0
    return lc


def _make_client(tmp_path, use_cache=True):
    return TESSClient(
        author="SPOC",
        exptime=120,
        quality_bitmask="default",
        cache_dir=tmp_path / "cache",
        cache_ttl_hours=24,
        use_cache=use_cache,
    )


# ═══════════════════════════════════════════════════════
# TESSLightCurveData
# ═══════════════════════════════════════════════════════

def _make_data_obj(n=100, sector=14):
    return TESSLightCurveData(
        target_id="TIC 123",
        sector=sector,
        time=np.arange(n, dtype=float) + 1000.0,
        flux=np.ones(n),
        flux_err=np.full(n, 1e-4),
        quality=np.zeros(n, dtype=np.int32),
        cadence=120.0,
        time_format="btjd",
        meta={"SECTOR": sector},
        n_points_raw=n + 10,
        n_points_clean=n,
    )


def test_lightcurve_data_duration_days():
    d = _make_data_obj(n=100)
    assert d.duration_days == pytest.approx(99.0)


def test_lightcurve_data_duration_days_short():
    d = _make_data_obj(n=1)
    assert d.duration_days == 0.0


def test_lightcurve_data_completeness():
    d = _make_data_obj(n=100)
    assert d.completeness == pytest.approx(100 / 110)


def test_lightcurve_data_completeness_zero_raw():
    d = _make_data_obj(n=0)
    d.n_points_raw = 0
    assert d.completeness == 0.0


def test_lightcurve_data_median_flux():
    d = _make_data_obj(n=10)
    assert d.median_flux == pytest.approx(1.0)


def test_lightcurve_data_median_flux_empty():
    d = _make_data_obj(n=0)
    assert d.median_flux == 0.0


def test_lightcurve_data_summary_keys():
    d = _make_data_obj()
    s = d.summary()
    assert s["target_id"] == "TIC 123"
    assert s["sector"] == 14
    assert "completeness" in s
    assert "median_flux" in s


# ═══════════════════════════════════════════════════════
# TESSMultiSectorData
# ═══════════════════════════════════════════════════════

def test_multisector_basics():
    m = TESSMultiSectorData(target_id="TIC 1")
    m.sectors.append(_make_data_obj(n=50, sector=1))
    m.sectors.append(_make_data_obj(n=30, sector=2))
    assert m.n_sectors == 2
    assert m.sector_numbers == [1, 2]
    assert m.total_points == 80
    assert m.total_duration_days == pytest.approx(49.0 + 29.0)


def test_multisector_empty_summary():
    m = TESSMultiSectorData(target_id="TIC 1")
    s = m.summary()
    assert s["n_sectors"] == 0
    assert s["sectors"] == []


# ═══════════════════════════════════════════════════════
# Hata sınıfları
# ═══════════════════════════════════════════════════════

def test_exception_hierarchy():
    assert issubclass(TESSNoDataError, TESSDataError)
    assert issubclass(TESSQualityError, TESSDataError)


# ═══════════════════════════════════════════════════════
# __init__
# ═══════════════════════════════════════════════════════

def test_client_init_with_cache(tmp_path):
    c = _make_client(tmp_path, use_cache=True)
    assert c._cache is not None
    assert c._mast is not None
    assert c.author == "SPOC"
    assert c.exptime == 120


def test_client_init_without_cache(tmp_path):
    c = _make_client(tmp_path, use_cache=False)
    assert c._cache is None


# ═══════════════════════════════════════════════════════
# _value_array
# ═══════════════════════════════════════════════════════

def test_value_array_from_ndarray():
    a = TESSClient._value_array(np.array([1, 2, 3]))
    assert isinstance(a, np.ndarray)
    assert list(a) == [1, 2, 3]


def test_value_array_from_quantity():
    q = np.array([1.0, 2.0]) * u.day
    a = TESSClient._value_array(q)
    assert list(a) == [1.0, 2.0]


# ═══════════════════════════════════════════════════════
# _row_value + _sector_from_row
# ═══════════════════════════════════════════════════════

def test_row_value_dict():
    row = {"sector": 14, "mission": "TESS Sector 14"}
    assert TESSClient._row_value(row, "sector") == 14
    assert TESSClient._row_value(row, "missing", "def") == "def"


def test_row_value_none():
    assert TESSClient._row_value(None, "x", 99) == 99


def test_sector_from_row_direct():
    assert TESSClient._sector_from_row({"sector": 14}) == 14
    assert TESSClient._sector_from_row({"sequence_number": "5"}) == 5


def test_sector_from_row_mission_string():
    row = {"mission": "TESS Sector 27"}
    assert TESSClient._sector_from_row(row) == 27


def test_sector_from_row_obs_id():
    # obs_id formatı: sector-XXX (regex "s" + rakamları hedefler)
    row = {"obs_id": "sector-0030-0000"}
    assert TESSClient._sector_from_row(row) == 30

    row2 = {"obs_id": "sector_27_x"}
    assert TESSClient._sector_from_row(row2) == 27

    # mission ve sector yoksa obs_id s adedi kontrol
    row3 = {"obs_id": "no-sector-here"}
    assert TESSClient._sector_from_row(row3) is None


def test_sector_from_row_missing():
    assert TESSClient._sector_from_row({"foo": "bar"}) is None


# ═══════════════════════════════════════════════════════
# _cache_identifier + _cache_path
# ═══════════════════════════════════════════════════════

def test_cache_identifier_contains_fields(tmp_path):
    c = _make_client(tmp_path)
    cid = c._cache_identifier("TIC 123", 14)
    assert "123" in cid
    assert "s14" in cid
    assert "SPOC" in cid
    assert "120" in cid


def test_cache_identifier_all_sectors(tmp_path):
    c = _make_client(tmp_path)
    cid = c._cache_identifier("TIC 123", None)
    assert "all" in cid


def test_cache_path_returns_none_without_cache(tmp_path):
    c = _make_client(tmp_path, use_cache=False)
    assert c._cache_path("x") is None


def test_cache_path_returns_path(tmp_path):
    c = _make_client(tmp_path)
    p = c._cache_path("something")
    assert p is not None
    assert p.suffix == ".npz"


# ═══════════════════════════════════════════════════════
# _clean_lightcurve
# ═══════════════════════════════════════════════════════

def test_clean_lightcurve_removes_nans(tmp_path):
    c = _make_client(tmp_path, use_cache=False)
    n = 50
    time = np.arange(n, dtype=float) + 1000.0
    flux = np.ones(n)
    flux[5] = np.nan
    lc = lk.LightCurve(time=time * u.day, flux=flux * u.dimensionless_unscaled)
    result = c._clean_lightcurve(lc)
    assert len(result.time) < n


def test_clean_lightcurve_removes_negative_flux(tmp_path):
    c = _make_client(tmp_path, use_cache=False)
    n = 30
    time = np.arange(n, dtype=float) + 1000.0
    flux = np.ones(n)
    flux[10] = -1.0
    lc = lk.LightCurve(time=time * u.day, flux=flux * u.dimensionless_unscaled)
    result = c._clean_lightcurve(lc)
    # en azından negatif akı ve NaN olanlar çıkarılmalı
    assert len(result.time) < n
    # hayatta kalanların hepsi pozitif olmalı
    assert np.all(np.asarray(result.flux) > 0)


def test_clean_lightcurve_skips_sigma_when_few_points(tmp_path):
    c = _make_client(tmp_path, use_cache=False)
    lc = _make_lc(n=5)
    result = c._clean_lightcurve(lc)
    assert len(result.time) == 5


# ═══════════════════════════════════════════════════════
# _to_data_object
# ═══════════════════════════════════════════════════════

def test_to_data_object_basic(tmp_path):
    c = _make_client(tmp_path, use_cache=False)
    lc = _make_lc(n=100, sector=14)
    data = c._to_data_object(lc, "TIC 123", n_raw=110)
    assert data.target_id == "TIC 123"
    assert data.sector == 14
    assert data.n_points_raw == 110
    assert data.n_points_clean == len(lc.time)
    assert data.meta.get("SECTOR") == 14


def test_to_data_object_no_flux_err(tmp_path):
    c = _make_client(tmp_path, use_cache=False)
    lc = _make_lc(n=50, with_err=False)
    data = c._to_data_object(lc, "TIC 123", n_raw=50)
    assert data.flux_err is not None
    assert len(data.flux_err) == len(data.time)


def test_to_data_object_no_quality(tmp_path):
    c = _make_client(tmp_path, use_cache=False)
    lc = _make_lc(n=50, with_quality=False)
    data = c._to_data_object(lc, "TIC 123", n_raw=50)
    assert data.quality is not None
    assert len(data.quality) == len(data.time)


# ═══════════════════════════════════════════════════════
# search
# ═══════════════════════════════════════════════════════

def test_search_no_lightkurve(tmp_path, monkeypatch):
    import astrotransit.data.tess_client as mod
    c = _make_client(tmp_path, use_cache=False)
    monkeypatch.setattr(mod, "lk", None)
    with pytest.raises(TESSDataError, match="Lightkurve"):
        c.search("TIC 123")


def test_search_returns_result(tmp_path):
    c = _make_client(tmp_path, use_cache=False)
    fake_result = MagicMock()
    fake_result.__len__ = MagicMock(return_value=3)
    with patch("astrotransit.data.tess_client.lk") as mock_lk:
        mock_lk.search_lightcurve.return_value = fake_result
        result = c.search("TIC 123", sector=14)
    assert result is fake_result
    mock_lk.search_lightcurve.assert_called_once()


def test_search_no_data_raises(tmp_path):
    c = _make_client(tmp_path, use_cache=False)
    empty = MagicMock()
    empty.__len__ = MagicMock(return_value=0)
    with patch("astrotransit.data.tess_client.lk") as mock_lk:
        mock_lk.search_lightcurve.return_value = empty
        with pytest.raises(TESSNoDataError):
            c.search("TIC 123")


def test_search_retries_then_fails(tmp_path, monkeypatch):
    c = _make_client(tmp_path, use_cache=False)
    # sleep'i sustur
    import time as _time
    monkeypatch.setattr(_time, "sleep", lambda *_: None)
    with patch("astrotransit.data.tess_client.lk") as mock_lk:
        mock_lk.search_lightcurve.side_effect = RuntimeError("network")
        with pytest.raises(TESSDataError, match="TESS araması başarısız"):
            c.search("TIC 123")
    assert mock_lk.search_lightcurve.call_count == 3


def test_search_int_target_normalized(tmp_path):
    c = _make_client(tmp_path, use_cache=False)
    fake_result = MagicMock()
    fake_result.__len__ = MagicMock(return_value=1)
    with patch("astrotransit.data.tess_client.lk") as mock_lk:
        mock_lk.search_lightcurve.return_value = fake_result
        c.search(123456789)
    call_args = mock_lk.search_lightcurve.call_args
    assert "TIC" in str(call_args[0][0])


# ═══════════════════════════════════════════════════════
# download_lightcurve
# ═══════════════════════════════════════════════════════

def test_download_invalid_index(tmp_path):
    c = _make_client(tmp_path, use_cache=False)
    fake = MagicMock()
    fake.__len__ = MagicMock(return_value=2)
    with pytest.raises(TESSDataError, match="geçersiz"):
        c.download_lightcurve(fake, index=5)


def test_download_success(tmp_path):
    c = _make_client(tmp_path, use_cache=False)
    lc = _make_lc(n=10)
    row = MagicMock()
    row.download.return_value = lc
    fake = MagicMock()
    fake.__len__ = MagicMock(return_value=1)
    fake.__getitem__ = MagicMock(return_value=row)
    result = c.download_lightcurve(fake, index=0)
    assert result is lc


def test_download_returns_none(tmp_path):
    c = _make_client(tmp_path, use_cache=False)
    row = MagicMock()
    row.download.return_value = None
    fake = MagicMock()
    fake.__len__ = MagicMock(return_value=1)
    fake.__getitem__ = MagicMock(return_value=row)
    with pytest.raises(TESSDataError, match="None"):
        c.download_lightcurve(fake, index=0)


def test_download_raises_wrapped(tmp_path):
    c = _make_client(tmp_path, use_cache=False)
    row = MagicMock()
    row.download.side_effect = RuntimeError("net")
    fake = MagicMock()
    fake.__len__ = MagicMock(return_value=1)
    fake.__getitem__ = MagicMock(return_value=row)
    with pytest.raises(TESSDataError, match="indirme başarısız"):
        c.download_lightcurve(fake, index=0)


# ═══════════════════════════════════════════════════════
# get_lightcurve — cache + akış
# ═══════════════════════════════════════════════════════

def test_get_lightcurve_cache_hit(tmp_path):
    c = _make_client(tmp_path, use_cache=True)
    existing = _make_data_obj(n=50, sector=14)
    with patch.object(c, "_load_cached_data", return_value=existing), \
         patch.object(c, "search") as mock_search:
        result = c.get_lightcurve("TIC 123", sector=14)
    assert result is existing
    mock_search.assert_not_called()


def test_get_lightcurve_full_flow(tmp_path):
    c = _make_client(tmp_path, use_cache=True)
    lc = _make_lc(n=200, sector=14)
    with patch.object(c, "_load_cached_data", return_value=None), \
         patch.object(c, "search") as mock_search, \
         patch.object(c, "download_lightcurve", return_value=lc):
        mock_search.return_value = MagicMock()
        result = c.get_lightcurve("TIC 123", sector=14)
    assert result.target_id == "TIC 123"
    assert result.sector == 14
    assert result.n_points_clean > 0


# ═══════════════════════════════════════════════════════
# get_available_sectors
# ═══════════════════════════════════════════════════════

def test_get_available_sectors_returns_list(tmp_path):
    c = _make_client(tmp_path, use_cache=False)
    rows = [
        {"sector": 14, "mission": "TESS"},
        {"sector": 15, "mission": "TESS"},
        {"sector": 14, "mission": "TESS"},  # dup
    ]
    fake_table = rows
    fake_result = MagicMock()
    fake_result.table = fake_table
    with patch.object(c, "search", return_value=fake_result):
        sectors = c.get_available_sectors("TIC 123")
    assert sectors == [14, 15]


def test_get_available_sectors_no_data(tmp_path):
    c = _make_client(tmp_path, use_cache=False)
    with patch.object(c, "search", side_effect=TESSNoDataError("yok")):
        assert c.get_available_sectors("TIC 123") == []


# ═══════════════════════════════════════════════════════
# get_all_sectors
# ═══════════════════════════════════════════════════════

def test_get_all_sectors_basic(tmp_path):
    c = _make_client(tmp_path, use_cache=True)
    lc = _make_lc(n=200, sector=14)
    fake_row = MagicMock()
    fake_row.colnames = ["sector"]
    fake_row.__getitem__ = MagicMock(return_value=14)
    fake_result = MagicMock()
    fake_result.__len__ = MagicMock(return_value=1)
    fake_result.table = [fake_row]

    with patch.object(c, "search", return_value=fake_result), \
         patch.object(c, "_load_cached_data", return_value=None), \
         patch.object(c, "download_lightcurve", return_value=lc):
        multi = c.get_all_sectors("TIC 123")
    assert multi.n_sectors == 1
    assert multi.sectors[0].sector == 14


def test_get_all_sectors_skips_low_data(tmp_path):
    c = _make_client(tmp_path, use_cache=True)
    # 50 noktalı lc -> minimum 100 altı, atlanmalı
    lc = _make_lc(n=50, sector=14)
    fake_row = MagicMock()
    fake_row.colnames = ["sector"]
    fake_row.__getitem__ = MagicMock(return_value=14)
    fake_result = MagicMock()
    fake_result.__len__ = MagicMock(return_value=1)
    fake_result.table = [fake_row]

    with patch.object(c, "search", return_value=fake_result), \
         patch.object(c, "_load_cached_data", return_value=None), \
         patch.object(c, "download_lightcurve", return_value=lc), pytest.raises(TESSNoDataError):
        c.get_all_sectors("TIC 123")


def test_get_all_sectors_continues_on_error(tmp_path):
    c = _make_client(tmp_path, use_cache=True)
    lc = _make_lc(n=200, sector=14)
    fake_row = MagicMock()
    fake_row.colnames = ["sector"]
    fake_row.__getitem__ = MagicMock(return_value=14)
    fake_result = MagicMock()
    fake_result.__len__ = MagicMock(return_value=2)
    fake_result.table = [fake_row, fake_row]

    calls = {"n": 0}

    def dl(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TESSDataError("boom")
        return lc

    with patch.object(c, "search", return_value=fake_result), \
         patch.object(c, "_load_cached_data", return_value=None), \
         patch.object(c, "download_lightcurve", side_effect=dl):
        multi = c.get_all_sectors("TIC 123")
    assert multi.n_sectors == 1


# ═══════════════════════════════════════════════════════
# Cache store/load
# ═══════════════════════════════════════════════════════

def test_store_and_load_cached_data(tmp_path):
    c = _make_client(tmp_path, use_cache=True)
    data = _make_data_obj(n=100, sector=14)
    cid = c._cache_identifier(data.target_id, data.sector)
    c._store_cached_data(cid, data)
    loaded = c._load_cached_data(cid)
    assert loaded is not None
    assert loaded.target_id == data.target_id
    assert loaded.sector == data.sector
    assert np.allclose(loaded.time, data.time)


def test_load_cached_data_invalidates_corrupt(tmp_path):
    c = _make_client(tmp_path, use_cache=True)
    cid = c._cache_identifier("TIC 123", 14)
    path = c._cache_path(cid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a valid npz file")
    loaded = c._load_cached_data(cid)
    # Bozuk kayıt okunamaz ve None döner; cache invalidation bildirilir
    assert loaded is None


def test_store_cached_data_no_cache(tmp_path):
    c = _make_client(tmp_path, use_cache=False)
    data = _make_data_obj()
    # No-op; exception fırlatmamalı
    c._store_cached_data("x", data)


def test_load_cached_data_no_cache(tmp_path):
    c = _make_client(tmp_path, use_cache=False)
    assert c._load_cached_data("x") is None
