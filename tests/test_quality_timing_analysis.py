"""
TimingAnalyzer birim testleri.

Kapsam
------
- _days_to_minutes / _minutes_to_days
- TimingTest / TimingReport to_dict + summary
- analyze(): O-C path, observed_midtimes path, bos seri
- _test_oc_rms / _test_max_abs_oc / _test_linear_trend: PASS/WARN/FAIL/SKIP
- _resolve_oc_series: oc_values, observed_midtimes, transit_numbers
- _compute_details, _compute_score, _compute_flag
"""

from __future__ import annotations

import numpy as np
import pytest

from astrotransit.quality.timing_analysis import (
    TimingAnalyzer,
    TimingReport,
    TimingTest,
    _days_to_minutes,
    _minutes_to_days,
)
from astrotransit.quality.vetting import VettingVerdict

# ─────────────────────────────────────────────────────────────
# Yardimcilar
# ─────────────────────────────────────────────────────────────

def _days_from_minutes(m: float) -> float:
    return m / (24.0 * 60.0)


@pytest.fixture
def analyzer() -> TimingAnalyzer:
    return TimingAnalyzer()


# ─────────────────────────────────────────────────────────────
# _days_to_minutes / _minutes_to_days
# ─────────────────────────────────────────────────────────────

def test_days_to_minutes_scalar() -> None:
    assert _days_to_minutes(1.0) == 1440.0


def test_days_to_minutes_array() -> None:
    arr = np.array([0.5, 1.0])
    out = _days_to_minutes(arr)
    assert np.allclose(out, [720.0, 1440.0])


def test_minutes_to_days() -> None:
    assert _minutes_to_days(1440.0) == 1.0


# ─────────────────────────────────────────────────────────────
# TimingTest
# ─────────────────────────────────────────────────────────────

def test_timing_test_to_dict() -> None:
    t = TimingTest(
        name="oc_rms", verdict=VettingVerdict.PASS,
        value=5.5, warn_threshold=15.0, fail_threshold=30.0,
        unit="min", description="test",
    )
    d = t.to_dict()
    assert d["name"] == "oc_rms"
    assert d["verdict"] == "pass"
    assert d["value"] == 5.5
    assert d["warn_threshold"] == 15.0
    assert d["fail_threshold"] == 30.0
    assert d["unit"] == "min"


# ─────────────────────────────────────────────────────────────
# TimingReport
# ─────────────────────────────────────────────────────────────

def test_timing_report_defaults() -> None:
    r = TimingReport(target_id="TIC-1", sector=1)
    assert r.n_transits == 0
    assert r.flag == "UNKNOWN"
    assert r.score == 0.0
    assert r.tests == []


def test_timing_report_to_dict() -> None:
    r = TimingReport(
        target_id="TIC-1", sector=1, n_transits=5,
        flag="STABLE", score=0.1,
        n_pass=3, n_warn=0, n_fail=0, n_skip=0,
        tests=[
            TimingTest("oc_rms", VettingVerdict.PASS, 5.0, 15.0, 30.0, "min", "ok"),
        ],
        details={"period_days": 5.0},
    )
    d = r.to_dict()
    assert d["target_id"] == "TIC-1"
    assert d["flag"] == "STABLE"
    assert d["score"] == 0.1
    assert d["n_transits"] == 5
    assert len(d["tests"]) == 1


def test_timing_report_summary() -> None:
    r = TimingReport(
        target_id="TIC-1", sector=2,
        flag="TTV_CANDIDATE", score=0.35,
        n_pass=1, n_warn=2, n_fail=0, n_skip=0,
        n_transits=4,
    )
    s = r.summary()
    assert "TIC-1" in s
    assert "S2" in s
    assert "TTV_CANDIDATE" in s
    assert "n_transits=4" in s


# ─────────────────────────────────────────────────────────────
# __init__
# ─────────────────────────────────────────────────────────────

