"""
PeriodogramPlotter birim testleri.

Kapsam
------
- plot_bls: bos veri, best=None, best dolu, harmonikler
- plot_tls: passed/rejected, reject_reason gosterimi
- plot_bls_tls_comparison: beraber, best=None
- save davranislari
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np
import pytest

from astrotransit.detection.bls_search import BLSPeak, BLSResult
from astrotransit.detection.tls_search import TLSResult
from astrotransit.visualization.base import FigureManager
from astrotransit.visualization.periodogram_plot import PeriodogramPlotter


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

def _bls_peak(period: float = 5.0, passed: bool = True) -> BLSPeak:
    return BLSPeak(
        period=period,
        period_err=0.01,
        duration=0.15,
        depth=0.005,
        t0=1.0,
        power=12.5,
        snr=8.0,
        depth_err=0.001,
        n_transits=4,
        transit_times=np.linspace(0.0, 20.0, 4),
        passed_threshold=passed,
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

    return BLSResult(
        target_id=target,
        sector=sector,
        best=_bls_peak() if with_best else None,
        all_peaks=[_bls_peak()] if with_best else [],
        periods_searched=periods,
        power_array=power,
        n_periods_searched=len(periods),
        has_candidate=with_best,
    )


def _tls_result(
    target: str = "TIC-100",
    sector: int = 1,
    passed: bool = True,
    reject_reason: str = "",
) -> TLSResult:
    n = 100
    return TLSResult(
        target_id=target,
        sector=sector,
        period=5.0,
        period_err=0.001,
        t0=1.0,
        duration=0.15,
        depth=0.005,
        rp_rs=0.08,
        sde=9.5,
        snr=8.0,
        odd_even_mismatch=0.5,
        transit_count=4,
        transit_times=np.linspace(0.0, 20.0, 4),
        transit_depths=np.full(4, 0.005),
        folded_phase=np.linspace(-0.5, 0.5, n),
        folded_flux=1.0 + 0.001 * np.random.default_rng(0).normal(size=n),
        model_phase=np.linspace(-0.5, 0.5, 200),
        model_flux=np.ones(200),
        passed_threshold=passed,
        reject_reason=reject_reason,
        false_alarm_probability=1e-5,
        raw_stats={},
    )


# ─────────────────────────────────────────────────────────────
# __init__
# ─────────────────────────────────────────────────────────────

def test_plotter_init() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    assert plotter.fm is fm


# ─────────────────────────────────────────────────────────────
# plot_bls
# ─────────────────────────────────────────────────────────────

def test_plot_bls_returns_figure() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_bls(_bls_result(), save=False)
    assert isinstance(fig, plt.Figure)
    assert len(fig.axes) == 1


def test_plot_bls_empty_data_shows_placeholder() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_bls(_bls_result(with_data=False, with_best=False), save=False)
    ax = fig.axes[0]
    texts = [t.get_text() for t in ax.texts]
    assert any("BLS verisi yok" in t for t in texts)


def test_plot_bls_empty_data_saves(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = PeriodogramPlotter(fm)
    plotter.plot_bls(_bls_result(with_data=False, with_best=False), save=True)
    files = list(tmp_path.glob("*bls.png"))
    assert len(files) == 1
    assert "_S01_bls.png" in files[0].name


def test_plot_bls_saves_with_periodogram_suffix(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = PeriodogramPlotter(fm)
    plotter.plot_bls(_bls_result(), save=True)
    files = list(tmp_path.glob("*periodogram.png"))
    assert len(files) == 1
    assert "_bls_periodogram.png" in files[0].name


def test_plot_bls_no_save(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = PeriodogramPlotter(fm)
    plotter.plot_bls(_bls_result(), save=False)
    assert list(tmp_path.glob("*.png")) == []


def test_plot_bls_labels_and_scale() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_bls(_bls_result(), save=False)
    ax = fig.axes[0]
    assert "Periyot" in ax.get_xlabel()
    assert "BLS" in ax.get_ylabel()
    # log scale x
    assert ax.get_xscale() == "log"


def test_plot_bls_title_contains_target_and_count() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_bls(_bls_result(target="TIC-999"), save=False)
    title = fig.axes[0].get_title()
    assert "TIC-999" in title
    assert "BLS" in title
    assert "500" in title  # n_periods_searched


def test_plot_bls_best_none_no_vline() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_bls(_bls_result(with_best=False), save=False)
    ax = fig.axes[0]
    # Best yoksa sadece esik axhline var, axvline yok
    # ax.lines listesinde vertical line'lar x degerleri esit
    vlines = [ln for ln in ax.lines if len(set(ln.get_xdata())) == 1]
    assert vlines == []


def test_plot_bls_with_best_has_vline() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_bls(_bls_result(with_best=True), save=False)
    ax = fig.axes[0]
    # En az bir vertical line (best.period) + harmonikler olabilir
    vlines = [ln for ln in ax.lines if len(set(ln.get_xdata())) == 1]
    assert len(vlines) >= 1


def test_plot_bls_watermark_added() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_bls(_bls_result(), save=False)
    texts = [t.get_text() for t in fig.axes[0].texts]
    assert any("AstroTransit" in t for t in texts)


def test_plot_bls_legend_created() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_bls(_bls_result(), save=False)
    assert fig.axes[0].get_legend() is not None


def test_plot_bls_safe_id_replaces_space(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = PeriodogramPlotter(fm)
    plotter.plot_bls(_bls_result(target="TIC 42"), save=True)
    files = list(tmp_path.glob("*.png"))
    assert len(files) == 1
    assert " " not in files[0].name


# ─────────────────────────────────────────────────────────────
# plot_tls
# ─────────────────────────────────────────────────────────────

def test_plot_tls_returns_figure() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_tls(_tls_result(), save=False)
    assert isinstance(fig, plt.Figure)
    assert len(fig.axes) == 1


def test_plot_tls_passed_shows_approved() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_tls(_tls_result(passed=True), save=False)
    texts = [t.get_text() for t in fig.axes[0].texts]
    assert any("ONAYLANDI" in t for t in texts)


def test_plot_tls_failed_shows_reject() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_tls(_tls_result(passed=False), save=False)
    texts = [t.get_text() for t in fig.axes[0].texts]
    assert any("BAŞARISIZ" in t for t in texts)


def test_plot_tls_failed_with_reason_shows_reason() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_tls(
        _tls_result(passed=False, reject_reason="SDE below threshold"),
        save=False,
    )
    texts = [t.get_text() for t in fig.axes[0].texts]
    assert any("SDE below threshold" in t for t in texts)


def test_plot_tls_passed_no_reason_no_reject_text() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_tls(_tls_result(passed=True), save=False)
    texts = [t.get_text() for t in fig.axes[0].texts]
    assert not any("Red:" in t for t in texts)


def test_plot_tls_saves(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = PeriodogramPlotter(fm)
    plotter.plot_tls(_tls_result(), save=True)
    files = list(tmp_path.glob("*tls_result.png"))
    assert len(files) == 1


def test_plot_tls_no_save(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = PeriodogramPlotter(fm)
    plotter.plot_tls(_tls_result(), save=False)
    assert list(tmp_path.glob("*.png")) == []


def test_plot_tls_title_contains_target() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_tls(_tls_result(target="TIC-777"), save=False)
    assert "TIC-777" in fig.axes[0].get_title()
    assert "TLS" in fig.axes[0].get_title()


def test_plot_tls_no_ticks() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_tls(_tls_result(), save=False)
    ax = fig.axes[0]
    assert len(ax.get_xticks()) == 0
    assert len(ax.get_yticks()) == 0


def test_plot_tls_watermark() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_tls(_tls_result(), save=False)
    texts = [t.get_text() for t in fig.axes[0].texts]
    assert any("AstroTransit" in t for t in texts)


# ─────────────────────────────────────────────────────────────
# plot_bls_tls_comparison
# ─────────────────────────────────────────────────────────────

def test_comparison_returns_figure() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_bls_tls_comparison(_bls_result(), _tls_result(), save=False)
    assert isinstance(fig, plt.Figure)
    assert len(fig.axes) == 2


def test_comparison_suptitle() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_bls_tls_comparison(
        _bls_result(target="TIC-55"),
        _tls_result(target="TIC-55"),
        save=False,
    )
    # fig._suptitle mevcut
    assert fig._suptitle is not None
    assert "TIC-55" in fig._suptitle.get_text()


def test_comparison_saves(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = PeriodogramPlotter(fm)
    plotter.plot_bls_tls_comparison(_bls_result(), _tls_result(), save=True)
    files = list(tmp_path.glob("*comparison.png"))
    assert len(files) == 1


def test_comparison_no_save(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    plotter = PeriodogramPlotter(fm)
    plotter.plot_bls_tls_comparison(_bls_result(), _tls_result(), save=False)
    assert list(tmp_path.glob("*.png")) == []


def test_comparison_with_empty_bls() -> None:
    """BLS verisi bos olsa da calismali (ax1 bos)."""
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_bls_tls_comparison(
        _bls_result(with_data=False, with_best=False),
        _tls_result(),
        save=False,
    )
    assert len(fig.axes) == 2


def test_comparison_with_best_none_still_plots() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_bls_tls_comparison(
        _bls_result(with_best=False),
        _tls_result(),
        save=False,
    )
    assert len(fig.axes) == 2


def test_comparison_period_match_text() -> None:
    """Ayni periyotlar ile 'Periyot uyumu' text gosterilmeli."""
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    bls = _bls_result(with_best=True)  # period=5.0
    tls = _tls_result()  # period=5.0
    fig = plotter.plot_bls_tls_comparison(bls, tls, save=False)
    ax2 = fig.axes[1]
    texts = [t.get_text() for t in ax2.texts]
    assert any("uyum" in t.lower() or "Periyot" in t for t in texts)


def test_comparison_status_texts() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_bls_tls_comparison(
        _bls_result(),
        _tls_result(passed=True),
        save=False,
    )
    texts = [t.get_text() for t in fig.axes[1].texts]
    assert any("ONAY" in t or "RED" in t for t in texts)


def test_comparison_labels_axes() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_bls_tls_comparison(_bls_result(), _tls_result(), save=False)
    ax1 = fig.axes[0]
    assert "Periyot" in ax1.get_xlabel()
    assert "BLS" in ax1.get_ylabel()
    assert ax1.get_xscale() == "log"


def test_comparison_watermark_on_ax2() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_bls_tls_comparison(_bls_result(), _tls_result(), save=False)
    texts = [t.get_text() for t in fig.axes[1].texts]
    assert any("AstroTransit" in t for t in texts)


def test_comparison_no_ticks_on_ax2() -> None:
    fm = FigureManager()
    plotter = PeriodogramPlotter(fm)
    fig = plotter.plot_bls_tls_comparison(_bls_result(), _tls_result(), save=False)
    ax2 = fig.axes[1]
    assert len(ax2.get_xticks()) == 0
    assert len(ax2.get_yticks()) == 0
