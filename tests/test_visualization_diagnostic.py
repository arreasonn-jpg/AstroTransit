"""
DiagnosticPlotter birim testleri.

Kapsam
------
- plot_residuals: normal, az veri (<10), NaN'li veri, buyuk orneklem
- plot_transit_timing: yeterli/az transit
- plot_quality_scorecard: bilesenli/bilesensiz, cesitli FPP degerleri
- save davranislari
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np
import pytest

from astrotransit.detection.cascade import CascadeCandidate, CascadeStatus
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
from astrotransit.visualization.diagnostic_plots import DiagnosticPlotter


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

def _residuals_data(n: int = 500, seed: int = 0):
    rng = np.random.default_rng(seed)
    t = np.linspace(100.0, 120.0, n)
    r = rng.normal(0, 1e-3, size=n)
    return t, r


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


def _quality_score(
    target: str = "TIC-100",
    sector: int = 1,
    with_components: bool = True,
) -> QualityScore:
    components = []
    if with_components:
        components = [
            ScoreComponent(name="snr", raw_value=12.5, score=85.0, weight=0.20, contribution=17.0),
            ScoreComponent(name="vetting", raw_value=0.5, score=75.0, weight=0.30, contribution=22.5),
            ScoreComponent(name="residual", raw_value=300.0, score=60.0, weight=0.25, contribution=15.0),
            ScoreComponent(name="transit_quality", raw_value=1.0, score=70.0, weight=0.25, contribution=17.5),
        ]

    return QualityScore(
        target_id=target,
        sector=sector,
        total_score=72.0,
        candidate_class=CandidateClass.B,
        class_description="Yuksek olasilikli aday",
        components=components,
        is_anomalous=False,
        anomaly_flags=[],
        fpp=0.15,
        fpp_method="heuristic_v1",
        is_false_positive=False,
    )


def _vetting_report(
    target: str = "TIC-100",
    sector: int = 1,
    fpp: float | None = 0.15,
    with_tests: bool = True,
) -> VettingReport:
    tests = []
    if with_tests:
        tests = [
            VettingTest(
                name="odd_even_test",
                verdict=VettingVerdict.PASS,
                value=1.2,
                threshold=3.0,
            ),
            VettingTest(
                name="secondary_eclipse_test",
                verdict=VettingVerdict.WARN,
                value=2.5,
                threshold=2.0,
            ),
            VettingTest(
                name="centroid_shift_test",
                verdict=VettingVerdict.FAIL,
                value=5.0,
                threshold=2.0,
            ),
            VettingTest(
                name="depth_consistency_test",
                verdict=VettingVerdict.SKIP,
                value=0.0,
                threshold=1.0,
            ),
        ]

    return VettingReport(
        target_id=target,
        sector=sector,
        tests=tests,
        n_pass=1,
        n_fail=1,
        n_warn=1,
        false_positive_probability=fpp,
        is_false_positive=False,
    )


# ─────────────────────────────────────────────────────────────
# __init__
# ─────────────────────────────────────────────────────────────

def test_plotter_init() -> None:
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    assert plotter.fm is fm


# ─────────────────────────────────────────────────────────────
# plot_residuals
# ─────────────────────────────────────────────────────────────

def test_plot_residuals_returns_figure() -> None:
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    t, r = _residuals_data(500)
    fig = plotter.plot_residuals(t, r, "TIC-100", 1, save=False)
    assert isinstance(fig, plt.Figure)
    assert len(fig.axes) == 2


def test_plot_residuals_scatter_on_left() -> None:
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    t, r = _residuals_data(500)
    fig = plotter.plot_residuals(t, r, "TIC-100", 1, save=False)
    ax1 = fig.axes[0]
    assert len(ax1.collections) >= 1
    assert "Zaman" in ax1.get_xlabel()
    assert "Residual" in ax1.get_ylabel()


def test_plot_residuals_histogram_with_enough_data() -> None:
    """n>10 ise histogram ve normal fit eklenmeli."""
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    t, r = _residuals_data(500)
    fig = plotter.plot_residuals(t, r, "TIC-100", 1, save=False)
    ax2 = fig.axes[1]
    # histogram -> patches
    assert len(ax2.patches) >= 1


def test_plot_residuals_skips_hist_for_small_data() -> None:
    """n<=10 ise histogram eklenmez."""
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    t = np.linspace(100.0, 100.5, 8)
    r = np.random.default_rng(0).normal(0, 1e-3, size=8)
    fig = plotter.plot_residuals(t, r, "TIC-100", 1, save=False)
    ax2 = fig.axes[1]
    assert len(ax2.patches) == 0


def test_plot_residuals_nan_filtered() -> None:
    """NaN'ler temizlenip histogram uretilmeli."""
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    rng = np.random.default_rng(1)
    t = np.linspace(100.0, 120.0, 200)
    r = rng.normal(0, 1e-3, size=200)
    r[::10] = np.nan
    fig = plotter.plot_residuals(t, r, "TIC-100", 1, save=False)
    ax2 = fig.axes[1]
    assert len(ax2.patches) >= 1