def test_analyzer_init_defaults() -> None:
    a = TimingAnalyzer()
    assert a.oc_rms_warn_min == 15.0
    assert a.oc_rms_fail_min == 30.0
    assert a.max_oc_warn_min == 20.0
    assert a.max_oc_fail_min == 40.0
    assert a.trend_drift_warn_min == 10.0
    assert a.trend_drift_fail_min == 25.0


def test_analyzer_init_custom() -> None:
    a = TimingAnalyzer(
        oc_rms_warn_min=5.0, oc_rms_fail_min=10.0,
    )
    assert a.oc_rms_warn_min == 5.0


# ─────────────────────────────────────────────────────────────
# _test_oc_rms
# ─────────────────────────────────────────────────────────────

def test_oc_rms_skip_insufficient(analyzer: TimingAnalyzer) -> None:
    t = analyzer._test_oc_rms(np.array([0.01]))
    assert t.verdict == VettingVerdict.SKIP


def test_oc_rms_pass(analyzer: TimingAnalyzer) -> None:
    """RMS kucuk -> PASS."""
    oc = np.array([0.001, -0.001, 0.002, -0.002])  # ~0.5 dk
    t = analyzer._test_oc_rms(oc)
    assert t.verdict == VettingVerdict.PASS


def test_oc_rms_warn(analyzer: TimingAnalyzer) -> None:
    """RMS ~20 dk (warn=15, fail=30)."""
    oc = np.full(4, _days_from_minutes(20.0))
    t = analyzer._test_oc_rms(oc)
    assert t.verdict == VettingVerdict.WARN


def test_oc_rms_fail(analyzer: TimingAnalyzer) -> None:
    """RMS > 30 dk."""
    oc = np.full(4, _days_from_minutes(50.0))
    t = analyzer._test_oc_rms(oc)
    assert t.verdict == VettingVerdict.FAIL


# ─────────────────────────────────────────────────────────────
# _test_max_abs_oc
# ─────────────────────────────────────────────────────────────

def test_max_abs_oc_skip_empty(analyzer: TimingAnalyzer) -> None:
    t = analyzer._test_max_abs_oc(np.array([]))
    assert t.verdict == VettingVerdict.SKIP


def test_max_abs_oc_pass(analyzer: TimingAnalyzer) -> None:
    oc = np.array([_days_from_minutes(5.0), _days_from_minutes(-5.0)])
    t = analyzer._test_max_abs_oc(oc)
    assert t.verdict == VettingVerdict.PASS


def test_max_abs_oc_warn(analyzer: TimingAnalyzer) -> None:
    oc = np.array([_days_from_minutes(25.0), 0.0])
    t = analyzer._test_max_abs_oc(oc)
    assert t.verdict == VettingVerdict.WARN


def test_max_abs_oc_fail(analyzer: TimingAnalyzer) -> None:
    oc = np.array([_days_from_minutes(50.0), 0.0])
    t = analyzer._test_max_abs_oc(oc)
    assert t.verdict == VettingVerdict.FAIL


# ─────────────────────────────────────────────────────────────
# _test_linear_trend
# ─────────────────────────────────────────────────────────────

def test_linear_trend_skip_insufficient(analyzer: TimingAnalyzer) -> None:
    t = analyzer._test_linear_trend(np.array([1.0, 2.0]), np.array([0.0, 0.0]))
    assert t.verdict == VettingVerdict.SKIP


def test_linear_trend_skip_zero_span(analyzer: TimingAnalyzer) -> None:
    """epochs hep ayni -> SKIP."""
    t = analyzer._test_linear_trend(
        np.array([5.0, 5.0, 5.0]), np.array([0.0, 0.0, 0.0]),
    )
    assert t.verdict == VettingVerdict.SKIP


def test_linear_trend_pass(analyzer: TimingAnalyzer) -> None:
    """Sifir trend -> PASS."""
    epochs = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    oc = np.array([0.0001, -0.0001, 0.0002, -0.0002, 0.0001])
    t = analyzer._test_linear_trend(epochs, oc)
    assert t.verdict == VettingVerdict.PASS


