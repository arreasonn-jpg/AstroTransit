"""
FigureManager ve Colors birim testleri.

Strateji
--------
Matplotlib Agg backend kullanir; her test urettigi figuru plt.close()
ile temizler. Kontroller fig.axes, ax.texts, dosya varligi uzerinden
yapilir; gorsel piksel karsilastirmasi yapilmaz.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import pytest
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from astrotransit.visualization.base import (
    Colors,
    FigureManager,
    apply_astrotransit_style,
)


@pytest.fixture(autouse=True)
def _close_figures_after_test():
    """Her testten sonra tum acik figurleri kapat."""
    yield
    plt.close("all")


# ─────────────────────────────────────────────────────────────
# apply_astrotransit_style
# ─────────────────────────────────────────────────────────────

def test_apply_style_sets_dark_background() -> None:
    apply_astrotransit_style()
    assert plt.rcParams["figure.facecolor"] == "#0d1117"
    assert plt.rcParams["axes.facecolor"] == "#161b22"


def test_apply_style_sets_savefig_defaults() -> None:
    apply_astrotransit_style()
    assert plt.rcParams["savefig.dpi"] == 150
    assert plt.rcParams["savefig.facecolor"] == "#0d1117"
    assert plt.rcParams["savefig.bbox"] == "tight"


def test_apply_style_idempotent() -> None:
    apply_astrotransit_style()
    apply_astrotransit_style()
    assert plt.rcParams["axes.grid"] is True


# ─────────────────────────────────────────────────────────────
# Colors.class_color
# ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "cls,expected",
    [
        ("A", Colors.CLASS_A),
        ("B", Colors.CLASS_B),
        ("C", Colors.CLASS_C),
        ("D", Colors.CLASS_D),
        ("X", Colors.CLASS_X),
    ],
)
def test_class_color_known(cls: str, expected: str) -> None:
    assert Colors.class_color(cls) == expected


def test_class_color_lowercase() -> None:
    assert Colors.class_color("a") == Colors.CLASS_A
    assert Colors.class_color("x") == Colors.CLASS_X


def test_class_color_unknown_returns_secondary() -> None:
    assert Colors.class_color("Z") == Colors.TEXT_SECONDARY
    assert Colors.class_color("") == Colors.TEXT_SECONDARY


# ─────────────────────────────────────────────────────────────
# FigureManager.__init__
# ─────────────────────────────────────────────────────────────

def test_figure_manager_no_output_dir() -> None:
    fm = FigureManager()
    assert fm.output_dir is None
    assert fm.figure_format == "png"
    assert fm.dpi == 150


def test_figure_manager_creates_output_dir(tmp_path: Path) -> None:
    target = tmp_path / "plots" / "run01"
    fm = FigureManager(output_dir=target)
    assert fm.output_dir == target
    assert target.exists()
    assert target.is_dir()


def test_figure_manager_format_lowercase_and_strip_dot(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path, figure_format=".PDF")
    assert fm.figure_format == "pdf"


def test_figure_manager_custom_dpi(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path, dpi=72)
    assert fm.dpi == 72


def test_figure_manager_skip_style(tmp_path: Path) -> None:
    """apply_style=False cagrisi hata vermemeli."""
    fm = FigureManager(output_dir=tmp_path, apply_style=False)
    assert fm.output_dir == tmp_path


# ─────────────────────────────────────────────────────────────
# FigureManager.create_figure
# ─────────────────────────────────────────────────────────────

def test_create_figure_single_axes() -> None:
    fm = FigureManager()
    fig, ax = fm.create_figure()
    assert isinstance(fig, Figure)
    assert isinstance(ax, Axes)
    assert len(fig.axes) == 1


def test_create_figure_custom_figsize() -> None:
    fm = FigureManager()
    fig, _ = fm.create_figure(figsize=(8, 4))
    w, h = fig.get_size_inches()
    assert (float(w), float(h)) == (8.0, 4.0)


def test_create_figure_subplot_grid() -> None:
    fm = FigureManager()
    fig, axes = fm.create_figure(n_rows=2, n_cols=1)
    assert isinstance(fig, Figure)
    assert len(fig.axes) == 2
    # ndarray donmeli
    assert axes.shape == (2,)


def test_create_figure_grid_with_height_ratios() -> None:
    fm = FigureManager()
    fig, _ = fm.create_figure(
        n_rows=2, n_cols=1, height_ratios=[3, 1]
    )
    assert len(fig.axes) == 2


def test_create_figure_multirow_multicol() -> None:
    fm = FigureManager()
    fig, axes = fm.create_figure(n_rows=2, n_cols=2)
    assert len(fig.axes) == 4
    assert axes.shape == (2, 2)


# ─────────────────────────────────────────────────────────────
# FigureManager.save
# ─────────────────────────────────────────────────────────────

def test_save_without_output_dir_returns_none() -> None:
    fm = FigureManager()
    fig, _ = fm.create_figure()
    result = fm.save(fig, "test_fig")
    assert result is None
    # fig kapatilmis olmali
    assert not plt.fignum_exists(fig.number)


def test_save_creates_file(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    fig, _ = fm.create_figure()
    result = fm.save(fig, "astro_test")
    assert result is not None
    assert result.exists()
    assert result.suffix == ".png"
    assert result.name == "astro_test.png"


def test_save_with_subdir(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    fig, _ = fm.create_figure()
    result = fm.save(fig, "panel", subdir="sector_42")
    assert result is not None
    assert result.exists()
    assert result.parent.name == "sector_42"


def test_save_respects_format(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path, figure_format="svg")
    fig, _ = fm.create_figure()
    result = fm.save(fig, "svg_test")
    assert result is not None
    assert result.suffix == ".svg"


def test_save_close_after_false(tmp_path: Path) -> None:
    fm = FigureManager(output_dir=tmp_path)
    fig, _ = fm.create_figure()
    fm.save(fig, "keep_open", close_after=False)
    assert plt.fignum_exists(fig.number)
    plt.close(fig)


def test_save_handles_exception_gracefully(tmp_path: Path) -> None:
    """Gecersiz filename savefig hatasini yutar, hata firlatmaz."""
    fm = FigureManager(output_dir=tmp_path)
    fig, _ = fm.create_figure()
    # '/' karakteri alt dizin gibi yorumlanir ve muhtemelen basarisiz olur
    bad_name = "sub/dir/file"
    result = fm.save(fig, bad_name)
    # Hata yakalanmis olmali (log.error), exception cikmamali
    assert isinstance(result, Path)


# ─────────────────────────────────────────────────────────────
# FigureManager.add_watermark
# ─────────────────────────────────────────────────────────────

def test_add_watermark_creates_text() -> None:
    fm = FigureManager()
    _fig, ax = fm.create_figure()
    fm.add_watermark(ax, text="Test v1", alpha=0.5)
    assert len(ax.texts) == 1
    assert ax.texts[0].get_text() == "Test v1"


def test_add_watermark_default_text() -> None:
    _fig, ax = plt.subplots()
    FigureManager.add_watermark(ax)
    assert len(ax.texts) == 1
    assert "AstroTransit" in ax.texts[0].get_text()


def test_add_watermark_position_bottom_right() -> None:
    _fig, ax = plt.subplots()
    FigureManager.add_watermark(ax, text="W")
    txt = ax.texts[0]
    assert txt.get_ha() == "right"
    assert txt.get_va() == "bottom"


# ─────────────────────────────────────────────────────────────
# FigureManager.format_target_title
# ─────────────────────────────────────────────────────────────

def test_format_target_title_basic() -> None:
    title = FigureManager.format_target_title("TIC-123", 5)
    assert "TIC-123" in title
    assert "5" in title
    assert "Sektör" in title


def test_format_target_title_with_extra() -> None:
    title = FigureManager.format_target_title("TIC-123", 5, extra="MAP Fit")
    assert "TIC-123" in title
    assert "Sektör 5" in title
    assert "MAP Fit" in title


def test_format_target_title_empty_extra() -> None:
    a = FigureManager.format_target_title("TIC-1", 1)
    b = FigureManager.format_target_title("TIC-1", 1, extra="")
    assert a == b


def test_format_target_title_separator() -> None:
    title = FigureManager.format_target_title("TIC-1", 2, extra="X")
    # Standart separator "  |  "
    assert "  |  " in title
