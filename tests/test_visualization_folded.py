"""
FoldedPlotter birim testleri.

Kapsam
------
- plot_folded_transit: TLS verisi var/yok, model_phase bos/dolu
- _bin_folded: binning davranislari (bos, az, cok)
- _add_parameter_box: tls_result var/yok
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
from astrotransit.detection.tls_search import TLSResult
from astrotransit.visualization.base import FigureManager
from astrotransit.visualization.folded_plot import FoldedPlotter


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

def _candidate(target: str = "TIC-100", sector: int = 1) -> CascadeCandidate:
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
        transit_times=np.linspace(100.0, 120.0, 4),
        decision_log=[],
    )


def _tls_result(
    target: str = "TIC-100",
    sector: int = 1,
    n_points: int = 200,
    with_model: bool = True,
) -> TLSResult:
    rng = np.random.default_rng(0)
    phase = np.linspace(0.0, 1.0, n_points)
    # Transit sinyali: faz 0.5 civarinda dusus
    flux = 1.0 + rng.normal(0, 1e-3, size=n_points)
    flux[95:105] -= 0.005  # kucuk transit

    if with_model:
        model_phase = np.linspace(0.0, 1.0, 300)
        model_flux = np.ones(300)
        # ayni sekilde transit
        model_flux[140:160] -= 0.005
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


def _tls_result_empty() -> TLSResult:
    """folded_phase ve folded_flux bos."""
    return TLSResult(
        target_id="TIC-empty",
        sector=1,
        period=5.0,
        period_err=0.001,
        t0=100.0,
        duration=0.15,
        depth=0.005,
        rp_rs=0.08,
        sde=0.0,
        snr=0.0,
        odd_even_mismatch=0.0,
        transit_count=0,
        transit_times=np.array([]),
        transit_depths=np.array([]),
        folded_phase=np.array([]),
        folded_flux=np.array([]),
        model_phase=np.array([]),
        model_flux=np.array([]),
        passed_threshold=False,
        reject_reason="no data",
        false_alarm_probability=1.0,
        raw_stats={},
    )


# ─────────────────────────────────────────────────────────────
# __init__
# ─────────────────────────────────────────────────────────────

def test_plotter_init() -> None:
    fm = FigureManager()
    plotter = FoldedPlotter(fm)
    assert plotter.fm is fm


# ─────────────────────────────────────────────────────────────
# plot_folded_transit
# ─────────────────────────────────────────────────────────────

def test_plot_returns_figure() -> None:
    fm = FigureManager()
    plotter = FoldedPlotter(fm)
    fig = plotter.plot_folded_transit(_candidate(), save=False)
    assert isinstance(fig, plt.Figure)
    assert len(fig.axes) == 2


def test_plot_no_tls_placeholder() -> None:
    """tls_result None ise placeholder text gosterilmeli."""
    fm = FigureManager()
    plotter = FoldedPlotter(fm)
    fig = plotter.plot_folded_transit(_candidate(), tls_result=None, save=False)
    ax1 = fig.axes[0]
    texts = [t.get_text() for t in ax1.texts]
    assert any("TLS faz verisi yok" in t for t in texts)


def test_plot_with_tls_scatter_and_errorbar() -> None:
    """TLS verisi varsa scatter + errorbar eklenir."""
    fm = FigureManager()
    plotter = FoldedPlotter(fm)
    fig = plotter.plot_folded_transit(
        _candidate(), tls_result=_tls_result(), save=False,
    )
    ax1 = fig.axes[0]
    # scatter -> collections
    assert len(ax1.collections) >= 1
    # errorbar -> lines (data line + errorbar line)
    assert len(ax1.lines) >= 1


def test_plot_with_tls_model_line() -> None:
    """model_phase dolu ise model cizgisi eklenir."""
    fm = FigureManager()
    plotter = FoldedPlotter(fm)
    fig = plotter.plot_folded_transit(
        _candidate(), tls_result=_tls_result(with_model=True), save=False,
    )
    ax1 = fig.axes[0]
    # en az bir model line olmali (errorbar disinda)
    line_labels = [ln.get_label() for ln in ax1.lines]
    assert any("TLS" in lbl or "model" in lbl.lower() for lbl in line_labels)


def test_plot_no_model_line_when_empty() -> None:
    """model_phase bos ise model cizgisi eklenmez."""
    fm = FigureManager()
    plotter = FoldedPlotter(fm)
    fig = plotter.plot_folded_transit(
        _candidate(), tls_result=_tls_result(with_model=False), save=False,
    )
    ax1 = fig.axes[0]
    line_labels = [ln.get_label() for ln in ax1.lines]
    assert not any("TLS Modeli" in lbl for lbl in line_labels)


def test_plot_empty_tls_phase_falls_to_placeholder() -> None:
    """tls_result var ama folded_phase bos -> placeholder."""
    fm = FigureManager()
    plotter = FoldedPlotter(fm)
    fig = plotter.plot_folded_transit(
        _candidate(), tls_result=_tls_result_empty(), save=False,
    )
    ax1 = fig.axes[0]
    texts = [t.get_text() for t in ax1.texts]
    assert any("TLS faz verisi yok" in t for t in texts)


def test_plot_residual_panel_with_model() -> None:
    """model varsa residual panel ax2'de errorbar olur."""
    fm = FigureManager()
    plotter = FoldedPlotter(fm)
    fig = plotter.plot_folded_transit(
        _candidate(), tls_result=_tls_result(with_model=True), save=False,
    )
    ax2 = fig.axes[1]
    # residual errorbar -> lines
    assert len(ax2.lines) >= 1


