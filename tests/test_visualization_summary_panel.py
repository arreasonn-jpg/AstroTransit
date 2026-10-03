"""
SummaryPanelPlotter birim testleri.

Kapsam
------
- plot() ana akis: 9 panel uretimi
- Panel metodlari ayri ayri (private)
- fit_result ve stellar_props var/yok senaryolari
- save davranislari
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np
import pytest

from astrotransit.data.catalog_client import StellarProperties
from astrotransit.detection.bls_search import BLSPeak, BLSResult
from astrotransit.detection.cascade import CascadeCandidate, CascadeStatus
from astrotransit.detection.tls_search import TLSResult
from astrotransit.modeling.map_fit import MAPFitResult
from astrotransit.modeling.parameters import DerivedParameters
from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve
from astrotransit.quality.scorer import (
    CandidateClass,
    QualityScore,
    ScoreComponent,
)
from astrotransit.quality.vetting import (
    VettingReport,
    VettingTest,
    VettingVerdict,
)
from astrotransit.visualization.base import FigureManager
from astrotransit.visualization.summary_panel import SummaryPanelPlotter


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

def _detrended(target: str = "TIC-100", sector: int = 1, n: int = 300) -> DetrendedLightCurve:
    rng = np.random.default_rng(0)
    t = np.linspace(100.0, 120.0, n)
    flux = 1.0 + rng.normal(0, 1e-3, size=n)
    err = np.full(n, 1e-3)
    trend = np.ones(n)
    raw = flux + 0.01
    return DetrendedLightCurve(
        target_id=target,
        sector=sector,
        time=t,
        flux=flux,
        flux_err=err,
        trend=trend,
        raw_flux=raw,
        method="biweight",
        window_length=0.5,
        break_tolerance=0.5,
        meta={"CADENCE": "120s"},
    )


def _candidate(target: str = "TIC-100", sector: int = 1, n_transits: int = 5) -> CascadeCandidate:
    dummy_bls = type("BLSDummy", (), {})()
    return CascadeCandidate(
        target_id=target,
        sector=sector,
        status=CascadeStatus.CONFIRMED,
        confirmed=True,
        bls_result=dummy_bls,  # type: ignore[arg-type]
        tls_result=None,
        period=5.0,
        period_err=0.01,
        t0=100.0,
        duration=0.15,
        depth=0.005,
        rp_rs=0.08,
        snr=8.0,
        sde=9.5,
        transit_times=np.linspace(100.0, 120.0, n_transits),
        decision_log=[],
    )


def _bls_result(
    target: str = "TIC-100",
    sector: int = 1,
    with_best: bool = True,
    with_data: bool = True,
) -> BLSResult:
    if with_data:
        periods = np.logspace(np.log10(0.5), np.log10(20.0), 500)
        power = 5.0 + 8.0 * np.exp(-0.5 * ((np.log10(periods) - np.log10(5.0)) / 0.1) ** 2)
    else:
        periods = np.array([])
        power = np.array([])

    best = None
    if with_best:
        best = BLSPeak(
            period=5.0,
            period_err=0.01,
            duration=0.15,
            depth=0.005,
            t0=1.0,
            power=12.5,
            snr=8.0,
            depth_err=0.001,
            n_transits=4,
            transit_times=np.linspace(0.0, 20.0, 4),
            passed_threshold=True,
        )

    return BLSResult(
        target_id=target,
        sector=sector,
        best=best,
        all_peaks=[best] if best else [],
        periods_searched=periods,
        power_array=power,
        n_periods_searched=len(periods),
        has_candidate=with_best,
    )


def _tls_result(
    target: str = "TIC-100",
    sector: int = 1,
    with_data: bool = True,
    with_model: bool = True,
) -> TLSResult:
    if with_data:
        phase = np.linspace(0.0, 1.0, 200)
        flux = 1.0 + np.random.default_rng(0).normal(0, 1e-3, size=200)
    else:
        phase = np.array([])
        flux = np.array([])

    if with_model:
        model_phase = np.linspace(0.0, 1.0, 300)
        model_flux = np.ones(300)
    else:
        model_phase = np.array([])
        model_flux = np.array([])

    return TLSResult(
        target_id=target,
        sector=sector,
        period=5.0,
        period_err=0.001,
        t0=100.0,
        duration=0.15,
        depth=0.005,
        rp_rs=0.08,
        sde=9.5,
        snr=8.0,
        odd_even_mismatch=0.5,
        transit_count=4,
        transit_times=np.linspace(100.0, 120.0, 4),
        transit_depths=np.full(4, 0.005),
        folded_phase=phase,
        folded_flux=flux,
        model_phase=model_phase,
        model_flux=model_flux,
        passed_threshold=True,
        reject_reason="",
        false_alarm_probability=1e-5,
        raw_stats={},
    )


def _score(target: str = "TIC-100", sector: int = 1, anomalous: bool = False) -> QualityScore:
    components = [
        ScoreComponent(name="snr", raw_value=12.5, score=85.0, weight=0.2, contribution=17.0),
        ScoreComponent(name="vetting", raw_value=0.5, score=75.0, weight=0.3, contribution=22.5),
    ]
    return QualityScore(
        target_id=target,
        sector=sector,
        total_score=72.0,
        candidate_class=CandidateClass.B,
        class_description="Yuksek olasilikli aday",
        components=components,
        is_anomalous=anomalous,
        anomaly_flags=["test_flag"] if anomalous else [],
        fpp=0.15,
        fpp_method="heuristic_v1",
        is_false_positive=False,
    )


def _vetting(target: str = "TIC-100", sector: int = 1, fpp: float | None = 0.15) -> VettingReport:
    tests = [
        VettingTest(name="test_a", verdict=VettingVerdict.PASS, value=1.0, threshold=2.0),
        VettingTest(name="test_b", verdict=VettingVerdict.WARN, value=2.5, threshold=2.0),
    ]
    return VettingReport(
        target_id=target,
        sector=sector,
        tests=tests,
        n_pass=1,
        n_fail=0,
        n_warn=1,
        false_positive_probability=fpp,
        is_false_positive=False,
    )


def _fit_result(target: str = "TIC-100", sector: int = 1, success: bool = True) -> MAPFitResult:
    derived = DerivedParameters(
        planet_radius_rjup=0.9,
        planet_radius_rearth=10.0,
        semi_major_axis_au=0.05,
        inclination_deg=88.5,
        stellar_density_gcm3=1.4,
        equilibrium_temperature_k=800.0,
        transit_depth_ppm=6400.0,
        insolation_flux=400.0,
    )
    return MAPFitResult(
        target_id=target,
        sector=sector,
        success=success,
        period=5.0,
        period_err=0.001,
        t0=100.0,
        rp_rs=0.08,
        impact_parameter=0.3,
        a_over_rs=8.5,
        inclination=88.5,
        u1=0.3,
        u2=0.2,
        log_jitter=-7.0,
        baseline=1.0,
        log_likelihood=-1234.5,
        residual_rms=0.0008,
        derived=derived,
        n_iterations=42,
        optimizer_message="CONVERGENCE: ...",
        fit_method="map",
    )


def _stellar(target: str = "TIC-100") -> StellarProperties:
    return StellarProperties(
        tic_id=100,
        ra=45.123,
        dec=-20.456,
        teff=5800.0,
        logg=4.4,
        radius=1.05,
        mass=1.0,
        tmag=10.5,
        distance=50.0,
        luminosity=1.1,
        metallicity=0.0,
        source="TIC",
    )


# ─────────────────────────────────────────────────────────────
# __init__
# ─────────────────────────────────────────────────────────────

def test_plotter_init() -> None:
    fm = FigureManager()
    plotter = SummaryPanelPlotter(fm)
    assert plotter.fm is fm


# ─────────────────────────────────────────────────────────────
# plot() ana akis
# ─────────────────────────────────────────────────────────────

def test_plot_minimal_returns_figure() -> None:
    fm = FigureManager()
    plotter = SummaryPanelPlotter(fm)
    fig = plotter.plot(
        detrended=_detrended(),
        candidate=_candidate(),
        bls_result=_bls_result(),
        tls_result=None,
        score=_score(),
        vetting=_vetting(),
        save=False,
    )
    assert isinstance(fig, plt.Figure)
    # 8 alt panel + suptitle
    assert len(fig.axes) == 8


def test_plot_with_tls_returns_figure() -> None:
    fm = FigureManager()
    plotter = SummaryPanelPlotter(fm)
    fig = plotter.plot(
        detrended=_detrended(),
        candidate=_candidate(),
        bls_result=_bls_result(),
        tls_result=_tls_result(),
        score=_score(),
        vetting=_vetting(),
        save=False,
    )
    assert len(fig.axes) == 8


def test_plot_with_fit_result() -> None:
    fm = FigureManager()
    plotter = SummaryPanelPlotter(fm)
    fig = plotter.plot(
        detrended=_detrended(),
        candidate=_candidate(),
        bls_result=_bls_result(),
        tls_result=_tls_result(),
        score=_score(),
        vetting=_vetting(),
        fit_result=_fit_result(),
        save=False,
    )
    assert isinstance(fig, plt.Figure)


def test_plot_with_stellar_props() -> None:
    fm = FigureManager()
    plotter = SummaryPanelPlotter(fm)
    fig = plotter.plot(
        detrended=_detrended(),
        candidate=_candidate(),
        bls_result=_bls_result(),
        tls_result=None,
        score=_score(),
        vetting=_vetting(),
        stellar_props=_stellar(),
        save=False,
    )
    assert isinstance(fig, plt.Figure)


def test_plot_suptitle() -> None:
    fm = FigureManager()
    plotter = SummaryPanelPlotter(fm)
    fig = plotter.plot(
        detrended=_detrended(),
        candidate=_candidate(target="TIC-999"),
        bls_result=_bls_result(),
        tls_result=None,
        score=_score(),
        vetting=_vetting(),
        save=False,
    )
    assert fig._suptitle is not None
    assert "TIC-999" in fig._suptitle.get_text()


def test_plot_fpp_none_in_suptitle() -> None:
    fm = FigureManager()
    plotter = SummaryPanelPlotter(fm)
    fig = plotter.plot(
        detrended=_detrended(),
        candidate=_candidate(),
        bls_result=_bls_result(),
        tls_result=None,
        score=_score(),
        vetting=_vetting(fpp=None),
        save=False,
    )
    assert "NA" in fig._suptitle.get_text()


def test_plot_saves(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = SummaryPanelPlotter(fm)
    plotter.plot(
        detrended=_detrended(),
        candidate=_candidate(),
        bls_result=_bls_result(),
        tls_result=None,
        score=_score(),
        vetting=_vetting(),
        save=True,
    )
    files = list(tmp_path.glob("*_summary.png"))
    assert len(files) == 1


def test_plot_no_save(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = SummaryPanelPlotter(fm)
    plotter.plot(
        detrended=_detrended(),
        candidate=_candidate(),
        bls_result=_bls_result(),
        tls_result=None,
        score=_score(),
        vetting=_vetting(),
        save=False,
    )
    assert list(tmp_path.glob("*.png")) == []


def test_plot_anomalous_candidate() -> None:
    fm = FigureManager()
    plotter = SummaryPanelPlotter(fm)
    fig = plotter.plot(
        detrended=_detrended(),
        candidate=_candidate(),
        bls_result=_bls_result(),
        tls_result=None,
        score=_score(anomalous=True),
        vetting=_vetting(),
        save=False,
    )
    # Anomali texti score panel'de olmali
    score_ax = fig.axes[1]
    texts = [t.get_text() for t in score_ax.texts]
    assert any("ANOMALY" in t for t in texts)


# ─────────────────────────────────────────────────────────────
# _draw_lightcurve
# ─────────────────────────────────────────────────────────────

def test_draw_lightcurve_basic() -> None:
    fig, ax = plt.subplots()
    fm = FigureManager()
    plotter = SummaryPanelPlotter(fm)
    plotter._draw_lightcurve(ax, _detrended(), _candidate(n_transits=3))
    # scatter -> collections
    assert len(ax.collections) >= 1
    assert "Flatten Flux" in ax.get_ylabel()
    plt.close(fig)


def test_draw_lightcurve_marks_transits() -> None:
    fig, ax = plt.subplots()
    fm = FigureManager()
    plotter = SummaryPanelPlotter(fm)
    plotter._draw_lightcurve(ax, _detrended(), _candidate(n_transits=4))
    # Transit pencereleri patch olarak
    span_like = [p for p in ax.patches if hasattr(p, "get_xy")]
    assert len(span_like) >= 4
    plt.close(fig)


def test_draw_lightcurve_no_transits() -> None:
    fig, ax = plt.subplots()
    fm = FigureManager()
    plotter = SummaryPanelPlotter(fm)
    plotter._draw_lightcurve(ax, _detrended(), _candidate(n_transits=0))
    span_like = [p for p in ax.patches if hasattr(p, "get_xy")]
    assert span_like == []
    plt.close(fig)


# ─────────────────────────────────────────────────────────────
# _draw_scorecard
# ─────────────────────────────────────────────────────────────

def test_draw_scorecard_basic() -> None:
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    plotter._draw_scorecard(ax, _score(), _vetting())
    texts = [t.get_text() for t in ax.texts]
    assert any("Sınıf B" in t for t in texts)
    assert any("72 / 100" in t for t in texts)
    assert any("FPP" in t for t in texts)
    plt.close(fig)


def test_draw_scorecard_fpp_none() -> None:
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    plotter._draw_scorecard(ax, _score(), _vetting(fpp=None))
    texts = [t.get_text() for t in ax.texts]
    assert any("NA" in t for t in texts)
    plt.close(fig)


def test_draw_scorecard_fpp_low() -> None:
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    plotter._draw_scorecard(ax, _score(), _vetting(fpp=0.05))
    texts = [t.get_text() for t in ax.texts]
    assert any("0.050" in t for t in texts)
    plt.close(fig)


def test_draw_scorecard_anomaly_flag() -> None:
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    plotter._draw_scorecard(ax, _score(anomalous=True), _vetting())
    texts = [t.get_text() for t in ax.texts]
    assert any("ANOMALY" in t for t in texts)
    plt.close(fig)


# ─────────────────────────────────────────────────────────────
# _draw_folded
# ─────────────────────────────────────────────────────────────

def test_draw_folded_with_tls() -> None:
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    plotter._draw_folded(ax, _candidate(), _tls_result())
    assert ax.get_xlim() == (0.3, 0.7)
    assert len(ax.collections) >= 1
    plt.close(fig)


def test_draw_folded_no_tls() -> None:
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    plotter._draw_folded(ax, _candidate(), None)
    # scatter yok ama baslik var
    assert "Faz" in ax.get_title()
    plt.close(fig)


def test_draw_folded_empty_data() -> None:
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    plotter._draw_folded(ax, _candidate(), _tls_result(with_data=False))
    assert "Faz" in ax.get_title()
    plt.close(fig)


def test_draw_folded_without_model() -> None:
    """tls_result var ama model_phase bos."""
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    plotter._draw_folded(ax, _candidate(), _tls_result(with_model=False))
    # Yine de cizim yapilmis olmali
    assert len(ax.collections) >= 1
    plt.close(fig)


# ─────────────────────────────────────────────────────────────
# _draw_bls
# ─────────────────────────────────────────────────────────────

def test_draw_bls_basic() -> None:
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    plotter._draw_bls(ax, _bls_result())
    assert ax.get_xscale() == "log"
    assert len(ax.lines) >= 1
    plt.close(fig)


def test_draw_bls_empty() -> None:
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    plotter._draw_bls(ax, _bls_result(with_data=False, with_best=False))
    assert ax.get_xscale() == "log"
    plt.close(fig)


def test_draw_bls_no_best() -> None:
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    plotter._draw_bls(ax, _bls_result(with_best=False))
    plt.close(fig)


# ─────────────────────────────────────────────────────────────
# _draw_residual_hist
# ─────────────────────────────────────────────────────────────

def test_draw_residual_hist_with_fit() -> None:
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    plotter._draw_residual_hist(ax, _detrended(), _fit_result())
    assert len(ax.patches) >= 1
    plt.close(fig)


def test_draw_residual_hist_no_fit() -> None:
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    plotter._draw_residual_hist(ax, _detrended(), None)
    assert len(ax.patches) >= 1
    plt.close(fig)


def test_draw_residual_hist_few_points() -> None:
    """<=5 nokta -> histogram cizilmez."""
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    det = _detrended(n=5)
    plotter._draw_residual_hist(ax, det, None)
    assert len(ax.patches) == 0
    plt.close(fig)


# ─────────────────────────────────────────────────────────────
# _draw_parameters
# ─────────────────────────────────────────────────────────────

def test_draw_parameters_with_fit() -> None:
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    plotter._draw_parameters(ax, _candidate(), _fit_result(success=True))
    texts = [t.get_text() for t in ax.texts]
    combined = " ".join(texts)
    assert "Rp/Rs" in combined
    assert "Yöntem" in combined
    plt.close(fig)


def test_draw_parameters_no_fit() -> None:
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    plotter._draw_parameters(ax, _candidate(), None)
    combined = " ".join(t.get_text() for t in ax.texts)
    assert "Periyot (TLS)" in combined
    assert "SNR" in combined
    plt.close(fig)


def test_draw_parameters_fit_unsuccessful() -> None:
    """fit_result.success=False ise candidate fallback."""
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    plotter._draw_parameters(ax, _candidate(), _fit_result(success=False))
    combined = " ".join(t.get_text() for t in ax.texts)
    assert "Periyot (TLS)" in combined
    plt.close(fig)


# ─────────────────────────────────────────────────────────────
# _draw_timing
# ─────────────────────────────────────────────────────────────

def test_draw_timing_enough_transits() -> None:
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    plotter._draw_timing(ax, _candidate(n_transits=6))
    assert len(ax.collections) >= 1
    assert "RMS" in " ".join(t.get_text() for t in ax.texts)
    plt.close(fig)


def test_draw_timing_insufficient() -> None:
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    plotter._draw_timing(ax, _candidate(n_transits=2))
    texts = " ".join(t.get_text() for t in ax.texts)
    assert "min. 3" in texts
    plt.close(fig)


# ─────────────────────────────────────────────────────────────
# _draw_stellar
# ─────────────────────────────────────────────────────────────

def test_draw_stellar_with_props() -> None:
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    plotter._draw_stellar(ax, _stellar(), _detrended())
    combined = " ".join(t.get_text() for t in ax.texts)
    assert "Teff" in combined
    assert "R★" in combined
    assert "TIC" in combined
    plt.close(fig)


def test_draw_stellar_without_props() -> None:
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    plotter._draw_stellar(ax, None, _detrended())
    combined = " ".join(t.get_text() for t in ax.texts)
    assert "Sektör" in combined
    assert "Gürültü" in combined
    assert "Kadans" in combined
    plt.close(fig)


def test_draw_stellar_meta_no_cadence() -> None:
    """meta'da CADENCE yoksa '?' gostermeli."""
    fig, ax = plt.subplots()
    plotter = SummaryPanelPlotter(FigureManager())
    det = _detrended()
    det.meta = {}
    plotter._draw_stellar(ax, None, det)
    combined = " ".join(t.get_text() for t in ax.texts)
    assert "?" in combined
    plt.close(fig)
