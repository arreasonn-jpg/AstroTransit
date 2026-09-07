"""
Faz katlanmış transit görselleştirme modülü.

TLS'nin faz katlanmış sonuçlarını ve
batman transit modelini birlikte gösterir.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import matplotlib.pyplot as plt
from loguru import logger

from astrotransit.visualization.base import FigureManager, Colors
from astrotransit.detection.cascade import CascadeCandidate
from astrotransit.detection.tls_search import TLSResult
from astrotransit.modeling.map_fit import MAPFitResult


class FoldedPlotter:
    """
    Faz katlanmış transit grafik üreticisi.

    Parameters
    ----------
    figure_manager : FigureManager
        Figür yöneticisi.
    """

    def __init__(self, figure_manager: FigureManager):
        self.fm = figure_manager

    def plot_folded_transit(
        self,
        candidate: CascadeCandidate,
        tls_result: Optional[TLSResult] = None,
        fit_result: Optional[MAPFitResult] = None,
        n_bins: int = 100,
        save: bool = True,
    ) -> plt.Figure:
        """
        Faz katlanmış transit eğrisi.

        Veriler faz uzayına katlanır, binlenir
        ve transit modeli üzerine çizilir.

        Parameters
        ----------
        candidate : CascadeCandidate
            Cascade tespit sonucu.
        tls_result : TLSResult, opsiyonel
            TLS faz ve flux dizileri için.
        fit_result : MAPFitResult, opsiyonel
            Model eğrisi için.
        n_bins : int
            Faz bin sayısı.
        save : bool
            Diske kaydet.

        Returns
        -------
        plt.Figure
        """

        target_id = candidate.target_id
        sector = candidate.sector

        fig, (ax1, ax2) = self.fm.create_figure(
            figsize=(12, 7),
            n_rows=2,
            n_cols=1,
            height_ratios=[3, 1],
        )

        fig.subplots_adjust(hspace=0.05)

        has_data = (
            tls_result is not None and
            len(tls_result.folded_phase) > 0 and
            len(tls_result.folded_flux) > 0
        )

        if has_data:
            # ── Ham faz noktalı görünüm ──
            ax1.scatter(
                tls_result.folded_phase,
                tls_result.folded_flux,
                s=3,
                color=Colors.FLUX,
                alpha=0.3,
                label="Faz Veri",
                rasterized=True,
                zorder=2,
            )

            # ── Binlenmiş veri ──
            bin_phase, bin_flux, bin_err = self._bin_folded(
                tls_result.folded_phase,
                tls_result.folded_flux,
                n_bins=n_bins,
            )

            ax1.errorbar(
                bin_phase,
                bin_flux,
                yerr=bin_err,
                fmt="o",
                color=Colors.DETRENDED,
                markersize=4,
                elinewidth=1,
                capsize=2,
                label=f"Binlenmiş (n={n_bins})",
                zorder=4,
            )

            # ── TLS model eğrisi ──
            if len(tls_result.model_phase) > 0:
                ax1.plot(
                    tls_result.model_phase,
                    tls_result.model_flux,
                    color=Colors.MODEL,
                    linewidth=2,
                    alpha=0.9,
                    label="TLS Modeli",
                    zorder=5,
                )

            # ── Residual ──
            if len(tls_result.model_phase) > 0:
                model_interp = np.interp(
                    bin_phase,
                    tls_result.model_phase,
                    tls_result.model_flux,
                )
                residuals = bin_flux - model_interp

                ax2.errorbar(
                    bin_phase,
                    residuals,
                    yerr=bin_err,
                    fmt="o",
                    color=Colors.RESIDUAL,
                    markersize=3,
                    elinewidth=1,
                    capsize=2,
                    rasterized=True,
                )
                ax2.axhline(
                    y=0,
                    color=Colors.TEXT_SECONDARY,
                    linewidth=0.8,
                    linestyle="--",
                    alpha=0.7,
                )

                # Residual RMS
                rms = float(np.std(residuals))
                ax2.set_ylabel(
                    f"Residual\nRMS={rms * 1e6:.0f}ppm",
                    color=Colors.TEXT_PRIMARY,
                    fontsize=8,
                )
        else:
            ax1.text(
                0.5, 0.5,
                "TLS faz verisi yok\n(TLS çalışmadı veya başarısız)",
                transform=ax1.transAxes,
                ha="center", va="center",
                color=Colors.TEXT_SECONDARY,
                fontsize=11,
            )

        # ── Transit merkez çizgisi ──
        ax1.axvline(
            x=0.5,
            color=Colors.TRANSIT_MARK,
            linewidth=0.8,
            linestyle=":",
            alpha=0.7,
        )
        ax2.axvline(
            x=0.5,
            color=Colors.TRANSIT_MARK,
            linewidth=0.8,
            linestyle=":",
            alpha=0.7,
        )

        # ── Referans çizgisi ──
        ax1.axhline(
            y=1.0,
            color=Colors.TEXT_SECONDARY,
            linewidth=0.8,
            linestyle="--",
            alpha=0.5,
        )

        # ── Parametre kutusu ──
        self._add_parameter_box(ax1, candidate, tls_result)

        # Eksen ayarları
        ax1.set_ylabel("Flatten Flux", color=Colors.TEXT_PRIMARY)
        ax1.set_xticklabels([])
        ax1.legend(loc="upper right")

        ax2.set_xlabel("Orbital Faz", color=Colors.TEXT_PRIMARY)
        if not has_data:
            ax2.set_ylabel("Residual", color=Colors.TEXT_PRIMARY)

        title = self.fm.format_target_title(
            target_id, sector,
            f"P={candidate.period:.4f}d"
        )
        ax1.set_title(title, color=Colors.TEXT_PRIMARY, fontweight="bold")

        ax1.set_xlim(0.25, 0.75)
        ax2.set_xlim(0.25, 0.75)

        self.fm.add_watermark(ax2)

        if save:
            safe_id = target_id.replace(" ", "_")
            self.fm.save(
                fig,
                f"{safe_id}_S{sector:02d}_folded",
            )

        return fig

    @staticmethod
    def _bin_folded(
        phase: np.ndarray,
        flux: np.ndarray,
        n_bins: int = 100,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Faz katlanmış veriyi binler.

        Returns
        -------
        tuple[np.ndarray, np.ndarray, np.ndarray]
            (bin_phase, bin_flux, bin_err)
        """

        bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
        bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])

        bin_flux = np.full(n_bins, np.nan)
        bin_err = np.full(n_bins, np.nan)

        for i in range(n_bins):
            mask = (phase >= bin_edges[i]) & (phase < bin_edges[i + 1])
            if mask.sum() >= 2:
                vals = flux[mask]
                bin_flux[i] = np.median(vals)
                bin_err[i] = np.std(vals) / np.sqrt(mask.sum())

        valid = np.isfinite(bin_flux)
        return (
            bin_centers[valid],
            bin_flux[valid],
            bin_err[valid],
        )

    @staticmethod
    def _add_parameter_box(
        ax: plt.Axes,
        candidate: CascadeCandidate,
        tls_result: Optional[TLSResult],
    ) -> None:
        """Sol üst köşeye parametre kutusu ekler."""

        lines = [
            f"P = {candidate.period:.5f} d",
            f"T₀ = {candidate.t0:.4f} BTJD",
            f"Derinlik = {candidate.depth * 1e6:.0f} ppm",
            f"Süre = {candidate.duration * 24:.2f} saat",
        ]

        if tls_result is not None:
            lines += [
                f"Rp/Rs = {tls_result.rp_rs:.4f}",
                f"SDE = {tls_result.sde:.2f}",
                f"SNR = {tls_result.snr:.2f}",
            ]

        text = "\n".join(lines)

        ax.text(
            0.02, 0.97, text,
            transform=ax.transAxes,
            ha="left", va="top",
            color=Colors.TEXT_PRIMARY,
            fontsize=8,
            family="monospace",
            bbox={
                "boxstyle": "round,pad=0.4",
                "facecolor": Colors.BG_PANEL,
                "edgecolor": Colors.BORDER,
                "alpha": 0.85,
            },
            zorder=10,
        )