"""astrotransit/detection/long_period.py için testler.

BoxLeastSquares ve DetrendedLightCurve mocklanır.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import astropy.units as u
import numpy as np
import pytest

from astrotransit.detection.long_period import (
    LongPeriodPeak,
    LongPeriodResult,
    LongPeriodSearchConfig,
    LongPeriodTransitSearch,
)

# ═══════════════════════════════════════════════════════
# LongPeriodSearchConfig
# ═══════════════════════════════════════════════════════

def test_config_defaults():
    c = LongPeriodSearchConfig()
    assert c.min_period_days == 20.0
    assert c.max_period_days == 500.0
    c.validate()


def test_config_validate_bad_period_range():
    with pytest.raises(ValueError, match="periyot aralığı"):
        LongPeriodSearchConfig(min_period_days=100, max_period_days=50).validate()


def test_config_validate_bad_power():
    with pytest.raises(ValueError, match="güç/derinlik"):
        LongPeriodSearchConfig(min_power=0).validate()


def test_config_validate_bad_depth():
    with pytest.raises(ValueError, match="güç/derinlik"):
        LongPeriodSearchConfig(min_depth=0.5, max_depth=0.1).validate()


def test_config_validate_min_points():
    with pytest.raises(ValueError, match="min_points_per_transit"):
        LongPeriodSearchConfig(min_points_per_transit=0).validate()


def test_config_validate_bad_durations_or_peaks():
    with pytest.raises(ValueError, match="n_durations ve n_peaks"):
        LongPeriodSearchConfig(n_durations=0).validate()
    with pytest.raises(ValueError, match="n_durations ve n_peaks"):
        LongPeriodSearchConfig(n_peaks=0).validate()


def test_config_from_settings():
    fake_cfg = SimpleNamespace(
        min_period_days=15.0, max_period_days=400.0, min_power=6.0,
        min_depth=1e-5, max_depth=0.4, min_points_per_transit=4,
        n_durations=6, n_peaks=3,
    )
    fake_settings = SimpleNamespace(detection=SimpleNamespace(long_period=fake_cfg))
    c = LongPeriodSearchConfig.from_settings(fake_settings)
    assert c.min_period_days == 15.0
    assert c.n_peaks == 3


# ═══════════════════════════════════════════════════════
# LongPeriodPeak
# ═══════════════════════════════════════════════════════

def _peak(**kw):
    base = dict(
        period=100.0, period_err=2.0, duration=0.1, depth=1e-3,
        depth_err=1e-4, t0=1000.0, power=15.0, snr=15.0,
        n_observed_transits=2, n_expected_transits=2,
        n_transit_points=10, transit_times=np.array([1000.0, 1100.0]),
        identifiability="multi_transit",
    )
    base.update(kw)
    return LongPeriodPeak(**base)


def test_peak_is_single_transit():
    assert _peak(n_observed_transits=1).is_single_transit is True
    assert _peak(n_observed_transits=2).is_single_transit is False


def test_peak_to_dict():
    d = _peak().to_dict()
    assert d["period_days"] == 100.0
    assert d["duration_hours"] == pytest.approx(2.4)
    assert d["depth_ppm"] == 1000.0
    assert d["n_observed_transits"] == 2
    assert len(d["transit_times"]) == 2


# ═══════════════════════════════════════════════════════
# LongPeriodResult
# ═══════════════════════════════════════════════════════

def _empty_result():
    return LongPeriodResult(
        target_id="T", source_sectors=(1,),
        coverage_baseline_days=100.0, observed_days=80.0,
        best=None, all_peaks=[],
        periods_searched=np.array([]), power_array=np.array([]),
        has_candidate=False,
    )


def test_result_n_observed_no_best():
    assert _empty_result().n_observed_transits == 0


def test_result_identifiability_no_best():
    assert _empty_result().identifiability == "none"


def test_result_n_observed_with_best():
    r = _empty_result()
    r.best = _peak(n_observed_transits=3)
    assert r.n_observed_transits == 3


def test_result_identifiability_with_best():
    r = _empty_result()
    r.best = _peak(identifiability="single_transit_ambiguous")
    assert r.identifiability == "single_transit_ambiguous"


def test_result_summary_no_best():
    s = _empty_result().summary()
    assert s["has_candidate"] is False
    assert "best_peak" not in s


def test_result_summary_with_best():
    r = _empty_result()
    r.best = _peak()
    s = r.summary()
    assert s["has_candidate"] is False  # has_candidate field
    assert "best_peak" in s


# ═══════════════════════════════════════════════════════
# LongPeriodTransitSearch.__init__
# ═══════════════════════════════════════════════════════

def test_search_init_default():
    s = LongPeriodTransitSearch()
    assert s.stellar_radius_rsun == 1.0
    assert s.stellar_mass_msun == 1.0


def test_search_init_custom_stellar():
    s = LongPeriodTransitSearch(stellar_radius_rsun=1.5, stellar_mass_msun=1.2)
    assert s.stellar_radius_rsun == 1.5
    assert s.stellar_mass_msun == 1.2


def test_search_init_zero_stellar_falls_back():
    s = LongPeriodTransitSearch(stellar_radius_rsun=0.0, stellar_mass_msun=-1.0)
    assert s.stellar_radius_rsun == 1.0
    assert s.stellar_mass_msun == 1.0


def test_search_init_invalid_config_raises():
    with pytest.raises(ValueError):
        LongPeriodTransitSearch(
            config=LongPeriodSearchConfig(min_period_days=-1)
        )


# ═══════════════════════════════════════════════════════
# _clean_arrays
# ═══════════════════════════════════════════════════════

def _make_lc(n=500, start=1000.0, end=1300.0, sector=1, meta=None):
    t = np.linspace(start, end, n)
    flux = 1.0 + np.random.default_rng(0).normal(0, 1e-4, n)
    err = np.full(n, 1e-4)
    return SimpleNamespace(
        target_id="TIC 1", sector=sector,
        time=t, flux=flux, flux_err=err,
        meta=meta or {},
    )


def test_clean_arrays_ok():
    s = LongPeriodTransitSearch()
    lc = _make_lc(n=100)
    t, _f, _e = s._clean_arrays(lc)
    assert t.size == 100
    assert np.all(np.diff(t) >= 0)  # sorted


def test_clean_arrays_mismatched_lengths():
    s = LongPeriodTransitSearch()
    lc = SimpleNamespace(
        time=np.array([1.0, 2.0]), flux=np.array([1.0]),
        flux_err=np.array([1e-4, 1e-4]),
    )
    with pytest.raises(ValueError, match="uzunlukları eşit"):
        s._clean_arrays(lc)


def test_clean_arrays_no_valid_data():
    s = LongPeriodTransitSearch()
    lc = SimpleNamespace(
        time=np.array([np.nan, np.nan]),
        flux=np.array([np.nan, np.nan]),
        flux_err=np.array([np.nan, np.nan]),
    )
    with pytest.raises(ValueError, match="geçerli veri yok"):
        s._clean_arrays(lc)


def test_clean_arrays_filters_nonfinite_and_neg_error():
    s = LongPeriodTransitSearch()
    lc = SimpleNamespace(
        time=np.array([1.0, 2.0, 3.0, 4.0]),
        flux=np.array([1.0, np.nan, 1.0, 1.0]),
        flux_err=np.array([1e-4, 1e-4, -1e-4, 1e-4]),
    )
    t, _f, _e = s._clean_arrays(lc)
    assert t.size == 2  # sadece index 0 ve 3


def test_clean_arrays_sorts():
    s = LongPeriodTransitSearch()
    lc = SimpleNamespace(
        time=np.array([3.0, 1.0, 2.0]),
        flux=np.array([1.0, 1.0, 1.0]),
        flux_err=np.array([1e-4, 1e-4, 1e-4]),
    )
    t, _, _ = s._clean_arrays(lc)
    assert list(t) == [1.0, 2.0, 3.0]


# ═══════════════════════════════════════════════════════
# _central_duration_days / _duration_grid
# ═══════════════════════════════════════════════════════

def test_central_duration_positive():
    s = LongPeriodTransitSearch()
    d = s._central_duration_days(100.0)
    assert d > 0


def test_central_duration_scales_with_period():
    s = LongPeriodTransitSearch()
    d1 = s._central_duration_days(50.0)
    d2 = s._central_duration_days(500.0)
    # P^(2/3) scaling
    assert d2 > d1


def test_duration_grid_valid():
    s = LongPeriodTransitSearch()
    d = s._duration_grid()
    assert d.size == s.config.n_durations
    assert np.all(d > 0)
    assert np.all(np.diff(d) > 0)


# ═══════════════════════════════════════════════════════
# _select_best
# ═══════════════════════════════════════════════════════

def test_select_best_empty():
    assert LongPeriodTransitSearch._select_best([]) is None


def test_select_best_prefers_multi_transit():
    multi = _peak(identifiability="multi_transit", power=10.0)
    single = _peak(identifiability="single_transit_ambiguous", power=20.0)
    best = LongPeriodTransitSearch._select_best([single, multi])
    assert best is multi


def test_select_best_power_tiebreak():
    a = _peak(identifiability="multi_transit", power=10.0)
    b = _peak(identifiability="multi_transit", power=20.0)
    best = LongPeriodTransitSearch._select_best([a, b])
    assert best is b


def test_select_best_unknown_identifiability():
    a = _peak(identifiability="weird", power=5.0)
    best = LongPeriodTransitSearch._select_best([a])
    assert best is a


# ═══════════════════════════════════════════════════════
# _observed_events
# ═══════════════════════════════════════════════════════

def test_observed_events_invalid_period():
    s = LongPeriodTransitSearch()
    t = np.linspace(1000, 1100, 100)
    assert s._observed_events(t, 1000.0, 0.0, 0.1) == ([], 0, 0)
    assert s._observed_events(t, 1000.0, 10.0, 0.0) == ([], 0, 0)


def test_observed_events_detects_transits():
    s = LongPeriodTransitSearch()
    # 100 günlük baseline, 30 gün periyot → ~3-4 transit
    t = np.linspace(1000, 1100, 1000)
    centers, n_pts, n_expected = s._observed_events(t, 1000.0, 30.0, 1.0)
    assert len(centers) >= 2
    assert n_pts > 0
    assert n_expected >= 3


def test_observed_events_no_points_in_duration():
    s = LongPeriodTransitSearch()
    # Dar aralık, transit merkezlerinde nokta yok
    t = np.linspace(1000, 1100, 10)
    centers, _, _ = s._observed_events(t, 1000.0, 1000.0, 0.001)
    # min_points_per_transit default 3, transit başına ~0 nokta
    assert all(isinstance(c, float) for c in centers)


# ═══════════════════════════════════════════════════════
# _evaluate_threshold
# ═══════════════════════════════════════════════════════

def test_evaluate_threshold_pass():
    s = LongPeriodTransitSearch()
    p = _peak(power=15.0, depth=1e-3, n_observed_transits=2)
    s._evaluate_threshold(p)
    assert p.passed_threshold is True
    assert p.reject_reason == ""


def test_evaluate_threshold_low_power():
    s = LongPeriodTransitSearch()
    p = _peak(power=1.0)
    s._evaluate_threshold(p)
    assert p.passed_threshold is False
    assert "power" in p.reject_reason


def test_evaluate_threshold_low_depth():
    s = LongPeriodTransitSearch()
    p = _peak(depth=1e-10)
    s._evaluate_threshold(p)
    assert p.passed_threshold is False
    assert "depth" in p.reject_reason


def test_evaluate_threshold_high_depth():
    s = LongPeriodTransitSearch()
    p = _peak(depth=0.9)
    s._evaluate_threshold(p)
    assert p.passed_threshold is False


def test_evaluate_threshold_no_transits():
    s = LongPeriodTransitSearch()
    p = _peak(n_observed_transits=0)
    s._evaluate_threshold(p)
    assert p.passed_threshold is False
    assert "transit" in p.reject_reason


def test_evaluate_threshold_nonfinite_power():
    s = LongPeriodTransitSearch()
    p = _peak(power=float("nan"))
    s._evaluate_threshold(p)
    assert p.passed_threshold is False


# ═══════════════════════════════════════════════════════
# _source_sectors
# ═══════════════════════════════════════════════════════

def test_source_sectors_from_meta():
    s = LongPeriodTransitSearch()
    lc = SimpleNamespace(meta={"source_sectors": [1, 2, 3]}, sector=1)
    assert s._source_sectors(lc) == (1, 2, 3)


def test_source_sectors_fallback_to_sector():
    s = LongPeriodTransitSearch()
    lc = SimpleNamespace(meta={}, sector=14)
    assert s._source_sectors(lc) == (14,)


# ═══════════════════════════════════════════════════════
# search() — erken çıkışlar
# ═══════════════════════════════════════════════════════

def test_search_insufficient_points():
    s = LongPeriodTransitSearch()
    lc = _make_lc(n=5)
    r = s.search(lc)
    assert r.has_candidate is False
    assert any("yetersiz" in n for n in r.notes)


def test_search_zero_baseline():
    s = LongPeriodTransitSearch()
    lc = SimpleNamespace(
        target_id="T", sector=1,
        time=np.full(30, 1000.0), flux=np.ones(30),
        flux_err=np.full(30, 1e-4), meta={},
    )
    r = s.search(lc)
    assert r.has_candidate is False
    assert any("taban" in n or "geçersiz" in n for n in r.notes)


# ═══════════════════════════════════════════════════════
# search() — mock BLS ile entegrasyon
# ═══════════════════════════════════════════════════════

def _fake_bls_result(periods, powers, durations=None, t0s=None):
    n = len(periods)
    durations = durations if durations is not None else [0.1] * n
    t0s = t0s if t0s is not None else [1000.0] * n
    return SimpleNamespace(
        period=np.array(periods) * u.day,
        power=np.array(powers),
        duration=np.array(durations) * u.day,
        transit_time=np.array(t0s) * u.day,
    )


def _fake_model_class(stats=None):
    stats = stats or {"depth": [1e-3, 1e-4]}
    class FakeModel:
        def __init__(self, *a, **kw): pass
        def autoperiod(self, *a, **kw):
            return np.linspace(20, 500, 100) * u.day
        def power(self, periods, durations, objective="snr"):
            n = len(periods)
            return SimpleNamespace(
                period=periods,
                power=np.linspace(5, 20, n),
                duration=np.full(n, durations[0].value if hasattr(durations[0], "value") else durations[0]) * u.day,
                transit_time=np.full(n, 1050.0) * u.day,
            )
        def compute_stats(self, *a, **kw):
            return stats
    return FakeModel


def test_search_full_flow():
    import astrotransit.detection.long_period as mod
    s = LongPeriodTransitSearch()
    lc = _make_lc(n=300, start=1000.0, end=1300.0)

    fake_model = _fake_model_class()
    with patch.object(mod, "BoxLeastSquares", fake_model):
        r = s.search(lc)
    assert isinstance(r, LongPeriodResult)
    assert r.target_id == "TIC 1"


def test_search_bls_raises_returns_notes():
    import astrotransit.detection.long_period as mod
    s = LongPeriodTransitSearch()
    lc = _make_lc(n=300)

    class FakeModel:
        def __init__(self, *a, **kw): pass
        def autoperiod(self, *a, **kw):
            return np.linspace(20, 500, 50) * u.day
        def power(self, *a, **kw):
            raise RuntimeError("bls fail")
    with patch.object(mod, "BoxLeastSquares", FakeModel):
        r = s.search(lc)
    assert r.has_candidate is False
    assert any("BLS" in n for n in r.notes)


# ═══════════════════════════════════════════════════════
# _period_grid — fallback
# ═══════════════════════════════════════════════════════

def test_period_grid_fallback():
    import astrotransit.detection.long_period as mod
    s = LongPeriodTransitSearch()
    t = np.linspace(1000, 1100, 100)
    d = np.array([0.1, 0.2])

    class BadModel:
        def __init__(self, *a, **kw): pass
        def autoperiod(self, *a, **kw):
            raise RuntimeError("no autoperiod")
    with patch.object(mod, "BoxLeastSquares", BadModel):
        periods = s._period_grid(t, d)
    assert periods.size > 0
    assert np.all(np.isfinite(periods))


def test_period_grid_caps_size():
    import astrotransit.detection.long_period as mod
    s = LongPeriodTransitSearch()
    t = np.linspace(1000, 1100, 100)
    d = np.array([0.1])

    class BigModel:
        def __init__(self, *a, **kw): pass
        def autoperiod(self, *a, **kw):
            return np.linspace(20, 500, 50000) * u.day
    with patch.object(mod, "BoxLeastSquares", BigModel):
        periods = s._period_grid(t, d)
    assert periods.size <= 12000


# ═══════════════════════════════════════════════════════
# _build_peaks
# ═══════════════════════════════════════════════════════

def test_build_peaks_basic():
    s = LongPeriodTransitSearch()
    # Daha küçük config ile hızlı
    s.config = LongPeriodSearchConfig(n_peaks=2)

    fake_result = _fake_bls_result([100.0, 200.0], [15.0, 12.0], durations=[0.1, 0.2])
    fake_model = MagicMock()
    fake_model.compute_stats.return_value = {"depth": [1e-3, 1e-4]}

    time = np.linspace(1000, 1200, 500)
    flux = np.ones(500)
    err = np.full(500, 1e-4)

    peaks = s._build_peaks(fake_model, fake_result, time, flux, err)
    assert len(peaks) == 2
    assert peaks[0].period == 100.0


def test_build_peaks_dedup_close_periods():
    s = LongPeriodTransitSearch()
    s.config = LongPeriodSearchConfig(n_peaks=3)

    fake_result = _fake_bls_result(
        [100.0, 100.5, 200.0],  # 100 ve 100.5 çok yakın
        [15.0, 14.0, 12.0],
    )
    fake_model = MagicMock()
    fake_model.compute_stats.return_value = {"depth": [1e-3, 1e-4]}

    time = np.linspace(1000, 1200, 500)
    flux = np.ones(500)
    err = np.full(500, 1e-4)

    peaks = s._build_peaks(fake_model, fake_result, time, flux, err)
    # 100 ve 200 kabul edilir (100.5 elenir)
    assert len(peaks) == 2


def test_build_peaks_limited_by_n_peaks():
    s = LongPeriodTransitSearch()
    s.config = LongPeriodSearchConfig(n_peaks=1)

    fake_result = _fake_bls_result(
        [50.0, 100.0, 200.0], [15.0, 12.0, 10.0],
    )
    fake_model = MagicMock()
    fake_model.compute_stats.return_value = {"depth": [1e-3, 1e-4]}

    time = np.linspace(1000, 1200, 500)
    flux = np.ones(500)
    err = np.full(500, 1e-4)

    peaks = s._build_peaks(fake_model, fake_result, time, flux, err)
    assert len(peaks) == 1