def test_linear_trend_fail(analyzer: TimingAnalyzer) -> None:
    """Guclu lineer trend -> FAIL."""
    epochs = np.arange(10, dtype=float)
    # drift: 10 epoch * ~5 dk/epoch = ~50 dk
    oc = np.array([_days_from_minutes(5.0 * e) for e in epochs])
    t = analyzer._test_linear_trend(epochs, oc)
    assert t.verdict == VettingVerdict.FAIL


def test_linear_trend_warn(analyzer: TimingAnalyzer) -> None:
    """Orta seviye trend + anlamli p -> WARN."""
    epochs = np.arange(8, dtype=float)
    # drift ~15 dk total
    oc = np.array([_days_from_minutes(2.0 * e) for e in epochs])
    t = analyzer._test_linear_trend(epochs, oc)
    assert t.verdict in (VettingVerdict.WARN, VettingVerdict.FAIL)


def test_linear_trend_large_drift_low_p(analyzer: TimingAnalyzer) -> None:
    """Buyuk drift ama yuksek p (gurultulu) -> WARN (fallback)."""
    epochs = np.arange(4, dtype=float)
    # drift buyuk ama p buyuk olsun diye az nokta
    oc = np.array([
        _days_from_minutes(30.0),
        _days_from_minutes(-20.0),
        _days_from_minutes(25.0),
        _days_from_minutes(-15.0),
    ])
    t = analyzer._test_linear_trend(epochs, oc)
    assert t.verdict in (VettingVerdict.WARN, VettingVerdict.PASS)


# ─────────────────────────────────────────────────────────────
# analyze() — O-C path
# ─────────────────────────────────────────────────────────────

def test_analyze_with_oc_values(analyzer: TimingAnalyzer) -> None:
    oc = np.array([0.001, -0.001, 0.002, -0.002, 0.001])
    report = analyzer.analyze(
        target_id="TIC-100", sector=1, period=5.0,
        oc_values=oc,
    )
    assert isinstance(report, TimingReport)
    assert report.target_id == "TIC-100"
    assert report.n_transits == 5


def test_analyze_with_oc_and_transit_numbers(analyzer: TimingAnalyzer) -> None:
    oc = np.array([0.001, -0.001, 0.002])
    tn = np.array([1.0, 2.0, 3.0])
    report = analyzer.analyze(
        target_id="TIC-100", sector=1, period=5.0,
        oc_values=oc, transit_numbers=tn,
    )
    assert report.n_transits == 3


def test_analyze_oc_with_wrong_length_transit_numbers(analyzer: TimingAnalyzer) -> None:
    """Uzunluk eslesmezse uyari + arange ile epoch."""
    oc = np.array([0.001, -0.001, 0.002])
    tn = np.array([1.0, 2.0])  # eslesmiyor
    report = analyzer.analyze(
        target_id="TIC-100", sector=1, period=5.0,
        oc_values=oc, transit_numbers=tn,
    )
    # Hata yok, 3 transit
    assert report.n_transits == 3


def test_analyze_oc_with_nan_filtered(analyzer: TimingAnalyzer) -> None:
    oc = np.array([0.001, np.nan, -0.001, 0.002])
    report = analyzer.analyze(
        target_id="TIC-100", sector=1, period=5.0,
        oc_values=oc,
    )
    assert report.n_transits == 3


# ─────────────────────────────────────────────────────────────
# analyze() — observed_midtimes path
# ─────────────────────────────────────────────────────────────

def test_analyze_with_observed_midtimes(analyzer: TimingAnalyzer) -> None:
    """Basit periyodik midtime'lar -> STABLE."""
    period = 5.0
    t0 = 100.0
    midtimes = t0 + np.arange(5) * period + np.array([0, 0.0001, -0.0001, 0, 0])
    report = analyzer.analyze(
        target_id="TIC-100", sector=1, period=period,
        observed_midtimes=midtimes, t0=t0,
    )
    assert report.n_transits == 5
    assert report.flag == "STABLE"


