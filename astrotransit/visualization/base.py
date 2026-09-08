"""
Temel görselleştirme altyapısı.

Tüm grafik modülleri bu modülden türer.
Ortak stil, renk paleti, figür yönetimi
ve kaydetme işlemleri burada tanımlanır.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import matplotlib
matplotlib.use('Agg', force=True)
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.axes import Axes
from loguru import logger


# ──────────────────────────────────────
# Global stil ayarları
# ──────────────────────────────────────
def apply_astrotransit_style() -> None:
    """
    AstroTransit standart matplotlib stil ayarlarını uygular.

    Tüm grafiklerde tutarlı görünüm sağlar.
    """

    plt.rcParams.update({
        # Genel
        "figure.facecolor": "#0d1117",
        "axes.facecolor": "#161b22",
        "axes.edgecolor": "#30363d",
        "axes.labelcolor": "#e6edf3",
        "axes.titlecolor": "#e6edf3",
        "axes.grid": True,
        "axes.axisbelow": True,

        # Grid
        "grid.color": "#21262d",
        "grid.linewidth": 0.6,
        "grid.alpha": 0.8,

        # Tick
        "xtick.color": "#8b949e",
        "ytick.color": "#8b949e",
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "xtick.direction": "in",
        "ytick.direction": "in",

        # Yazı tipi
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.labelsize": 10,

        # Çizgi
        "lines.linewidth": 1.2,
        "lines.antialiased": True,

        # Efsane
        "legend.facecolor": "#161b22",
        "legend.edgecolor": "#30363d",
        "legend.labelcolor": "#e6edf3",
        "legend.fontsize": 8,
        "legend.framealpha": 0.9,

        # Figür
        "figure.dpi": 100,
        "savefig.dpi": 150,
        "savefig.facecolor": "#0d1117",
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.15,
    })


# ──────────────────────────────────────
# Renk paleti
# ──────────────────────────────────────
class Colors:
    """AstroTransit standart renk paleti."""

    # Ana renkler
    FLUX = "#58a6ff"           # Mavi — flux noktaları
    FLUX_ERR = "#1f6feb"       # Koyu mavi — hata çubuğu
    TREND = "#f0883e"          # Turuncu — trend
    DETRENDED = "#3fb950"      # Yeşil — detrend sonrası
    MODEL = "#ff7b72"          # Kırmızı — transit modeli
    RESIDUAL = "#bc8cff"       # Mor — residual

    # Transit işaretleyiciler
    TRANSIT_MARK = "#ffa657"   # Sarı — transit zamanları
    IN_TRANSIT = "#21262d"     # Koyu gri — transit penceresi

    # Periodogram
    BLS_POWER = "#58a6ff"
    TLS_POWER = "#3fb950"
    PEAK_MARK = "#f85149"

    # Arka plan ve metin
    BG_DARK = "#0d1117"
    BG_PANEL = "#161b22"
    TEXT_PRIMARY = "#e6edf3"
    TEXT_SECONDARY = "#8b949e"
    BORDER = "#30363d"

    # Sınıf renkleri
    CLASS_A = "#3fb950"        # Yeşil
    CLASS_B = "#58a6ff"        # Mavi
    CLASS_C = "#f0883e"        # Turuncu
    CLASS_D = "#8b949e"        # Gri
    CLASS_X = "#bc8cff"        # Mor

    @staticmethod
    def class_color(candidate_class: str) -> str:
        """Sınıf adına göre renk döndürür."""
        mapping = {
            "A": Colors.CLASS_A,
            "B": Colors.CLASS_B,
            "C": Colors.CLASS_C,
            "D": Colors.CLASS_D,
            "X": Colors.CLASS_X,
        }
        return mapping.get(candidate_class.upper(), Colors.TEXT_SECONDARY)


# ──────────────────────────────────────
# Figür yöneticisi
# ──────────────────────────────────────
class FigureManager:
    """
    Figür oluşturma ve kaydetme yöneticisi.

    Parameters
    ----------
    output_dir : Path
        Grafiklerin kaydedileceği dizin.
    figure_format : str
        Çıktı formatı. "png", "pdf", "svg".
    dpi : int
        Çözünürlük (DPI).
    apply_style : bool
        AstroTransit stilini uygula.
    """

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        figure_format: str = "png",
        dpi: int = 150,
        apply_style: bool = True,
    ):
        self.output_dir = Path(output_dir) if output_dir else None
        self.figure_format = figure_format.lower().lstrip(".")
        self.dpi = dpi

        if apply_style:
            apply_astrotransit_style()

        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.debug(
            f"FigureManager — format: {figure_format}, "
            f"dpi: {dpi}, "
            f"dizin: {output_dir}"
        )

    def create_figure(
        self,
        figsize: Tuple[float, float] = (14, 5),
        n_rows: int = 1,
        n_cols: int = 1,
        height_ratios: Optional[list] = None,
    ) -> Tuple[Figure, any]:
        """
        Standart figür ve eksen(ler) oluşturur.

        Parameters
        ----------
        figsize : tuple
            Figür boyutu (genişlik, yükseklik) inç.
        n_rows, n_cols : int
            Subplot ızgara boyutları.
        height_ratios : list, opsiyonel
            Satır yükseklik oranları.

        Returns
        -------
        tuple[Figure, Axes veya array]
            Figür ve eksen nesnesi/nesneleri.
        """

        if n_rows == 1 and n_cols == 1:
            fig, ax = plt.subplots(figsize=figsize)
            return fig, ax

        kwargs = {}
        if height_ratios:
            kwargs["height_ratios"] = height_ratios

        fig, axes = plt.subplots(
            n_rows, n_cols,
            figsize=figsize,
            gridspec_kw=kwargs,
        )
        return fig, axes

    def save(
        self,
        fig: Figure,
        filename: str,
        subdir: Optional[str] = None,
        close_after: bool = True,
    ) -> Optional[Path]:
        """
        Figürü diske kaydeder.

        Parameters
        ----------
        fig : Figure
            Kaydedilecek figür.
        filename : str
            Dosya adı (uzantısız).
        subdir : str, opsiyonel
            Alt dizin adı.
        close_after : bool
            Kaydettikten sonra figürü kapat.

        Returns
        -------
        Path veya None
            Kaydedilen dosya yolu.
        """

        if self.output_dir is None:
            if close_after:
                plt.close(fig)
            return None

        save_dir = self.output_dir
        if subdir:
            save_dir = self.output_dir / subdir
            save_dir.mkdir(parents=True, exist_ok=True)

        filepath = save_dir / f"{filename}.{self.figure_format}"

        try:
            fig.savefig(
                filepath,
                dpi=self.dpi,
                format=self.figure_format,
            )
            logger.debug(f"Grafik kaydedildi: {filepath.name}")
        except Exception as e:
            logger.error(f"Grafik kaydetme hatası: {e}")
        finally:
            if close_after:
                plt.close(fig)

        return filepath

    @staticmethod
    def add_watermark(
        ax: Axes,
        text: str = "AstroTransit v0.1",
        alpha: float = 0.15,
    ) -> None:
        """Eksene filigran ekler."""

        ax.text(
            0.99, 0.01, text,
            transform=ax.transAxes,
            fontsize=7,
            color=Colors.TEXT_SECONDARY,
            alpha=alpha,
            ha="right", va="bottom",
            style="italic",
        )

    @staticmethod
    def format_target_title(
        target_id: str,
        sector: int,
        extra: str = "",
    ) -> str:
        """Standart başlık formatı üretir."""

        title = f"{target_id}  |  Sektör {sector}"
        if extra:
            title += f"  |  {extra}"
        return title