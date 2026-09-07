"""
Işık eğrisi görselleştirme modülü.

Ham, normalize ve detrend edilmiş
light curve karşılaştırma grafikleri üretir.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from loguru import logger

from astrotransit.visualization.base import (
    FigureManager, Colors, apply_astrotransit_style
)
from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve
from astrotransit.preprocessing.normalization import NormalizedLightCurve
from astrotransit.detection.cascade import CascadeCandidate


class LightCurvePlotter:
    """
    Light curve grafik üreticisi.

    Parameters
    ----------
    figure_manager : FigureManager
        Figür yöneticisi.
    """

    def __init__(self, figure_manager: FigureManager):
        self.fm = figure_manager

    def plot_raw_and_detrended(
        self,
        normalized: NormalizedLightCurve,
        detrended: DetrendedLightCurve,
        candidate: Optional[CascadeCandidate] = None,
        save: bool = True,
    ) -> plt.Figure:
        """
        Ham ve detrend edilmiş light curve karşılaştırması.

        Üst panel: normalize flux + trend eğrisi.
        Alt panel: detrend edilmiş flux.

        Parameters
        ----------
        normalized : NormalizedLightCurve
            Normalize edilmiş ham veri.
        detrended : DetrendedLightCurve
            Trend giderilmiş veri.
        candidate : CascadeCandidate, opsiyonel
            Transit zamanlarını işaretlemek için.
        save : bool
            Diske kaydet.

        Returns
        -------
        plt.Figure
        """

        target_id = detrended.target_id
        sector = detrended.sector

        fig, (ax1, ax2) = self.fm.create_figure(
            figsize=(15, 7),
            n_rows=2,
            n_cols=1,
            height_ratios=[1.2, 1],
        )

        fig.subplots_adjust(hspace=0.05)

        # ── Üst panel: ham + trend ──
        ax1.errorbar(
            normalized.time,
            normalized.flux,
            yerr=normalized.flux_err,
            fmt=".",
            color=Colors.FLUX,
            alpha=0.4,
            markersize=2,
            elinewidth=0.5,
            label="Normalize Flux",
            rasterized=True,
        )

        # Trend eğrisi
        ax1.plot(
            detrended.time,
            detrended.trend,
            color=Colors.TREND,
            linewidth=1.5,
            alpha=0.9,
            label="Trend (wotan)",
            zorder=5,
        )

        ax1.set_ylabel("Normalize Flux", color=Colors.TEXT_PRIMARY)
        ax1.set_xticklabels([])
        ax1.legend(loc="upper right", markerscale=3)

        title = self.fm.format_target_title(
            target_id, sector, f"yöntem: {detrended.method}"
        )
        ax1.set_title(title, color=Colors.TEXT_PRIMARY, fontweight="bold")

        # ── Alt panel: detrend ──
        ax2.errorbar(
            detrended.time,
            detrended.flux,
            yerr=detrended.flux_err,
            fmt=".",
            color=Colors.DETRENDED,
            alpha=0.4,
            markersize=2,
            elinewidth=0.5,
            label="Detrend Flux",
            rasterized=True,
        )

        # Transit zamanlarını işaretle
        if candidate is not None and len(candidate.transit_times) > 0:
            self._mark_transit_times(ax2, candidate)

        # Referans çizgisi
        ax2.axhline(
            y=1.0,
            color=Colors.TEXT_SECONDARY,
            linewidth=0.8,
            alpha=0.5,
            linestyle="--",
        )

        ax2.set_xlabel("Zaman (BTJD)", color=Colors.TEXT_PRIMARY)
        ax2.set_ylabel("Flatten Flux", color=Colors.TEXT_PRIMARY)

        noise_ppm = detrended.noise_ppm
        ax2.legend(
            title=f"RMS: {noise_ppm:.0f} ppm",
            loc="upper right",
            markerscale=3,
        )

        # Eksen sınırlarını hizala
        ax1.set_xlim(detrended.time[0], detrended.time[-1])
        ax2.set_xlim(detrended.time[0], detrended.time[-1])

        self.fm.add_watermark(ax2)

        if save:
            safe_id = target_id.replace(" ", "_")
            self.fm.save(
                fig,
                f"{safe_id}_S{sector:02d}_lightcurve",
            )

        return fig

    def plot_detrended_only(
        self,
        detrended: DetrendedLightCurve,
        candidate: Optional[CascadeCandidate] = None,
        save: bool = True,
    ) -> plt.Figure:
        """
        Yalnızca detrend edilmiş light curve.

        Parameters
        ----------
        detrended : DetrendedLightCurve
            Trend giderilmiş veri.
        candidate : CascadeCandidate, opsiyonel
            Transit işaretleri için.
        save : bool
            Diske kaydet.

        Returns
        -------
        plt.Figure
        """

        target_id = detrended.target_id
        sector = detrended.sector

        fig, ax = self.fm.create_figure(figsize=(15, 4))

        ax.errorbar(
            detrended.time,
            detrended.flux,
            yerr=detrended.flux_err,
            fmt=".",
            color=Colors.DETRENDED,
            alpha=0.4,
            markersize=2,
            elinewidth=0.5,
            rasterized=True,
            label="Flatten Flux",
        )

        ax.axhline(
            y=1.0,
            color=Colors.TEXT_SECONDARY,
            linewidth=0.8,
            alpha=0.5,
            linestyle="--",
        )

        if candidate is not None and len(candidate.transit_times) > 0:
            self._mark_transit_times(ax, candidate)

        ax.set_xlabel("Zaman (BTJD)", color=Colors.TEXT_PRIMARY)
        ax.set_ylabel("Flatten Flux", color=Colors.TEXT_PRIMARY)

        title = self.fm.format_target_title(
            target_id, sector,
            f"gürültü: {detrended.noise_ppm:.0f} ppm"
        )
        ax.set_title(title, color=Colors.TEXT_PRIMARY, fontweight="bold")
        ax.legend(loc="upper right", markerscale=3)

        self.fm.add_watermark(ax)

        if save:
            safe_id = target_id.replace(" ", "_")
            self.fm.save(
                fig,
                f"{safe_id}_S{sector:02d}_detrended",
            )

        return fig

    @staticmethod
    def _mark_transit_times(
        ax: plt.Axes,
        candidate: CascadeCandidate,
        alpha: float = 0.15,
    ) -> None:
        """
        Transit pencerelerini eksene işaretler.

        Her transit zamanı etrafında yarı saydam
        dikey bant çizer.
        """

        half_dur = candidate.duration / 2.0

        for t_transit in candidate.transit_times:
            ax.axvspan(
                t_transit - half_dur,
                t_transit + half_dur,
                color=Colors.TRANSIT_MARK,
                alpha=alpha,
                zorder=0,
            )

        # Efsanede sadece bir kez göster
        patch = mpatches.Patch(
            color=Colors.TRANSIT_MARK,
            alpha=alpha * 2,
            label=f"Transit ({len(candidate.transit_times)} geçiş)",
        )
        ax.legend(handles=[
            *ax.get_legend_handles_labels()[0],
            patch,
        ], loc="upper right", markerscale=3)