def test_plot_residuals_suptitle() -> None:
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    t, r = _residuals_data(500)
    fig = plotter.plot_residuals(t, r, "TIC-42", 7, save=False)
    assert fig._suptitle is not None
    assert "TIC-42" in fig._suptitle.get_text()


def test_plot_residuals_saves(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = DiagnosticPlotter(fm)
    t, r = _residuals_data(500)
    plotter.plot_residuals(t, r, "TIC-100", 1, save=True)
    files = list(tmp_path.glob("*_residuals.png"))
    assert len(files) == 1


def test_plot_residuals_no_save(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = DiagnosticPlotter(fm)
    t, r = _residuals_data(500)
    plotter.plot_residuals(t, r, "TIC-100", 1, save=False)
    assert list(tmp_path.glob("*.png")) == []


def test_plot_residuals_watermark() -> None:
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    t, r = _residuals_data(500)
    fig = plotter.plot_residuals(t, r, "TIC-100", 1, save=False)
    texts = [t.get_text() for t in fig.axes[1].texts]
    assert any("AstroTransit" in txt for txt in texts)


def test_plot_residuals_shapiro_skipped_for_large_sample() -> None:
    """n>=5000 ise Shapiro atlanir (warning olmamali)."""
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    n = 6000
    t = np.linspace(100.0, 120.0, n)
    r = np.random.default_rng(2).normal(0, 1e-3, size=n)
    fig = plotter.plot_residuals(t, r, "TIC-100", 1, save=False)
    # sadece suptitle + watermark text'leri (normality text yok)
    ax2_texts = [t.get_text() for t in fig.axes[1].texts]
    assert not any("Shapiro" in txt for txt in ax2_texts)


def test_plot_residuals_safe_id(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = DiagnosticPlotter(fm)
    t, r = _residuals_data(500)
    plotter.plot_residuals(t, r, "TIC 100", 1, save=True)
    files = list(tmp_path.glob("*.png"))
    assert len(files) == 1
    assert " " not in files[0].name


# ─────────────────────────────────────────────────────────────
# plot_transit_timing
# ─────────────────────────────────────────────────────────────

def test_plot_timing_returns_figure() -> None:
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    fig = plotter.plot_transit_timing(_candidate(n_transits=5), save=False)
    assert isinstance(fig, plt.Figure)
    assert len(fig.axes) == 1


def test_plot_timing_insufficient_transits_shows_text() -> None:
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    fig = plotter.plot_transit_timing(_candidate(n_transits=2), save=False)
    ax = fig.axes[0]
    texts = [t.get_text() for t in ax.texts]
    assert any("yeterli transit yok" in t for t in texts)


def test_plot_timing_insufficient_saves_placeholder(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = DiagnosticPlotter(fm)
    plotter.plot_transit_timing(_candidate(n_transits=2), save=True)
    files = list(tmp_path.glob("*_timing.png"))
    assert len(files) == 1


def test_plot_timing_errorbar_present() -> None:
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    fig = plotter.plot_transit_timing(_candidate(n_transits=6), save=False)
    ax = fig.axes[0]
    # errorbar -> lines
    assert len(ax.lines) >= 1
    assert "O-C" in ax.get_ylabel()
    assert "Transit" in ax.get_xlabel()


def test_plot_timing_title_contains_rms() -> None:
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    fig = plotter.plot_transit_timing(_candidate(target="TIC-77"), save=False)
    title = fig.axes[0].get_title()
    assert "TIC-77" in title
    assert "RMS" in title


def test_plot_timing_saves(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = DiagnosticPlotter(fm)
    plotter.plot_transit_timing(_candidate(n_transits=5), save=True)
    files = list(tmp_path.glob("*_timing.png"))
    assert len(files) == 1


def test_plot_timing_no_save(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = DiagnosticPlotter(fm)
    plotter.plot_transit_timing(_candidate(n_transits=5), save=False)
    assert list(tmp_path.glob("*.png")) == []


def test_plot_timing_watermark() -> None:
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    fig = plotter.plot_transit_timing(_candidate(n_transits=5), save=False)
    texts = [t.get_text() for t in fig.axes[0].texts]
    assert any("AstroTransit" in t for t in texts)


# ─────────────────────────────────────────────────────────────
# plot_quality_scorecard
# ─────────────────────────────────────────────────────────────

def test_plot_scorecard_returns_figure() -> None:
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    fig = plotter.plot_quality_scorecard(
        _quality_score(), _vetting_report(), save=False,
    )
    assert isinstance(fig, plt.Figure)
    assert len(fig.axes) == 2


def test_plot_scorecard_bars_for_components() -> None:
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    fig = plotter.plot_quality_scorecard(
        _quality_score(with_components=True), _vetting_report(), save=False,
    )
    ax1 = fig.axes[0]
    # 4 bilesen -> 4 bar
    assert len(ax1.patches) == 4


def test_plot_scorecard_no_components() -> None:
    """components bos olsa da hata vermemeli."""
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    fig = plotter.plot_quality_scorecard(
        _quality_score(with_components=False), _vetting_report(), save=False,
    )
    assert isinstance(fig, plt.Figure)


def test_plot_scorecard_vetting_symbols() -> None:
    """Vetting testleri icin sembol + isim text'leri."""
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    fig = plotter.plot_quality_scorecard(
        _quality_score(), _vetting_report(), save=False,
    )
    ax2 = fig.axes[1]
    texts = [t.get_text() for t in ax2.texts]
    # ✓ ⚠ ✗ – sembolleri
    assert any("✓" in t for t in texts)
    assert any("✗" in t for t in texts)
    # FPP
    assert any("FPP" in t for t in texts)


def test_plot_scorecard_fpp_none() -> None:
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    fig = plotter.plot_quality_scorecard(
        _quality_score(), _vetting_report(fpp=None), save=False,
    )
    ax2 = fig.axes[1]
    texts = [t.get_text() for t in ax2.texts]
    assert any("NA" in t for t in texts)


def test_plot_scorecard_fpp_low() -> None:
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    fig = plotter.plot_quality_scorecard(
        _quality_score(), _vetting_report(fpp=0.05), save=False,
    )
    ax2 = fig.axes[1]
    texts = [t.get_text() for t in ax2.texts]
    assert any("0.050" in t for t in texts)


def test_plot_scorecard_fpp_high() -> None:
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    fig = plotter.plot_quality_scorecard(
        _quality_score(), _vetting_report(fpp=0.5), save=False,
    )
    assert isinstance(fig, plt.Figure)


def test_plot_scorecard_no_tests() -> None:
    """Vetting tests bos olsa da calisir."""
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    fig = plotter.plot_quality_scorecard(
        _quality_score(), _vetting_report(with_tests=False), save=False,
    )
    assert isinstance(fig, plt.Figure)


def test_plot_scorecard_suptitle() -> None:
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    fig = plotter.plot_quality_scorecard(
        _quality_score(target="TIC-55"), _vetting_report(target="TIC-55"), save=False,
    )
    assert fig._suptitle is not None
    assert "TIC-55" in fig._suptitle.get_text()


def test_plot_scorecard_saves(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = DiagnosticPlotter(fm)
    plotter.plot_quality_scorecard(
        _quality_score(), _vetting_report(), save=True,
    )
    files = list(tmp_path.glob("*_scorecard.png"))
    assert len(files) == 1


def test_plot_scorecard_no_save(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = DiagnosticPlotter(fm)
    plotter.plot_quality_scorecard(
        _quality_score(), _vetting_report(), save=False,
    )
    assert list(tmp_path.glob("*.png")) == []


def test_plot_scorecard_watermark() -> None:
    fm = FigureManager()
    plotter = DiagnosticPlotter(fm)
    fig = plotter.plot_quality_scorecard(
        _quality_score(), _vetting_report(), save=False,
    )
    texts = [t.get_text() for t in fig.axes[1].texts]
    assert any("AstroTransit" in t for t in texts)
