"""
TESSDetrending ve DetrendComparator birim testleri.

Strateji
--------
wotan.flatten module-level monkeypatch ile mock'lanir; gercek detrending
yapilmaz. CleanedLightCurve fixture'i sentetik veri ile uretilir.
"""

from __future__ import annotations

import numpy as np
import pytest

from astrotransit.preprocessing import tess_detrend as td_module
from astrotransit.preprocessing.cleaning import CleanedLightCurve, LightCurveSegment
from astrotransit.preprocessing.tess_detrend import (
    DetrendComparator,
    DetrendComparison,
    DetrendedLightCurve,
    DetrendMethod,
    TESSDetrending,
)

# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

def _cleaned(target: str = "TIC-100", sector: int = 1, n: int = 500) -> CleanedLightCurve:
    rng = np.random.default_rng(0)
    time = np.linspace(100.0, 120.0, n)
    flux = 1.0 + rng.normal(0, 5e-4, size=n)
    err = np.full(n, 5e-4)
    seg = LightCurveSegment(
        time=time, flux=flux, flux_err=err,
        start_time=float(time[0]), end_time=float(time[-1]),
        segment_index=0,
    )
    return CleanedLightCurve(
        target_id=target, sector=sector,
        time=time, flux=flux, flux_err=err,
        segments=[seg], n_points_input=n,
        n_gaps_detected=0, meta={"CADENCE": "120s"},
    )


def _install_fake_flatten(monkeypatch, trend_scale: float = 1.0, n_removed: int = 0):
    """wotan.flatten yerine cagrilabilir bir fake kurar."""
    def fake_flatten(time, flux, method, window_length, break_tolerance,
                     return_trend, cval=None, edge_cutoff=None, **kwargs):
        trend = np.full(len(time), trend_scale)
        flattened = flux / trend
        if n_removed > 0:
            # Belirli noktalari nan yap
            flattened = flattened.copy()
            flattened[-n_removed:] = np.nan
        return flattened, trend

    monkeypatch.setattr(td_module, "flatten", fake_flatten)
    monkeypatch.setattr(td_module, "_WOTAN_AVAILABLE", True)


def _detrended(target: str = "TIC-100", sector: int = 1, n: int = 500,
               method: str = "biweight") -> DetrendedLightCurve:
    rng = np.random.default_rng(0)
    time = np.linspace(100.0, 120.0, n)
    flux = 1.0 + rng.normal(0, 5e-4, size=n)
    return DetrendedLightCurve(
        target_id=target, sector=sector,
        time=time, flux=flux,
        flux_err=np.full(n, 5e-4),
        trend=np.ones(n),
        raw_flux=flux + 0.001,
        method=method,
        window_length=0.5,
        break_tolerance=0.5,
        meta={"CADENCE": "120s"},
    )


# ─────────────────────────────────────────────────────────────
# DetrendMethod enum
# ─────────────────────────────────────────────────────────────

def test_detrend_method_values() -> None:
    assert DetrendMethod.BIWEIGHT.value == "biweight"
    assert DetrendMethod.COSINE.value == "cosine"
    assert DetrendMethod.SPLINE.value == "spline"
    assert DetrendMethod.MEDIAN.value == "median"
    assert DetrendMethod.LOWESS.value == "lowess"


# ─────────────────────────────────────────────────────────────
# DetrendedLightCurve properties
# ─────────────────────────────────────────────────────────────

def test_detrended_n_points() -> None:
    d = _detrended(n=123)
    assert d.n_points == 123


def test_detrended_residual_std() -> None:
    """residual_std = std(flux - 1.0)"""
    d = _detrended(n=1000)
    expected = float(np.nanstd(d.flux - 1.0))
    assert d.residual_std == pytest.approx(expected, rel=1e-6)


def test_detrended_residual_rms() -> None:
    d = _detrended(n=1000)
    expected = float(np.sqrt(np.nanmean((d.flux - 1.0) ** 2)))
    assert d.residual_rms == pytest.approx(expected, rel=1e-6)


def test_detrended_noise_ppm() -> None:
    d = _detrended(n=1000)
    assert d.noise_ppm == pytest.approx(d.residual_std * 1e6, rel=1e-6)


