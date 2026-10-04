"""astrotransit/detection/tls_search.py için testler."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from astrotransit.detection.tls_search import (
    TLSResult,
    TLSSearch,
)

# ═══════════════════════════════════════════════════════
# TLSResult
# ═══════════════════════════════════════════════════════

def _make_result(**kw):
    base = dict(
        target_id="TIC 1", sector=1,
        period=3.5, period_err=0.01, t0=100.0, duration=0.1,
        depth=0.001, rp_rs=0.1, sde=15.0, snr=20.0,
        odd_even_mismatch=0.5, transit_count=3,
        transit_times=np.array([100.0, 103.5, 107.0]),
        transit_depths=np.array([0.001, 0.0011, 0.0009]),
        folded_phase=np.linspace(-0.5, 0.5, 100),
        folded_flux=np.ones(100),
        model_phase=np.linspace(-0.5, 0.5, 100),
        model_flux=np.ones(100),
    )
    base.update(kw)
    return TLSResult(**base)


def test_tls_result_to_dict():
    r = _make_result()
    d = r.to_dict()
    assert d["period"] == 3.5
    assert d["duration_hours"] == 2.4
    assert d["depth_ppm"] == 1000.0
    assert d["sde"] == 15.0
    assert d["snr"] == 20.0
    assert d["transit_count"] == 3
    assert d["passed_threshold"] is True


def test_tls_result_summary_includes_ids():
    r = _make_result(target_id="TIC X", sector=14)
    s = r.summary()
    assert s["target_id"] == "TIC X"
    assert s["sector"] == 14
    assert s["period"] == 3.5


# ═══════════════════════════════════════════════════════
# TLSSearch.__init__
# ═══════════════════════════════════════════════════════

def test_init_requires_tls(monkeypatch):
    import astrotransit.detection.tls_search as mod
    monkeypatch.setattr(mod, "_TLS_AVAILABLE", False)
    with pytest.raises(ImportError, match="transitleastsquares"):
        TLSSearch()


def _make_search(monkeypatch, **kw):
    import astrotransit.detection.tls_search as mod
    monkeypatch.setattr(mod, "_TLS_AVAILABLE", True)
    # Thresholds.validate() çağrısını da geçir
    return TLSSearch(**kw)


def test_init_default(monkeypatch):
    s = _make_search(monkeypatch)
    assert s.oversampling_factor == 3
    assert s.use_stellar_params is True
    assert s.transit_template == "default"
    assert s.period_search_window == 0.1


def test_init_custom(monkeypatch):
    s = _make_search(
        monkeypatch, oversampling_factor=5, use_stellar_params=False,
        transit_template="box", period_search_window=0.2,
    )
    assert s.oversampling_factor == 5
    assert s.use_stellar_params is False


# ═══════════════════════════════════════════════════════
# _evaluate_threshold
# ═══════════════════════════════════════════════════════

def test_evaluate_threshold_all_pass(monkeypatch):
    s = _make_search(monkeypatch)
    r = _make_result(sde=20.0, snr=20.0, odd_even_mismatch=0.5,
                     transit_count=3, false_alarm_probability=0.001)
    out = s._evaluate_threshold(r)
    assert out.passed_threshold is True
    assert out.reject_reason == ""


def test_evaluate_threshold_low_sde(monkeypatch):
    s = _make_search(monkeypatch)
    r = _make_result(sde=1.0)
    out = s._evaluate_threshold(r)
    assert out.passed_threshold is False
    assert "SDE" in out.reject_reason


def test_evaluate_threshold_low_snr(monkeypatch):
    s = _make_search(monkeypatch)
    r = _make_result(snr=0.5)
    out = s._evaluate_threshold(r)
    assert out.passed_threshold is False
    assert "SNR" in out.reject_reason


def test_evaluate_threshold_few_transits(monkeypatch):
    s = _make_search(monkeypatch)
    r = _make_result(transit_count=1)
    out = s._evaluate_threshold(r)
    assert out.passed_threshold is False
    assert "transit_count" in out.reject_reason


def test_evaluate_threshold_high_odd_even(monkeypatch):
    s = _make_search(monkeypatch)
    r = _make_result(odd_even_mismatch=99.0)
    out = s._evaluate_threshold(r)
    assert out.passed_threshold is False
    assert "odd_even" in out.reject_reason


def test_evaluate_threshold_high_fap(monkeypatch):
    s = _make_search(monkeypatch)
    r = _make_result(false_alarm_probability=0.9)
    out = s._evaluate_threshold(r)
    assert out.passed_threshold is False
    assert "FAP" in out.reject_reason


def test_evaluate_threshold_multiple_fails(monkeypatch):
    s = _make_search(monkeypatch)
    r = _make_result(sde=1.0, snr=0.5, transit_count=1)
    out = s._evaluate_threshold(r)
    assert out.passed_threshold is False
    assert "|" in out.reject_reason  # birleştirilmiş sebepler


# ═══════════════════════════════════════════════════════
# _failed_result
# ═══════════════════════════════════════════════════════

def test_failed_result(monkeypatch):
    s = _make_search(monkeypatch)
    r = s._failed_result("TIC 1", 5, "test reason")
    assert r.target_id == "TIC 1"
    assert r.sector == 5
    assert r.passed_threshold is False
    assert "test reason" in r.reject_reason
    assert r.false_alarm_probability == 1.0
    assert r.odd_even_mismatch == 999.0


# ═══════════════════════════════════════════════════════
# validate — hata yolları
# ═══════════════════════════════════════════════════════

def _make_detrended(n=1000, span=200.0, target="TIC 1", sector=1):
    t = np.linspace(1000.0, 1000.0 + span, n)
    flux = 1.0 + np.random.default_rng(0).normal(0, 1e-4, n)
    return SimpleNamespace(
        target_id=target, sector=sector,
        time=t, flux=flux, flux_err=np.full(n, 1e-4),
    )


def _make_bls_peak(period=3.5, t0=100.0, duration=0.1):
    return SimpleNamespace(
        period=period, t0=t0, duration=duration,
        period_err=0.01, depth=0.001, snr=15.0, power=20.0,
        transit_times=np.array([100.0, 103.5]),
        passed_threshold=True,
    )


def _fake_tls_model_class(result_data=None):
    """transitleastsquares(...) çağrısına cevap verecek fake class."""
    class FakeTLSModel:
        def __init__(self, *a, **kw):
            pass
        def power(self, **kw):
            if result_data is not None and result_data.get("raise"):
                raise RuntimeError(result_data["raise"])
            defaults = dict(
                period=3.5, period_uncertainty=0.01, T0=100.0,
                duration=0.1, depth=0.999, rp_rs=0.1,
                SDE=15.0, snr=20.0, odd_even_mismatch=0.5,
                transit_count=3, FAP=0.001,
                transit_times=[100.0, 103.5, 107.0],
                transit_depths=[0.001, 0.0011, 0.0009],
                folded_phase=np.linspace(-0.5, 0.5, 50),
                folded_y=np.ones(50),
                model_folded_phase=np.linspace(-0.5, 0.5, 50),
                model_folded_model=np.ones(50),
            )
            if result_data:
                defaults.update({k: v for k, v in result_data.items() if k != "raise"})
            return SimpleNamespace(**defaults)
    return FakeTLSModel


def test_validate_invalid_bls_period(monkeypatch):
    s = _make_search(monkeypatch)
    peak = _make_bls_peak(period=0.0)
    r = s.validate(_make_detrended(), peak)
    assert r.passed_threshold is False
    assert "invalid BLS period" in r.reject_reason


def test_validate_tls_raises(monkeypatch):
    s = _make_search(monkeypatch)
    import astrotransit.detection.tls_search as mod

    def raiser(*a, **kw):
        raise RuntimeError("tls failed")
    monkeypatch.setattr(mod, "transitleastsquares", raiser)

    peak = _make_bls_peak()
    r = s.validate(_make_detrended(), peak)
    assert r.passed_threshold is False
    assert "tls failed" in r.reject_reason


def test_validate_result_parse_error(monkeypatch):
    s = _make_search(monkeypatch)
    import astrotransit.detection.tls_search as mod

    # power() dönüşü eksik attributelarla → parse hatası
    class BadResult:
        def __init__(self):
            self.period = "not a float"

    class FakeModel:
        def __init__(self, *a, **kw): pass
        def power(self, **kw): return BadResult()
    monkeypatch.setattr(mod, "transitleastsquares", FakeModel)

    peak = _make_bls_peak()
    r = s.validate(_make_detrended(), peak)
    assert r.passed_threshold is False


def test_validate_period_window_corrective_fail(monkeypatch):
    """period_min >= period_max → corrective; sonra hâlâ geçersiz → hata."""
    s = _make_search(monkeypatch, period_search_window=0.99)
    # span çok küçük → period_max = obs/2 çok küçük, corrective de yetersiz
    detrended = _make_detrended(n=10, span=0.01)
    peak = _make_bls_peak(period=1000.0)
    r = s.validate(detrended, peak)
    assert r.passed_threshold is False
    assert "period range invalid" in r.reject_reason


def test_validate_happy_path(monkeypatch):
    s = _make_search(monkeypatch)
    import astrotransit.detection.tls_search as mod
    monkeypatch.setattr(mod, "transitleastsquares", _fake_tls_model_class())

    peak = _make_bls_peak()
    r = s.validate(_make_detrended(), peak)
    assert r.passed_threshold is True
    assert r.period == 3.5
    assert r.sde == 15.0


def test_validate_happy_path_custom_result(monkeypatch):
    s = _make_search(monkeypatch)
    import astrotransit.detection.tls_search as mod
    monkeypatch.setattr(
        mod, "transitleastsquares",
        _fake_tls_model_class({"period": 5.0, "SDE": 25.0, "snr": 30.0}),
    )
    peak = _make_bls_peak(period=5.0)
    r = s.validate(_make_detrended(), peak)
    assert r.period == 5.0
    assert r.sde == 25.0


def test_validate_threshold_fail(monkeypatch):
    s = _make_search(monkeypatch)
    import astrotransit.detection.tls_search as mod
    # Düşük SDE → threshold fail
    monkeypatch.setattr(
        mod, "transitleastsquares",
        _fake_tls_model_class({"SDE": 1.0, "snr": 1.0}),
    )
    peak = _make_bls_peak()
    r = s.validate(_make_detrended(), peak)
    assert r.passed_threshold is False
    assert "SDE" in r.reject_reason


def test_validate_without_stellar_params(monkeypatch):
    s = _make_search(monkeypatch, use_stellar_params=False)
    import astrotransit.detection.tls_search as mod
    monkeypatch.setattr(mod, "transitleastsquares", _fake_tls_model_class())
    peak = _make_bls_peak()
    r = s.validate(_make_detrended(), peak)
    assert r.passed_threshold is True


def test_validate_no_rp_rs_attribute(monkeypatch):
    """rp_rs attribute yoksa sqrt(depth) fallback."""
    s = _make_search(monkeypatch)
    import astrotransit.detection.tls_search as mod

    class FakeResult:
        def __init__(self):
            self.period = 3.5
            self.period_uncertainty = 0.01
            self.T0 = 100.0
            self.duration = 0.1
            self.depth = 0.999
            # rp_rs yok → sqrt(depth) = sqrt(0.001)
            self.SDE = 15.0
            self.snr = 20.0
            self.odd_even_mismatch = 0.5
            self.transit_count = 3
            self.FAP = 0.001
            self.transit_times = np.array([100.0, 103.5])
            # transit_depths yok
            self.folded_phase = np.linspace(-0.5, 0.5, 50)
            self.folded_y = np.ones(50)
            self.model_folded_phase = np.linspace(-0.5, 0.5, 50)
            self.model_folded_model = np.ones(50)

    class FakeModel:
        def __init__(self, *a, **kw): pass
        def power(self, **kw): return FakeResult()
    monkeypatch.setattr(mod, "transitleastsquares", FakeModel)

    peak = _make_bls_peak()
    r = s.validate(_make_detrended(), peak)
    assert r.passed_threshold is True
    assert r.rp_rs == pytest.approx(np.sqrt(0.001))