def test_analyze_observed_without_t0(analyzer: TimingAnalyzer) -> None:
    """t0 verilmezse robust tahmin."""
    period = 5.0
    midtimes = np.arange(5) * period
    report = analyzer.analyze(
        target_id="TIC-100", sector=1, period=period,
        observed_midtimes=midtimes,
    )
    assert report.n_transits == 5


def test_analyze_observed_with_transit_numbers(analyzer: TimingAnalyzer) -> None:
    period = 5.0
    t0 = 100.0
    tn = np.arange(5).astype(float)
    midtimes = t0 + tn * period
    report = analyzer.analyze(
        target_id="TIC-100", sector=1, period=period,
        observed_midtimes=midtimes, transit_numbers=tn, t0=t0,
    )
    assert report.n_transits == 5


def test_analyze_observed_transit_numbers_wrong_length(analyzer: TimingAnalyzer) -> None:
    period = 5.0
    t0 = 100.0
    midtimes = t0 + np.arange(5) * period
    tn = np.array([1.0, 2.0])  # eslesmiyor
    report = analyzer.analyze(
        target_id="TIC-100", sector=1, period=period,
        observed_midtimes=midtimes, transit_numbers=tn, t0=t0,
    )
    assert report.n_transits == 5


def test_analyze_observed_with_nan(analyzer: TimingAnalyzer) -> None:
    period = 5.0
    t0 = 100.0
    midtimes = np.array([t0, np.nan, t0 + 2 * period, t0 + 3 * period])
    report = analyzer.analyze(
        target_id="TIC-100", sector=1, period=period,
        observed_midtimes=midtimes, t0=t0,
    )
    assert report.n_transits == 3


# ─────────────────────────────────────────────────────────────
# analyze() — bos/gecersiz
# ─────────────────────────────────────────────────────────────

def test_analyze_invalid_period(analyzer: TimingAnalyzer) -> None:
    """period <= 0 -> bos seri."""
    report = analyzer.analyze(
        target_id="TIC-100", sector=1, period=0.0,
        oc_values=np.array([0.001, 0.002]),
    )
    assert report.n_transits == 0
    assert report.flag == "UNKNOWN"


def test_analyze_no_inputs(analyzer: TimingAnalyzer) -> None:
    """Hicbir giris yok -> bos seri."""
    report = analyzer.analyze(
        target_id="TIC-100", sector=1, period=5.0,
    )
    assert report.n_transits == 0


def test_analyze_observed_empty(analyzer: TimingAnalyzer) -> None:
    report = analyzer.analyze(
        target_id="TIC-100", sector=1, period=5.0,
        observed_midtimes=np.array([]),
    )
    assert report.n_transits == 0


# ─────────────────────────────────────────────────────────────
# _compute_score
# ─────────────────────────────────────────────────────────────

def test_score_all_pass() -> None:
    tests = [
        TimingTest("oc_rms", VettingVerdict.PASS, 0.0, 15.0, 30.0),
        TimingTest("max_abs_oc", VettingVerdict.PASS, 0.0, 20.0, 40.0),
        TimingTest("linear_ephemeris_trend", VettingVerdict.PASS, 0.0, 10.0, 25.0),
    ]
    assert TimingAnalyzer._compute_score(tests) == 0.0


def test_score_all_fail() -> None:
    tests = [
        TimingTest("oc_rms", VettingVerdict.FAIL, 50.0, 15.0, 30.0),
        TimingTest("max_abs_oc", VettingVerdict.FAIL, 60.0, 20.0, 40.0),
    ]
    assert TimingAnalyzer._compute_score(tests) == 1.0


def test_score_all_skip() -> None:
    tests = [TimingTest("oc_rms", VettingVerdict.SKIP, 0.0, 15.0, 30.0)]
    assert TimingAnalyzer._compute_score(tests) == 0.0


def test_score_warn_only() -> None:
    tests = [TimingTest("oc_rms", VettingVerdict.WARN, 20.0, 15.0, 30.0)]
    assert TimingAnalyzer._compute_score(tests) == pytest.approx(0.4)


