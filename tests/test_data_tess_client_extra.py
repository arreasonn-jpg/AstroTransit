"""tess_client.py ek coverage testleri (kalan satırlar için)."""
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
    TESSNoDataError,
)


def _client(tmp_path, use_cache=True):
    return TESSClient(
        author="SPOC", exptime=120, quality_bitmask="default",
        cache_dir=tmp_path / "cache", cache_ttl_hours=24,
        use_cache=use_cache,
    )


def _make_lc(n=50, sector=14, with_err=True, with_quality=True):
    rng = np.random.default_rng(0)
    time = np.arange(n, dtype=float) + 1000.0
    flux = 1.0 + rng.normal(0, 1e-4, n)
    kwargs = {"time": time * u.day, "flux": flux}
    if with_err:
        kwargs["flux_err"] = np.full(n, 1e-4)
    lc = lk.LightCurve(**kwargs)
    lc.meta["SECTOR"] = sector
    return lc


# ═══════════════════════════════════════════════════════
# search: retry başarı (296->317 dalı)
# ═══════════════════════════════════════════════════════

def test_search_retry_then_success(tmp_path, monkeypatch):
    """İlk deneme patlar, 2. başarılı → retry loop'un continue dalı."""
    import time as _time
    monkeypatch.setattr(_time, "sleep", lambda *_: None)
    c = _client(tmp_path, use_cache=False)

    fake_result = MagicMock()
    fake_result.__len__ = MagicMock(return_value=3)

    call_count = {"n": 0}

    def flaky(*a, **kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("net glitch")
        return fake_result

    with patch("astrotransit.data.tess_client.lk") as mock_lk:
        mock_lk.search_lightcurve.side_effect = flaky
        result = c.search("TIC 123")
    assert result is fake_result
    assert call_count["n"] == 2


# ═══════════════════════════════════════════════════════
# _to_data_object: flux_err / quality fallback (483-484, 488)
# ═══════════════════════════════════════════════════════

def test_to_data_object_no_flux_err_branch(tmp_path):
    """flux_err yok → fallback (483-484)."""
    c = _client(tmp_path, use_cache=False)
    lc = _make_lc(n=50, with_err=False)
    data = c._to_data_object(lc, "TIC 1", n_raw=50)
    assert data.flux_err is not None
    assert len(data.flux_err) == 50


def test_to_data_object_no_quality_branch(tmp_path):
    """lc.quality yok/None → zeros (488)."""
    c = _client(tmp_path, use_cache=False)
    import contextlib
    lc = _make_lc(n=50)
    # quality attribute'unu zorla sil
    with contextlib.suppress(AttributeError):
        del lc.quality
    data = c._to_data_object(lc, "TIC 1", n_raw=50)
    assert data.quality is not None


# ═══════════════════════════════════════════════════════
# _to_data_object: meta .item() (501)
# ═══════════════════════════════════════════════════════

def test_to_data_object_meta_item_conversion(tmp_path):
    """numpy scalar meta değeri .item() ile Python tipine çevrilir (501)."""
    c = _client(tmp_path, use_cache=False)
    lc = _make_lc(n=50)
    lc.meta["SECTOR"] = np.int64(14)
    lc.meta["TEFF"] = np.float64(5778.0)
    data = c._to_data_object(lc, "TIC 1", n_raw=50)
    assert isinstance(data.meta.get("SECTOR"), int)
    assert isinstance(data.meta.get("TEFF"), float)


# ═══════════════════════════════════════════════════════
# _row_value: astropy Row / fallback (543->547, 549-552)
# ═══════════════════════════════════════════════════════

class _FakeRow:
    """astropy Row benzeri: colnames + __getitem__."""
    def __init__(self, cols):
        self.colnames = list(cols)
        self._data = cols
    def __getitem__(self, key):
        if key in self._data:
            return self._data[key]
        raise KeyError(key)


def test_row_value_astropy_like():
    row = _FakeRow({"sector": 14})
    assert TESSClient._row_value(row, "sector") == 14


def test_row_value_astropy_missing_key():
    row = _FakeRow({"sector": 14})
    assert TESSClient._row_value(row, "missing", "d") == "d"


def test_row_value_dict_missing_key():
    assert TESSClient._row_value({"a": 1}, "b", 99) == 99


def test_row_value_object_index_fail():
    """colnames'te yok ama __getitem__ IndexError fırlatır → fallback."""
    from typing import ClassVar
    class _Bad:
        colnames: ClassVar[list] = ["y"]  # name 'x' değil, astropy check False
        def __getitem__(self, k):
            raise IndexError("no")
    assert TESSClient._row_value(_Bad(), "x", "default") == "default"


# ═══════════════════════════════════════════════════════
# _sector_from_row: int conversion fail (563-564)
# ═══════════════════════════════════════════════════════

def test_sector_from_row_int_fail():
    """sector değeri int'e çevrilemez → fallback None."""
    row = {"sector": "not-a-number"}
    assert TESSClient._sector_from_row(row) is None


def test_sector_from_row_sequence_fallback():
    """sector yoksa sequence_number dener."""
    assert TESSClient._sector_from_row({"sequence_number": "5"}) == 5


# ═══════════════════════════════════════════════════════
# _load_cached_data: corrupt cache (602-613)
# ═══════════════════════════════════════════════════════

def test_load_cached_data_corrupt_file(tmp_path):
    """Bozuk npz → exception handling dalı."""
    c = _client(tmp_path, use_cache=True)
    cid = c._cache_identifier("TIC 1", 14)
    path = c._cache_path(cid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a valid npz file")
    loaded = c._load_cached_data(cid)
    assert loaded is None


def test_load_cached_data_missing_meta_json(tmp_path):
    """npz var ama 'meta_json' anahtarı yok → KeyError dalı."""
    c = _client(tmp_path, use_cache=True)
    cid = c._cache_identifier("TIC 1", 14)
    path = c._cache_path(cid)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, time=np.arange(10), flux=np.ones(10))
    loaded = c._load_cached_data(cid)
    assert loaded is None


# ═══════════════════════════════════════════════════════
# _store_cached_data: path None (622)
# ═══════════════════════════════════════════════════════

def test_store_cached_data_no_cache_returns_early(tmp_path):
    """use_cache=False → _cache None → early return (622)."""
    c = _client(tmp_path, use_cache=False)
    data = TESSLightCurveData(
        target_id="TIC 1", sector=14,
        time=np.arange(10, dtype=float),
        flux=np.ones(10), flux_err=np.full(10, 1e-4),
        quality=np.zeros(10, dtype=np.int32),
        cadence=120.0, time_format="btjd", meta={},
        n_points_raw=10, n_points_clean=10,
    )
    # raise etmemeli
    c._store_cached_data("x", data)


# ═══════════════════════════════════════════════════════
# _store_cached_data: exception (645-648)
# ═══════════════════════════════════════════════════════

def test_store_cached_data_oserror(tmp_path, monkeypatch):
    """np.savez_compressed patlarsa warning + suppress (645-648)."""
    c = _client(tmp_path, use_cache=True)
    data = TESSLightCurveData(
        target_id="TIC 1", sector=14,
        time=np.arange(10, dtype=float),
        flux=np.ones(10), flux_err=np.full(10, 1e-4),
        quality=np.zeros(10, dtype=np.int32),
        cadence=120.0, time_format="btjd", meta={},
        n_points_raw=10, n_points_clean=10,
    )
    with patch("numpy.savez_compressed", side_effect=OSError("disk full")):
        # raise etmemeli, sadece warning
        c._store_cached_data("x", data)


# ═══════════════════════════════════════════════════════
# get_lightcurve: actual_cache_id != cache_id (728)
# ═══════════════════════════════════════════════════════

def test_get_lightcurve_actual_cache_id_differs(tmp_path):
    """Sektör belirsizken data.sector farklı çıkarsa ikinci cache yazılır."""
    c = _client(tmp_path, use_cache=True)
    lc = _make_lc(n=200, sector=15)  # lc.meta.SECTOR=15

    # search None dönsün (sector parametresi None olacak → cache_id "all")
    with patch.object(c, "_load_cached_data", return_value=None), \
         patch.object(c, "search") as mock_search, \
         patch.object(c, "download_lightcurve", return_value=lc):
        mock_search.return_value = MagicMock()
        # sector=None → cache_id "s15" değil "all"
        result = c.get_lightcurve("TIC 1", sector=None)
    # Gerçek sector 15 olduğu için actual_cache_id != cache_id olmalı
    assert result.sector == 15


# ═══════════════════════════════════════════════════════
# get_all_sectors: table None / IndexError (781->786, 783-784)
# ═══════════════════════════════════════════════════════

def test_get_all_sectors_table_none(tmp_path):
    """search_result.table=None → row None döner, sector atlanır."""
    c = _client(tmp_path, use_cache=False)
    fake_result = MagicMock()
    fake_result.__len__ = MagicMock(return_value=1)
    fake_result.table = None

    with patch.object(c, "search", return_value=fake_result), \
         patch.object(c, "_load_cached_data", return_value=None), pytest.raises(TESSNoDataError):
        c.get_all_sectors("TIC 1")


def test_get_all_sectors_index_error(tmp_path):
    """table[i] IndexError → row None."""
    c = _client(tmp_path, use_cache=False)
    fake_result = MagicMock()
    fake_result.__len__ = MagicMock(return_value=1)

    class _BadTable:
        def __getitem__(self, i):
            raise IndexError("out of range")
    fake_result.table = _BadTable()

    with patch.object(c, "search", return_value=fake_result), \
         patch.object(c, "_load_cached_data", return_value=None), pytest.raises(TESSNoDataError):
        c.get_all_sectors("TIC 1")


# ═══════════════════════════════════════════════════════
# get_all_sectors: cache hit (800->821)
# ═══════════════════════════════════════════════════════

def test_get_all_sectors_uses_cached_data(tmp_path):
    """Cache hit → download çağrılmaz (800->821 dalı)."""
    c = _client(tmp_path, use_cache=True)

    cached_data = TESSLightCurveData(
        target_id="TIC 1", sector=14,
        time=np.arange(200, dtype=float),
        flux=np.ones(200), flux_err=np.full(200, 1e-4),
        quality=np.zeros(200, dtype=np.int32),
        cadence=120.0, time_format="btjd", meta={"SECTOR": 14},
        n_points_raw=200, n_points_clean=200,
    )

    fake_row = MagicMock()
    fake_row.colnames = ["sector"]
    fake_row.__getitem__ = MagicMock(return_value=14)
    fake_result = MagicMock()
    fake_result.__len__ = MagicMock(return_value=1)
    fake_result.table = [fake_row]

    with patch.object(c, "search", return_value=fake_result), \
         patch.object(c, "_load_cached_data", return_value=cached_data), \
         patch.object(c, "download_lightcurve") as mock_dl:
        multi = c.get_all_sectors("TIC 1")
    assert multi.n_sectors == 1
    mock_dl.assert_not_called()


# ═══════════════════════════════════════════════════════
# get_all_sectors: unexpected exception (838-840)
# ═══════════════════════════════════════════════════════

def test_get_all_sectors_unexpected_error(tmp_path):
    """Beklenmeyen exception logger.error dalı (838-840)."""
    c = _client(tmp_path, use_cache=False)
    fake_row = MagicMock()
    fake_row.colnames = ["sector"]
    fake_row.__getitem__ = MagicMock(return_value=14)
    fake_result = MagicMock()
    fake_result.__len__ = MagicMock(return_value=1)
    fake_result.table = [fake_row]

    with patch.object(c, "search", return_value=fake_result), \
         patch.object(c, "_load_cached_data", return_value=None), \
         patch.object(c, "download_lightcurve",
                      side_effect=ValueError("unexpected")), pytest.raises(TESSNoDataError):
        c.get_all_sectors("TIC 1")


# ═══════════════════════════════════════════════════════
# get_available_sectors: empty table (880->878)
# ═══════════════════════════════════════════════════════

def test_get_available_sectors_empty_table(tmp_path):
    """table boş → 880->878 loop skip."""
    c = _client(tmp_path, use_cache=False)
    fake_result = MagicMock()
    fake_result.table = []
    with patch.object(c, "search", return_value=fake_result):
        sectors = c.get_available_sectors("TIC 1")
    assert sectors == []


# ═══════════════════════════════════════════════════════
# _clean_lightcurve: <10 points sigma clip skip (413->415)
# ═══════════════════════════════════════════════════════

def test_clean_lightcurve_few_points_no_sigma_clip(tmp_path):
    """<10 nokta → sigma kırpma atlanır (413->415)."""
    c = _client(tmp_path, use_cache=False)
    lc = _make_lc(n=5)
    out = c._clean_lightcurve(lc)
    assert len(out.time) == 5


# ═══════════════════════════════════════════════════════
# search retry: 3. deneme de patlar (296->317 tam)
# ═══════════════════════════════════════════════════════

def test_search_all_retries_fail(tmp_path, monkeypatch):
    """Üç deneme de patlar → TESSDataError."""
    import time as _time
    monkeypatch.setattr(_time, "sleep", lambda *_: None)
    c = _client(tmp_path, use_cache=False)
    with patch("astrotransit.data.tess_client.lk") as mock_lk:
        mock_lk.search_lightcurve.side_effect = RuntimeError("persistent")
        with pytest.raises(TESSDataError, match="başarısız"):
            c.search("TIC 1")
    assert mock_lk.search_lightcurve.call_count == 3