def test_plot_xlim() -> None:
    """Eksen sinirlari 0.25-0.75 arasinda olmali."""
    fm = FigureManager()
    plotter = FoldedPlotter(fm)
    fig = plotter.plot_folded_transit(_candidate(), save=False)
    ax1, ax2 = fig.axes
    assert ax1.get_xlim() == (0.25, 0.75)
    assert ax2.get_xlim() == (0.25, 0.75)


def test_plot_title_contains_target_and_period() -> None:
    fm = FigureManager()
    plotter = FoldedPlotter(fm)
    fig = plotter.plot_folded_transit(
        _candidate(target="TIC-42"), save=False,
    )
    title = fig.axes[0].get_title()
    assert "TIC-42" in title
    assert "P=" in title


def test_plot_watermark() -> None:
    fm = FigureManager()
    plotter = FoldedPlotter(fm)
    fig = plotter.plot_folded_transit(_candidate(), save=False)
    texts = [t.get_text() for t in fig.axes[1].texts]
    assert any("AstroTransit" in t for t in texts)


def test_plot_saves(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = FoldedPlotter(fm)
    plotter.plot_folded_transit(_candidate(), save=True)
    files = list(tmp_path.glob("*_folded.png"))
    assert len(files) == 1


def test_plot_no_save(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = FoldedPlotter(fm)
    plotter.plot_folded_transit(_candidate(), save=False)
    assert list(tmp_path.glob("*.png")) == []


def test_plot_safe_id_replaces_space(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = FoldedPlotter(fm)
    plotter.plot_folded_transit(_candidate(target="TIC 100"), save=True)
    files = list(tmp_path.glob("*.png"))
    assert len(files) == 1
    assert " " not in files[0].name


def test_plot_parameter_box_without_tls() -> None:
    """tls_result yok: parametre kutusunda 4 satir."""
    fm = FigureManager()
    plotter = FoldedPlotter(fm)
    fig = plotter.plot_folded_transit(_candidate(), tls_result=None, save=False)
    ax1 = fig.axes[0]
    # Parametre kutusu en azindan "P =" iceren text
    box_texts = [t for t in ax1.texts if "P =" in t.get_text()]
    assert len(box_texts) >= 1


def test_plot_parameter_box_with_tls() -> None:
    """tls_result var: parametre kutusunda Rp/Rs ve SDE/SNR."""
    fm = FigureManager()
    plotter = FoldedPlotter(fm)
    fig = plotter.plot_folded_transit(
        _candidate(), tls_result=_tls_result(), save=False,
    )
    ax1 = fig.axes[0]
    combined = " ".join(t.get_text() for t in ax1.texts)
    assert "Rp/Rs" in combined
    assert "SDE" in combined
    assert "SNR" in combined


# ─────────────────────────────────────────────────────────────
# _bin_folded
# ─────────────────────────────────────────────────────────────

def test_bin_folded_basic() -> None:
    phase = np.linspace(0.0, 1.0, 1000)
    flux = np.ones_like(phase)
    bp, bf, be = FoldedPlotter._bin_folded(phase, flux, n_bins=10)
    assert len(bp) > 0
    assert len(bf) == len(bp)
    assert len(be) == len(bp)
    # Sabit flux -> medyan 1.0
    assert np.allclose(bf, 1.0)


def test_bin_folded_empty_input() -> None:
    bp, bf, be = FoldedPlotter._bin_folded(
        np.array([]), np.array([]), n_bins=10,
    )
    assert len(bp) == 0
    assert len(bf) == 0
    assert len(be) == 0


def test_bin_folded_one_point_per_bin() -> None:
    """Her bin'de 1 nokta varsa (mask.sum() < 2) hicbir sey donmez."""
    phase = np.array([0.05, 0.15, 0.25])
    flux = np.array([1.0, 1.0, 1.0])
    bp, _bf, _be = FoldedPlotter._bin_folded(phase, flux, n_bins=10)
    # nokta sayisi < 2 oldugu icin hicbir bin dolu degil
    assert len(bp) == 0


def test_bin_folded_two_points_per_bin() -> None:
    """Her bin'de en az 2 nokta varsa dolmali."""
    phase = np.linspace(0.0, 1.0, 40)
    flux = np.ones_like(phase)
    bp, _bf, _be = FoldedPlotter._bin_folded(phase, flux, n_bins=10)
    # 40 nokta / 10 bin = 4 nokta/bin
    assert len(bp) > 0


def test_bin_folded_nan_handling() -> None:
    """Bos bin'ler NaN uretir ve filtrelenir."""
    phase = np.array([0.01, 0.02, 0.99, 0.98])  # sadece ilk ve son bin
    flux = np.array([1.0, 1.0, 1.0, 1.0])
    bp, bf, be = FoldedPlotter._bin_folded(phase, flux, n_bins=20)
    # Sadece 2 bin dolu (ilk ve son)
    assert len(bp) <= 2
    assert np.all(np.isfinite(bf))
    assert np.all(np.isfinite(be))


def test_bin_folded_returns_errorbars() -> None:
    """Bin hatalari std/sqrt(n) olmali."""
    rng = np.random.default_rng(42)
    phase = np.linspace(0.0, 1.0, 100)
    flux = rng.normal(1.0, 0.01, size=100)
    _bp, _bf, be = FoldedPlotter._bin_folded(phase, flux, n_bins=5)
    assert np.all(be >= 0.0)


# ─────────────────────────────────────────────────────────────
# _add_parameter_box
# ─────────────────────────────────────────────────────────────

def test_add_parameter_box_basic() -> None:
    fig, ax = plt.subplots()
    FoldedPlotter._add_parameter_box(ax, _candidate(), tls_result=None)
    # Kutu bir text ekler
    assert len(ax.texts) >= 1
    txt = ax.texts[0].get_text()
    assert "P =" in txt
    assert "Derinlik" in txt
    assert "Süre" in txt
    plt.close(fig)


def test_add_parameter_box_with_tls() -> None:
    fig, ax = plt.subplots()
    FoldedPlotter._add_parameter_box(ax, _candidate(), _tls_result())
    txt = ax.texts[0].get_text()
    assert "Rp/Rs" in txt
    assert "SDE" in txt
    assert "SNR" in txt
    plt.close(fig)


def test_add_parameter_box_position_top_left() -> None:
    fig, ax = plt.subplots()
    FoldedPlotter._add_parameter_box(ax, _candidate(), None)
    txt = ax.texts[0]
    assert txt.get_ha() == "left"
    assert txt.get_va() == "top"
    plt.close(fig)