# ─────────────────────────────────────────────────────────────
# _compute_flag
# ─────────────────────────────────────────────────────────────

def test_flag_unknown_no_active() -> None:
    tests = [TimingTest("oc_rms", VettingVerdict.SKIP, 0.0, 15.0, 30.0)]
    assert TimingAnalyzer._compute_flag(tests, 0.0, 0, 0) == "UNKNOWN"


def test_flag_stable() -> None:
    tests = [TimingTest("oc_rms", VettingVerdict.PASS, 0.0, 15.0, 30.0)]
    assert TimingAnalyzer._compute_flag(tests, 0.0, 0, 0) == "STABLE"


def test_flag_ttv_candidate_rms_warn() -> None:
    tests = [TimingTest("oc_rms", VettingVerdict.WARN, 20.0, 15.0, 30.0)]
    assert TimingAnalyzer._compute_flag(tests, 0.4, 0, 1) == "TTV_CANDIDATE"


def test_flag_timing_unstable_trend_fail() -> None:
    tests = [TimingTest("linear_ephemeris_trend", VettingVerdict.FAIL, 50.0, 10.0, 25.0)]
    assert TimingAnalyzer._compute_flag(tests, 1.0, 1, 0) == "TIMING_UNSTABLE"


def test_flag_timing_unstable_score_high() -> None:
    tests = [TimingTest("oc_rms", VettingVerdict.WARN, 20.0, 15.0, 30.0)]
    assert TimingAnalyzer._compute_flag(tests, 0.65, 0, 1) == "TIMING_UNSTABLE"


# ─────────────────────────────────────────────────────────────
# _compute_details
# ─────────────────────────────────────────────────────────────

def test_compute_details_basic(analyzer: TimingAnalyzer) -> None:
    details = analyzer._compute_details(
        period=5.0,
        epochs=np.array([0.0, 1.0, 2.0]),
        oc_days=np.array([0.001, -0.001, 0.002]),
        observed_midtimes=np.array([100.0, 105.0, 110.0]),
        expected_midtimes=np.array([100.0, 105.0, 110.0]),
        t0_used=100.0,
    )
    assert details["period_days"] == 5.0
    assert details["t0_used"] == 100.0
    assert details["n_transits"] == 3
    assert "oc_days" in details
    assert "oc_minutes" in details
    assert "observed_midtimes" in details
    assert "expected_midtimes" in details


def test_compute_details_single_transit(analyzer: TimingAnalyzer) -> None:
    """n=1 -> max_abs_oc var ama oc_rms yok."""
    details = analyzer._compute_details(
        period=5.0,
        epochs=np.array([0.0]),
        oc_days=np.array([0.001]),
        observed_midtimes=np.array([]),
        expected_midtimes=np.array([]),
        t0_used=None,
    )
    assert details["n_transits"] == 1
    assert "max_abs_oc_min" in details
    assert "oc_rms_min" not in details
    assert details["t0_used"] is None


def test_compute_details_with_linear_fit(analyzer: TimingAnalyzer) -> None:
    """n>=3 ve epochs farkli -> linear_slope_* eklenir."""
    details = analyzer._compute_details(
        period=5.0,
        epochs=np.array([0.0, 1.0, 2.0, 3.0]),
        oc_days=np.array([0.001, 0.002, 0.003, 0.004]),
        observed_midtimes=np.array([]),
        expected_midtimes=np.array([]),
        t0_used=0.0,
    )
    assert "linear_slope_days_per_epoch" in details
    assert "linear_pvalue" in details
    assert "linear_total_drift_min" in details


def test_compute_details_empty_oc(analyzer: TimingAnalyzer) -> None:
    details = analyzer._compute_details(
        period=5.0,
        epochs=np.array([]),
        oc_days=np.array([]),
        observed_midtimes=np.array([]),
        expected_midtimes=np.array([]),
        t0_used=None,
    )
    assert details["n_transits"] == 0