def test_detrended_summary() -> None:
    d = _detrended(method="spline")
    s = d.summary()
    assert s["target_id"] == "TIC-100"
    assert s["sector"] == 1
    assert s["method"] == "spline"
    assert s["n_points"] == 500
    assert s["window_length_days"] == 0.5
    assert "residual_std" in s
    assert "residual_rms" in s
    assert "noise_ppm" in s


# ─────────────────────────────────────────────────────────────
# DetrendComparison
# ─────────────────────────────────────────────────────────────

def test_detrend_comparison_summary() -> None:
    r1 = _detrended(method="biweight")
    r2 = _detrended(method="spline")
    c = DetrendComparison(
        target_id="TIC-1", sector=2,
        results={"biweight": r1, "spline": r2},
        best_method="biweight",
    )
    s = c.summary()
    assert s["target_id"] == "TIC-1"
    assert s["sector"] == 2
    assert s["best_method"] == "biweight"
    assert "biweight" in s["method_scores"]
    assert "spline" in s["method_scores"]


# ─────────────────────────────────────────────────────────────
# TESSDetrending.__init__
# ─────────────────────────────────────────────────────────────

def test_detrending_init_default(monkeypatch) -> None:
    monkeypatch.setattr(td_module, "_WOTAN_AVAILABLE", True)
    d = TESSDetrending()
    assert d.method == DetrendMethod.BIWEIGHT
    assert d.window_length == 0.5
    assert d.break_tolerance == 0.5
    assert d.edge_cutoff == 0.0
    assert d.cval == 5.0


def test_detrending_init_string_method(monkeypatch) -> None:
    monkeypatch.setattr(td_module, "_WOTAN_AVAILABLE", True)
    d = TESSDetrending(method="spline")
    assert d.method == DetrendMethod.SPLINE


def test_detrending_init_uppercase_string(monkeypatch) -> None:
    monkeypatch.setattr(td_module, "_WOTAN_AVAILABLE", True)
    d = TESSDetrending(method="SPLINE")
    assert d.method == DetrendMethod.SPLINE


def test_detrending_init_invalid_method(monkeypatch) -> None:
    monkeypatch.setattr(td_module, "_WOTAN_AVAILABLE", True)
    with pytest.raises(ValueError, match="Geçersiz detrending yöntemi"):
        TESSDetrending(method="nonsense")


def test_detrending_init_enum_method(monkeypatch) -> None:
    monkeypatch.setattr(td_module, "_WOTAN_AVAILABLE", True)
    d = TESSDetrending(method=DetrendMethod.MEDIAN)
    assert d.method == DetrendMethod.MEDIAN


def test_detrending_init_no_wotan(monkeypatch) -> None:
    monkeypatch.setattr(td_module, "_WOTAN_AVAILABLE", False)
    with pytest.raises(ImportError, match="wotan"):
        TESSDetrending()


def test_detrending_init_custom_params(monkeypatch) -> None:
    monkeypatch.setattr(td_module, "_WOTAN_AVAILABLE", True)
    d = TESSDetrending(
        method="cosine", window_length=1.2,
        break_tolerance=0.3, edge_cutoff=0.1, cval=4.0,
    )
    assert d.window_length == 1.2
    assert d.break_tolerance == 0.3
    assert d.edge_cutoff == 0.1
    assert d.cval == 4.0


# ─────────────────────────────────────────────────────────────
# detrend()
# ─────────────────────────────────────────────────────────────

def test_detrend_success(monkeypatch) -> None:
    _install_fake_flatten(monkeypatch, trend_scale=1.0)
    d = TESSDetrending()
    result = d.detrend(_cleaned())
    assert isinstance(result, DetrendedLightCurve)
    assert result.target_id == "TIC-100"
    assert result.method == "biweight"
    assert result.n_points == 500
    assert result.window_length == 0.5


def test_detrend_removes_invalid_points(monkeypatch) -> None:
    _install_fake_flatten(monkeypatch, trend_scale=1.0, n_removed=5)
    d = TESSDetrending()
    result = d.detrend(_cleaned(n=500))
    # 5 nokta NaN -> cikarilmali
    assert result.n_points == 495


