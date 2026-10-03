"""
LightCurvePlotter birim testleri.

Strateji
--------
Dataclass'lar sentetik numpy array'leri ile olusturulur; plotter
cagrilir, donen Figure uzerinden eksen sayisi, cizgi sayisi, baslik,
etiket ve dosya cikisi dogrulanir.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np
import pytest

from astrotransit.detection.cascade import CascadeCandidate, CascadeStatus
from astrotransit.preprocessing.normalization import NormalizedLightCurve
from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve
from astrotransit.visualization.base import FigureManager
from astrotransit.visualization.lightcurve_plot import LightCurvePlotter


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


# ─────────────────────────────────────────────────────────────
# Synthetic data helpers
# ─────────────────────────────────────────────────────────────

def _normalized(target: str = "TIC-100", sector: int = 1, n: int = 200) -> NormalizedLightCurve:
    rng = np.random.default_rng(0)
    t = np.linspace(0.0, 20.0, n)
    flux = 1.0 + rng.normal(0, 1e-3, size=n)
    err = np.full(n, 1e-3)
    return NormalizedLightCurve(
        target_id=target,
        sector=sector,
        time=t,
        flux=flux,
        flux_err=err,
        norm_factor=1.0,
        method="median",
        meta={"CADENCE": "120s"},
    )


def _detrended(target: str = "TIC-100", sector: int = 1, n: int = 200) -> DetrendedLightCurve:
    rng = np.random.default_rng(1)
    t = np.linspace(0.0, 20.0, n)
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


def _candidate(target: str = "TIC-100", sector: int = 1, n_transits: int = 3) -> CascadeCandidate:
    # bls_result zorunlu; minimal bir dummy yeterli cunku plotter sadece
    # transit_times ve duration kullaniyor.
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
        t0=1.0,
        duration=0.2,
        depth=0.01,
        rp_rs=0.1,
        snr=10.0,
        sde=8.0,
        transit_times=np.linspace(0.0, 20.0, n_transits),
        decision_log=[],
    )


# ─────────────────────────────────────────────────────────────
# __init__
# ─────────────────────────────────────────────────────────────

def test_plotter_init() -> None:
    fm = FigureManager()
    plotter = LightCurvePlotter(fm)
    assert plotter.fm is fm


# ─────────────────────────────────────────────────────────────
# plot_raw_and_detrended
# ─────────────────────────────────────────────────────────────

def test_plot_raw_and_detrended_returns_figure() -> None:
    fm = FigureManager()
    plotter = LightCurvePlotter(fm)
    fig = plotter.plot_raw_and_detrended(
        _normalized(), _detrended(), save=False,
    )
    assert isinstance(fig, plt.Figure)
    assert len(fig.axes) == 2


def test_plot_raw_and_detrended_no_save(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = LightCurvePlotter(fm)
    plotter.plot_raw_and_detrended(_normalized(), _detrended(), save=False)
    files = list(tmp_path.glob("*.png"))
    assert files == []


def test_plot_raw_and_detrended_saves_file(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = LightCurvePlotter(fm)
    plotter.plot_raw_and_detrended(_normalized(), _detrended(), save=True)
    files = list(tmp_path.glob("*.png"))
    assert len(files) == 1
    assert "TIC-100" in files[0].name
    assert "_S01_lightcurve" in files[0].name


def test_plot_raw_and_detrended_title_contains_target() -> None:
    fm = FigureManager()
    plotter = LightCurvePlotter(fm)
    fig = plotter.plot_raw_and_detrended(
        _normalized(target="TIC-999"), _detrended(target="TIC-999"),
        save=False,
    )
    title = fig.axes[0].get_title()
    assert "TIC-999" in title
    assert "biweight" in title


def test_plot_raw_and_detrended_labels() -> None:
    fm = FigureManager()
    plotter = LightCurvePlotter(fm)
    fig = plotter.plot_raw_and_detrended(_normalized(), _detrended(), save=False)
    ax1, ax2 = fig.axes
    assert "Normalize Flux" in ax1.get_ylabel()
    assert "Flatten Flux" in ax2.get_ylabel()
    assert "BTJD" in ax2.get_xlabel()


def test_plot_raw_and_detrended_xlim_matches_data() -> None:
    fm = FigureManager()
    plotter = LightCurvePlotter(fm)
    det = _detrended()
    fig = plotter.plot_raw_and_detrended(_normalized(), det, save=False)
    ax1, ax2 = fig.axes
    xlim1 = ax1.get_xlim()
    xlim2 = ax2.get_xlim()
    assert xlim1 == pytest.approx((det.time[0], det.time[-1]))
    assert xlim2 == pytest.approx((det.time[0], det.time[-1]))


def test_plot_raw_and_detrended_with_candidate_marks_transits() -> None:
    fm = FigureManager()
    plotter = LightCurvePlotter(fm)
    cand = _candidate(n_transits=4)
    fig = plotter.plot_raw_and_detrended(
        _normalized(), _detrended(), candidate=cand, save=False,
    )
    # Transit zamanlari icin axvspan patch'leri eklenmis olmali
    ax2 = fig.axes[1]
    patches = [p for p in ax2.patches if hasattr(p, "get_xy")]
    assert len(patches) >= 4


def test_plot_raw_and_detrended_no_candidate_no_patches() -> None:
    fm = FigureManager()
    plotter = LightCurvePlotter(fm)
    fig = plotter.plot_raw_and_detrended(
        _normalized(), _detrended(), candidate=None, save=False,
    )
    ax2 = fig.axes[1]
    # Sadece axhline var, axvspan patch'i yok
    span_like = [p for p in ax2.patches if hasattr(p, "get_xy")]
    assert span_like == []


def test_plot_raw_and_detrended_watermark_added() -> None:
    fm = FigureManager()
    plotter = LightCurvePlotter(fm)
    fig = plotter.plot_raw_and_detrended(_normalized(), _detrended(), save=False)
    ax2 = fig.axes[1]
    texts = [t.get_text() for t in ax2.texts]
    assert any("AstroTransit" in t for t in texts)


def test_plot_raw_and_detrended_safe_id_replaces_space(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = LightCurvePlotter(fm)
    plotter.plot_raw_and_detrended(
        _normalized(target="TIC 100"), _detrended(target="TIC 100"),
        save=True,
    )
    files = list(tmp_path.glob("*.png"))
    assert len(files) == 1
    assert " " not in files[0].name


# ─────────────────────────────────────────────────────────────
# plot_detrended_only
# ─────────────────────────────────────────────────────────────

def test_plot_detrended_only_returns_figure() -> None:
    fm = FigureManager()
    plotter = LightCurvePlotter(fm)
    fig = plotter.plot_detrended_only(_detrended(), save=False)
    assert isinstance(fig, plt.Figure)
    assert len(fig.axes) == 1


def test_plot_detrended_only_saves(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = LightCurvePlotter(fm)
    plotter.plot_detrended_only(_detrended(), save=True)
    files = list(tmp_path.glob("*.png"))
    assert len(files) == 1
    assert "_S01_detrended" in files[0].name


def test_plot_detrended_only_no_save(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = LightCurvePlotter(fm)
    plotter.plot_detrended_only(_detrended(), save=False)
    assert list(tmp_path.glob("*.png")) == []


def test_plot_detrended_only_title_and_labels() -> None:
    fm = FigureManager()
    plotter = LightCurvePlotter(fm)
    fig = plotter.plot_detrended_only(_detrended(target="TIC-500"), save=False)
    ax = fig.axes[0]
    assert "TIC-500" in ax.get_title()
    assert "gürültü" in ax.get_title()
    assert "BTJD" in ax.get_xlabel()
    assert "Flatten Flux" in ax.get_ylabel()


def test_plot_detrended_only_with_candidate() -> None:
    fm = FigureManager()
    plotter = LightCurvePlotter(fm)
    cand = _candidate(n_transits=3)
    fig = plotter.plot_detrended_only(_detrended(), candidate=cand, save=False)
    ax = fig.axes[0]
    span_like = [p for p in ax.patches if hasattr(p, "get_xy")]
    assert len(span_like) >= 3


def test_plot_detrended_only_watermark() -> None:
    fm = FigureManager()
    plotter = LightCurvePlotter(fm)
    fig = plotter.plot_detrended_only(_detrended(), save=False)
    texts = [t.get_text() for t in fig.axes[0].texts]
    assert any("AstroTransit" in t for t in texts)


# ─────────────────────────────────────────────────────────────
# _mark_transit_times
# ─────────────────────────────────────────────────────────────

def test_mark_transit_times_adds_spans() -> None:
    fig, ax = plt.subplots()
    cand = _candidate(n_transits=5)
    LightCurvePlotter._mark_transit_times(ax, cand)
    spans = [p for p in ax.patches if hasattr(p, "get_xy")]
    assert len(spans) == 5
    plt.close(fig)


def test_mark_transit_times_uses_duration() -> None:
    fig, ax = plt.subplots()
    cand = _candidate(n_transits=1)
    cand.duration = 0.4
    LightCurvePlotter._mark_transit_times(ax, cand)
    spans = [p for p in ax.patches if hasattr(p, "get_xy")]
    assert len(spans) == 1
    # Genislik ~ duration olmali
    _x0, _y0 = spans[0].get_xy()
    w = spans[0].get_width()
    assert w == pytest.approx(0.4, rel=1e-6)
    plt.close(fig)


def test_mark_transit_times_zero_transits() -> None:
    """transit_times bos ise sadece legend patch eklenir, span yok."""
    fig, ax = plt.subplots()
    cand = _candidate(n_transits=0)
    LightCurvePlotter._mark_transit_times(ax, cand)
    spans = [p for p in ax.patches if hasattr(p, "get_xy")]
    assert spans == []
    plt.close(fig)


def test_mark_transit_times_legend_created() -> None:
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1], label="prev")
    cand = _candidate(n_transits=2)
    LightCurvePlotter._mark_transit_times(ax, cand)
    legend = ax.get_legend()
    assert legend is not None
    labels = [t.get_text() for t in legend.get_texts()]
    assert any("Transit" in lbl for lbl in labels)
    plt.close(fig)
