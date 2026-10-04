"""astrotransit/detection/cascade.py için testler."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from astrotransit.detection.cascade import (
    CascadeCandidate,
    CascadeDetector,
    CascadeStatus,
)

# ═══════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════

def _fake_bls_result_empty():
    return SimpleNamespace(
        target_id="TIC 1", sector=1, best=None, all_peaks=[],
        periods_searched=np.array([]), power_array=np.array([]),
        n_periods_searched=0, has_candidate=False,
    )


def _fake_bls_peak(period=3.5, depth=0.01, snr=15.0, power=20.0,
                   t0=100.0, duration=0.1, period_err=0.01):
    return SimpleNamespace(
        period=period, depth=depth, snr=snr, power=power,
        t0=t0, duration=duration, period_err=period_err,
        transit_times=np.array([t0, t0 + period]),
        passed_threshold=True,
    )


def _fake_bls_result_with_candidate(peaks=None):
    peaks = peaks or [_fake_bls_peak()]
    return SimpleNamespace(
        target_id="TIC 1", sector=1, best=peaks[0], all_peaks=peaks,
        periods_searched=np.array([3.5]), power_array=np.array([20.0]),
        n_periods_searched=1, has_candidate=True,
    )


def _fake_tls_result(passed=True, period=3.5, sde=12.0, snr=15.0,
                     depth=0.01, rp_rs=0.1, t0=100.0, duration=0.1,
                     period_err=0.01):
    return SimpleNamespace(
        passed_threshold=passed, period=period, sde=sde, snr=snr,
        depth=depth, rp_rs=rp_rs, t0=t0, duration=duration,
        period_err=period_err,
        transit_times=np.array([t0, t0 + period]),
    )


def _candidate(status=CascadeStatus.CONFIRMED, confirmed=True):
    return CascadeCandidate(
        target_id="TIC 1", sector=1, status=status, confirmed=confirmed,
        bls_result=_fake_bls_result_empty(), tls_result=None,
        period=3.5, snr=15.0, sde=12.0,
    )


def _patch_cascade_deps(monkeypatch, thresholds=None):
    import astrotransit.detection.cascade as mod
    monkeypatch.setattr(mod, "BLSSearch", lambda **kw: MagicMock())
    monkeypatch.setattr(mod, "TLSSearch", lambda **kw: MagicMock())
    if thresholds is None:
        thresholds = SimpleNamespace(
            bls=MagicMock(), tls=MagicMock(),
            require_both=True, period_tolerance=0.05,
        )
    monkeypatch.setattr(mod, "CascadeThresholds", MagicMock(
        from_settings=MagicMock(return_value=thresholds),
    ))
    return thresholds


def _detector(monkeypatch, tol=0.05, require_both=True):
    thresholds = SimpleNamespace(
        bls=MagicMock(), tls=MagicMock(),
        require_both=require_both, period_tolerance=tol,
    )
    _patch_cascade_deps(monkeypatch, thresholds)
    return CascadeDetector()


def _make_detrended(n=500, sector=1, target="TIC 1"):
    t = np.linspace(1000, 1002, n)  # kısa obs_span → harmonik eklenmez
    return SimpleNamespace(
        target_id=target, sector=sector,
        time=t, flux=np.ones(n), flux_err=np.full(n, 1e-4),
    )


# ═══════════════════════════════════════════════════════
# CascadeStatus + CascadeCandidate
# ═══════════════════════════════════════════════════════

def test_status_enum_values():
    assert CascadeStatus.CONFIRMED.value == "confirmed"
    assert CascadeStatus.BLS_ONLY.value == "bls_only"
    assert CascadeStatus.BLS_FAILED.value == "bls_failed"
    assert CascadeStatus.TLS_FAILED.value == "tls_failed"
    assert CascadeStatus.PERIOD_MISMATCH.value == "period_mismatch"
    assert CascadeStatus.ERROR.value == "error"


def test_candidate_has_candidate_confirmed():
    assert _candidate(CascadeStatus.CONFIRMED).has_candidate is True


def test_candidate_has_candidate_bls_only():
    assert _candidate(CascadeStatus.BLS_ONLY, confirmed=False).has_candidate is True


def test_candidate_has_candidate_bls_failed():
    assert _candidate(CascadeStatus.BLS_FAILED, confirmed=False).has_candidate is False


def test_candidate_to_dict_keys():
    d = _candidate().to_dict()
    assert d["target_id"] == "TIC 1"
    assert d["status"] == "confirmed"
    assert d["confirmed"] is True
    assert d["has_candidate"] is True
    assert d["period"] == 3.5
    assert "n_transits" in d
    assert "decision_log" in d


def test_candidate_summary_equals_to_dict():
    c = _candidate()
    assert c.summary() == c.to_dict()


# ═══════════════════════════════════════════════════════
# __init__
# ═══════════════════════════════════════════════════════

def test_init_default(monkeypatch):
    _patch_cascade_deps(monkeypatch)
    d = CascadeDetector()
    assert d.stellar_radius == 1.0
    assert d.stellar_mass == 1.0


def test_init_custom_stellar(monkeypatch):
    _patch_cascade_deps(monkeypatch)
    d = CascadeDetector(stellar_radius=1.5, stellar_mass=1.2)
    assert d.stellar_radius == 1.5
    assert d.stellar_mass == 1.2


def test_init_custom_thresholds(monkeypatch):
    import astrotransit.detection.cascade as mod
    monkeypatch.setattr(mod, "BLSSearch", lambda **kw: MagicMock())
    monkeypatch.setattr(mod, "TLSSearch", lambda **kw: MagicMock())
    custom = SimpleNamespace(
        bls=MagicMock(), tls=MagicMock(),
        require_both=False, period_tolerance=0.1,
    )
    d = CascadeDetector(thresholds=custom)
    assert d.thresholds is custom


# ═══════════════════════════════════════════════════════
# _check_period_agreement
# ═══════════════════════════════════════════════════════

def test_period_agreement_invalid_periods(monkeypatch):
    d = _detector(monkeypatch)
    ok, diff = d._check_period_agreement(0.0, 3.5)
    assert ok is False
    assert diff == 999.0
    ok, diff = d._check_period_agreement(3.5, -1.0)
    assert ok is False


def test_period_agreement_exact(monkeypatch):
    d = _detector(monkeypatch, tol=0.05)
    ok, diff = d._check_period_agreement(3.5, 3.5)
    assert ok is True
    assert diff < 0.001


def test_period_agreement_harmonic_half(monkeypatch):
    d = _detector(monkeypatch, tol=0.05)
    ok, _diff = d._check_period_agreement(3.5, 1.75)
    assert ok is True


def test_period_agreement_harmonic_double(monkeypatch):
    d = _detector(monkeypatch, tol=0.05)
    ok, _diff = d._check_period_agreement(3.5, 7.0)
    assert ok is True


def test_period_agreement_mismatch(monkeypatch):
    d = _detector(monkeypatch, tol=0.01)
    ok, diff = d._check_period_agreement(3.5, 5.5)
    assert ok is False
    assert diff > 0.01


# ═══════════════════════════════════════════════════════
# detect — erken çıkışlar
# ═══════════════════════════════════════════════════════

def test_detect_bls_exception(monkeypatch):
    d = _detector(monkeypatch)
    d._bls = MagicMock()
    d._bls.search.side_effect = RuntimeError("bls boom")

    c = d.detect(_make_detrended())
    assert c.status == CascadeStatus.ERROR
    assert c.confirmed is False
    assert any("BLS hata" in log for log in c.decision_log)


def test_detect_bls_no_candidate(monkeypatch):
    d = _detector(monkeypatch)
    d._bls = MagicMock()
    d._bls.search.return_value = _fake_bls_result_empty()

    c = d.detect(_make_detrended())
    assert c.status == CascadeStatus.BLS_FAILED
    assert c.confirmed is False


# ═══════════════════════════════════════════════════════
# detect — TLS onaylı / mismatch
# ═══════════════════════════════════════════════════════

def test_detect_confirmed(monkeypatch):
    d = _detector(monkeypatch, tol=0.05, require_both=True)
    d._bls = MagicMock()
    d._bls.search.return_value = _fake_bls_result_with_candidate()

    d._tls = MagicMock()
    d._tls.validate.return_value = _fake_tls_result(
        passed=True, period=3.5, sde=12.0, snr=15.0,
    )

    c = d.detect(_make_detrended())
    assert c.status == CascadeStatus.CONFIRMED
    assert c.confirmed is True
    assert c.period == 3.5


def test_detect_period_mismatch(monkeypatch):
    d = _detector(monkeypatch, tol=0.01, require_both=True)
    d._bls = MagicMock()
    peak = _fake_bls_peak(period=3.5)
    d._bls.search.return_value = _fake_bls_result_with_candidate([peak])

    d._tls = MagicMock()
    d._tls.validate.return_value = _fake_tls_result(
        passed=True, period=9.5, sde=10.0, snr=12.0,
    )

    c = d.detect(_make_detrended())
    assert c.status == CascadeStatus.PERIOD_MISMATCH
    assert c.confirmed is False


def test_detect_tls_exception_require_both(monkeypatch):
    d = _detector(monkeypatch, tol=0.05, require_both=True)
    d._bls = MagicMock()
    peak = _fake_bls_peak(period=3.5)
    d._bls.search.return_value = _fake_bls_result_with_candidate([peak])

    d._tls = MagicMock()
    d._tls.validate.side_effect = RuntimeError("tls boom")

    c = d.detect(_make_detrended())
    assert c.status == CascadeStatus.TLS_FAILED
    assert c.confirmed is False
    assert c.period == 3.5


def test_detect_tls_exception_no_require_both(monkeypatch):
    d = _detector(monkeypatch, tol=0.05, require_both=False)
    d._bls = MagicMock()
    peak = _fake_bls_peak(period=3.5)
    d._bls.search.return_value = _fake_bls_result_with_candidate([peak])

    d._tls = MagicMock()
    d._tls.validate.side_effect = RuntimeError("tls boom")

    c = d.detect(_make_detrended())
    assert c.status == CascadeStatus.BLS_ONLY
    assert c.confirmed is False
    assert c.period == 3.5


def test_detect_harmonic_candidates_added(monkeypatch):
    """Harmonik adayları: kod dataclasses.replace() kullandığı için gerçek
    BLSPeak/BLSResult gerekir. obs_span uzun tutulur, 2P ve 0.5P eklenir."""
    from astrotransit.detection.bls_search import BLSPeak, BLSResult

    d = _detector(monkeypatch, tol=0.05, require_both=True)
    d._bls = MagicMock()

    peak = BLSPeak(
        period=10.0, period_err=0.1, duration=0.1,
        depth=0.01, t0=1000.0, power=20.0, snr=15.0,
        depth_err=1e-4, n_transits=3,
        transit_times=np.array([1000.0, 1010.0, 1020.0]),
    )
    bls_result = BLSResult(
        target_id="TIC 1", sector=1, best=peak,
        all_peaks=[peak],
        periods_searched=np.array([10.0]),
        power_array=np.array([20.0]),
        n_periods_searched=1, has_candidate=True,
    )
    d._bls.search.return_value = bls_result

    call_count = {"n": 0}

    def fake_validate(*a, **kw):
        call_count["n"] += 1
        return _fake_tls_result(passed=True, period=10.0, sde=10.0 + call_count["n"])

    d._tls = MagicMock()
    d._tls.validate.side_effect = fake_validate

    # Uzun obs_span: 300 gün → harmonikler (2P=20, 0.5P=5) eklenir
    n = 500
    detrended = SimpleNamespace(
        target_id="TIC 1", sector=1,
        time=np.linspace(1000, 1300, n),
        flux=np.ones(n), flux_err=np.full(n, 1e-4),
    )

    d.detect(detrended)
    # En az 2 çağrı: orijinal + 1 harmonik
    assert call_count["n"] >= 2


# ═══════════════════════════════════════════════════════
# _build_bls_only_candidate
# ═══════════════════════════════════════════════════════

def test_build_bls_only_no_tls(monkeypatch):
    d = _detector(monkeypatch)
    peak = _fake_bls_peak(depth=0.01, snr=15.0)
    c = d._build_bls_only_candidate(
        "TIC 1", 1, _fake_bls_result_empty(), None, peak, ["test"],
    )
    assert c.status == CascadeStatus.BLS_ONLY
    assert c.confirmed is False
    assert c.sde == 0.0
    assert c.rp_rs == pytest.approx(np.sqrt(0.01))


def test_build_bls_only_with_tls(monkeypatch):
    d = _detector(monkeypatch)
    peak = _fake_bls_peak(depth=0.01)
    tls = _fake_tls_result(sde=12.0)
    c = d._build_bls_only_candidate(
        "TIC 1", 1, _fake_bls_result_empty(), tls, peak, ["test"],
    )
    assert c.status == CascadeStatus.BLS_ONLY
    assert c.sde == 12.0


def test_build_bls_only_negative_depth(monkeypatch):
    d = _detector(monkeypatch)
    peak = _fake_bls_peak(depth=-0.01)
    c = d._build_bls_only_candidate(
        "TIC 1", 1, _fake_bls_result_empty(), None, peak, [],
    )
    assert c.rp_rs == 0.0


# ═══════════════════════════════════════════════════════
# detect_multi_sector
# ═══════════════════════════════════════════════════════

def test_detect_multi_sector_empty(monkeypatch):
    d = _detector(monkeypatch)
    assert d.detect_multi_sector([]) == []


def test_detect_multi_sector_happy(monkeypatch):
    d = _detector(monkeypatch)
    monkeypatch.setattr(d, "detect", lambda lc: _candidate(
        CascadeStatus.CONFIRMED, confirmed=True,
    ))
    results = d.detect_multi_sector([_make_detrended(), _make_detrended()])
    assert len(results) == 2


def test_detect_multi_sector_handles_exception(monkeypatch):
    d = _detector(monkeypatch)
    calls = {"n": 0}

    def fake_detect(lc):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return _candidate(CascadeStatus.CONFIRMED, confirmed=True)

    monkeypatch.setattr(d, "detect", fake_detect)
    results = d.detect_multi_sector([_make_detrended(), _make_detrended()])
    assert len(results) == 1


# ═══════════════════════════════════════════════════════
# get_best_candidate
# ═══════════════════════════════════════════════════════

def test_get_best_empty(monkeypatch):
    d = _detector(monkeypatch)
    assert d.get_best_candidate([]) is None


def test_get_best_prefers_confirmed(monkeypatch):
    d = _detector(monkeypatch)
    c1 = CascadeCandidate(
        target_id="TIC 1", sector=1, status=CascadeStatus.BLS_ONLY,
        confirmed=False, bls_result=_fake_bls_result_empty(),
        tls_result=None, snr=20.0, sde=15.0,
    )
    c2 = CascadeCandidate(
        target_id="TIC 1", sector=2, status=CascadeStatus.CONFIRMED,
        confirmed=True, bls_result=_fake_bls_result_empty(),
        tls_result=None, snr=10.0, sde=8.0,
    )
    best = d.get_best_candidate([c1, c2])
    assert best is c2


def test_get_best_by_snr_among_confirmed(monkeypatch):
    d = _detector(monkeypatch)
    c1 = CascadeCandidate(
        target_id="T", sector=1, status=CascadeStatus.CONFIRMED,
        confirmed=True, bls_result=_fake_bls_result_empty(),
        tls_result=None, snr=10.0,
    )
    c2 = CascadeCandidate(
        target_id="T", sector=2, status=CascadeStatus.CONFIRMED,
        confirmed=True, bls_result=_fake_bls_result_empty(),
        tls_result=None, snr=20.0,
    )
    assert d.get_best_candidate([c1, c2]) is c2


def test_get_best_by_sde_when_no_confirmed(monkeypatch):
    d = _detector(monkeypatch)
    c1 = CascadeCandidate(
        target_id="T", sector=1, status=CascadeStatus.BLS_ONLY,
        confirmed=False, bls_result=_fake_bls_result_empty(),
        tls_result=None, sde=5.0,
    )
    c2 = CascadeCandidate(
        target_id="T", sector=2, status=CascadeStatus.BLS_ONLY,
        confirmed=False, bls_result=_fake_bls_result_empty(),
        tls_result=None, sde=15.0,
    )
    assert d.get_best_candidate([c1, c2]) is c2