def test_detrend_too_few_valid_points(monkeypatch) -> None:
    """Cok az gecerli nokta -> ValueError."""
    def fake_flatten(time, flux, **kwargs):
        # Cogunu nan yap
        flux_nan = np.full(len(time), np.nan)
        flux_nan[:10] = 1.0
        trend = np.full(len(time), 1.0)
        return flux_nan, trend

    monkeypatch.setattr(td_module, "flatten", fake_flatten)
    monkeypatch.setattr(td_module, "_WOTAN_AVAILABLE", True)

    d = TESSDetrending()
    with pytest.raises(ValueError, match="çok az geçerli nokta"):
        d.detrend(_cleaned(n=500))


def test_detrend_wotan_exception(monkeypatch) -> None:
    def fake_flatten(*args, **kwargs):
        raise RuntimeError("wotan crashed")

    monkeypatch.setattr(td_module, "flatten", fake_flatten)
    monkeypatch.setattr(td_module, "_WOTAN_AVAILABLE", True)

    d = TESSDetrending()
    with pytest.raises(RuntimeError, match="Detrending başarısız"):
        d.detrend(_cleaned())


def test_detrend_passes_cval_for_biweight(monkeypatch) -> None:
    captured = {}

    def fake_flatten(**kwargs):
        captured.update(kwargs)
        return np.ones(len(kwargs["time"])), np.ones(len(kwargs["time"]))

    monkeypatch.setattr(td_module, "flatten", fake_flatten)
    monkeypatch.setattr(td_module, "_WOTAN_AVAILABLE", True)

    d = TESSDetrending(method="biweight", cval=4.5)
    d.detrend(_cleaned(n=100))
    assert captured["cval"] == 4.5


def test_detrend_no_cval_for_non_biweight(monkeypatch) -> None:
    captured = {}

    def fake_flatten(**kwargs):
        captured.update(kwargs)
        return np.ones(len(kwargs["time"])), np.ones(len(kwargs["time"]))

    monkeypatch.setattr(td_module, "flatten", fake_flatten)
    monkeypatch.setattr(td_module, "_WOTAN_AVAILABLE", True)

    d = TESSDetrending(method="spline")
    d.detrend(_cleaned(n=100))
    assert "cval" not in captured


def test_detrend_passes_edge_cutoff(monkeypatch) -> None:
    captured = {}

    def fake_flatten(**kwargs):
        captured.update(kwargs)
        return np.ones(len(kwargs["time"])), np.ones(len(kwargs["time"]))

    monkeypatch.setattr(td_module, "flatten", fake_flatten)
    monkeypatch.setattr(td_module, "_WOTAN_AVAILABLE", True)

    d = TESSDetrending(edge_cutoff=0.2)
    d.detrend(_cleaned(n=100))
    assert captured["edge_cutoff"] == 0.2


# ─────────────────────────────────────────────────────────────
# detrend_with_window_search
# ─────────────────────────────────────────────────────────────

def test_window_search_picks_best(monkeypatch) -> None:
    """En dusuk RMS'li pencereyi secer."""
    call_windows = []

    def fake_flatten(**kwargs):
        w = kwargs["window_length"]
        call_windows.append(w)
        n = len(kwargs["time"])
        # window_length buyudukce scatter azalsin
        scale = 1.0 / w
        rng = np.random.default_rng(int(w * 100))
        flux = 1.0 + rng.normal(0, 1e-4 * scale, size=n)
        return flux, np.ones(n)

    monkeypatch.setattr(td_module, "flatten", fake_flatten)
    monkeypatch.setattr(td_module, "_WOTAN_AVAILABLE", True)

    d = TESSDetrending()
    result = d.detrend_with_window_search(
        _cleaned(n=200),
        window_candidates=[0.3, 1.0],
    )
    assert result.window_length in (0.3, 1.0)
    # 1.0 daha dusuk RMS uretmeli
    assert result.window_length == 1.0


def test_window_search_default_candidates(monkeypatch) -> None:
    """Default pencere listesi kullanilir."""
    called = []

    def fake_flatten(**kwargs):
        called.append(kwargs["window_length"])
        n = len(kwargs["time"])
        return np.ones(n), np.ones(n)

    monkeypatch.setattr(td_module, "flatten", fake_flatten)
    monkeypatch.setattr(td_module, "_WOTAN_AVAILABLE", True)

    d = TESSDetrending()
    d.detrend_with_window_search(_cleaned(n=100))
    # Default: [0.3, 0.5, 0.75, 1.0, 1.5]
    assert len(called) == 5
    assert 0.5 in called


def test_window_search_all_fail(monkeypatch) -> None:
    def fake_flatten(*args, **kwargs):
        raise RuntimeError("all fail")

    monkeypatch.setattr(td_module, "flatten", fake_flatten)
    monkeypatch.setattr(td_module, "_WOTAN_AVAILABLE", True)

    d = TESSDetrending()
    with pytest.raises(RuntimeError, match="hiçbir pencere genişliği başarılı olmadı"):
        d.detrend_with_window_search(_cleaned(n=100), window_candidates=[0.5])


def test_window_search_partial_failure(monkeypatch) -> None:
    """Bir pencere basarisiz olursa digeri devam eder."""
    call_windows = []

    def fake_flatten(**kwargs):
        w = kwargs["window_length"]
        call_windows.append(w)
        if w == 0.3:
            raise RuntimeError("first window fail")
        n = len(kwargs["time"])
        return np.ones(n), np.ones(n)

    monkeypatch.setattr(td_module, "flatten", fake_flatten)
    monkeypatch.setattr(td_module, "_WOTAN_AVAILABLE", True)

    d = TESSDetrending()
    result = d.detrend_with_window_search(
        _cleaned(n=100), window_candidates=[0.3, 0.5],
    )
    assert result.window_length == 0.5


# ─────────────────────────────────────────────────────────────
# DetrendComparator
# ─────────────────────────────────────────────────────────────

def test_comparator_init_defaults() -> None:
    c = DetrendComparator()
    assert c.methods == ["biweight", "cosine", "spline", "median"]
    assert c.window_length == 0.5
    assert c.break_tolerance == 0.5


def test_comparator_init_custom() -> None:
    c = DetrendComparator(methods=["spline"], window_length=1.0)
    assert c.methods == ["spline"]
    assert c.window_length == 1.0


def test_compare_success(monkeypatch) -> None:
    """Tum yontemler basarili -> DetrendComparison."""
    monkeypatch.setattr(td_module, "_WOTAN_AVAILABLE", True)

    def fake_flatten(**kwargs):
        n = len(kwargs["time"])
        # Farkli yontemler farkli scatter uretsin
        method = kwargs["method"]
        scale = {"biweight": 1e-4, "spline": 2e-4, "median": 3e-4, "cosine": 4e-4}.get(method, 1e-4)
        rng = np.random.default_rng(hash(method) % 2**31)
        flux = 1.0 + rng.normal(0, scale, size=n)
        return flux, np.ones(n)

    monkeypatch.setattr(td_module, "flatten", fake_flatten)

    c = DetrendComparator()
    result = c.compare(_cleaned(n=200))
    assert isinstance(result, DetrendComparison)
    assert result.target_id == "TIC-100"
    assert len(result.results) == 4
    # En dusuk scatter'li yontem biweight
    assert result.best_method == "biweight"


def test_compare_partial_failure(monkeypatch) -> None:
    """Bir yontem hata verse bile digerleri tamamlanir."""
    monkeypatch.setattr(td_module, "_WOTAN_AVAILABLE", True)

    def fake_flatten(**kwargs):
        if kwargs["method"] == "spline":
            raise RuntimeError("spline fail")
        n = len(kwargs["time"])
        return np.ones(n), np.ones(n)

    monkeypatch.setattr(td_module, "flatten", fake_flatten)

    c = DetrendComparator(methods=["biweight", "spline", "median"])
    result = c.compare(_cleaned(n=100))
    assert "spline" not in result.results
    assert "biweight" in result.results


def test_compare_all_fail_raises(monkeypatch) -> None:
    monkeypatch.setattr(td_module, "_WOTAN_AVAILABLE", True)

    def fake_flatten(*args, **kwargs):
        raise RuntimeError("all fail")

    monkeypatch.setattr(td_module, "flatten", fake_flatten)

    c = DetrendComparator()
    with pytest.raises(RuntimeError, match="hiçbir detrending yöntemi başarılı olmadı"):
        c.compare(_cleaned(n=100))
