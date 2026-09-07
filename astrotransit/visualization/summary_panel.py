"""
Çok panelli özet görselleştirme modülü.

Bir transit adayı için tüm kritik grafikleri
tek bir büyük figürde birleştirir.

Panel düzeni (3×3):
    [1] Detrend LC       [2] BLS Peridog.    [3] Skor Kartı
    [4] Faz Katlanmış    [5] Residual        [6] TLS Özet
    [7] Parametre Kutusu [8] Timing (O-C)    [9] Yıldız Bilgisi
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from loguru import logger

from astrotransit.visualization.base import FigureManager, Colors
from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve
from astrotransit.detection.cascade import CascadeCandidate
from astrotransit.detection.bls_search import BLSResult
from astrotransit.detection.tls_search import TLSResult
from astrotransit.quality.scorer import QualityScore
from astrotransit.quality.vetting import VettingReport
from astrotransit.modeling.map_fit import MAPFitResult


class SummaryPanelPlotter:
    """
    Çok panelli özet grafik üreticisi.

    Tüm kritik grafikleri tek figürde
    sunan kapsamlı özet paneli oluşturur.

    Parameters
    ----------
    figure_manager : FigureManager
        Figür yöneticisi.
    """

    def __init__(self, figure_manager: FigureManager):
        self.fm = figure_manager

    def plot(
        self,
        detrended: DetrendedLightCurve,
        candidate: CascadeCandidate,
        bls_result: BLSResult,
        tls_result: Optional[TLSResult],
        score: QualityScore,
        vetting: VettingReport,
        fit_result: Optional[MAPFitResult] = None,
        stellar_props=None,
        save: bool = True,
    ) -> plt.Figure:
        """
        Kapsamlı özet paneli oluşturur.

        Parameters
        ----------
        detrended : DetrendedLightCurve
            Trend giderilmiş light curve.
        candidate : CascadeCandidate
            Cascade tespit sonucu.
        bls_result : BLSResult
            BLS arama sonucu.
        tls_result : TLSResult, opsiyonel
            TLS doğrulama sonucu.
        score : QualityScore
            Kalite skoru.
        vetting : VettingReport
            Vetting raporu.
        fit_result : MAPFitResult, opsiyonel
            MAP fit sonucu.
        stellar_props : opsiyonel
            Yıldız özellikleri.
        save : bool
            Diske kaydet.

        Returns
        -------
        plt.Figure
        """

        target_id = candidate.target_id
        sector = candidate.sector

        logger.debug(
            f"Özet panel oluşturuluyor — "
            f"{target_id} sektör {sector}"
        )

        # ── Figür ve GridSpec ──
        fig = plt.figure(figsize=(20, 14))
        fig.patch.set_facecolor(Colors.BG_DARK)

        gs = gridspec.GridSpec(
            3, 3,
            figure=fig,
            hspace=0.38,
            wspace=0.32,
            left=0.06, right=0.97,
            top=0.93, bottom=0.06,
        )

        ax_lc = fig.add_subplot(gs[0, :2])        # [0,0:2] Detrend LC
        ax_score = fig.add_subplot(gs[0, 2])       # [0,2]   Skor
        ax_fold = fig.add_subplot(gs[1, 0])        # [1,0]   Faz katlanmış
        ax_bls = fig.add_subplot(gs[1, 1])         # [1,1]   BLS
        ax_resid = fig.add_subplot(gs[1, 2])       # [1,2]   Residual hist
        ax_params = fig.add_subplot(gs[2, 0])      # [2,0]   Parametre kutusu
        ax_timing = fig.add_subplot(gs[2, 1])      # [2,1]   Timing O-C
        ax_stellar = fig.add_subplot(gs[2, 2])     # [2,2]   Yıldız bilgisi

        # ── Panel 1: Detrend Light Curve ──
        self._draw_lightcurve(ax_lc, detrended, candidate)

        # ── Panel 2: Skor Kartı ──
        self._draw_scorecard(ax_score, score, vetting)

        # ── Panel 3: Faz Katlanmış ──
        self._draw_folded(ax_fold, candidate, tls_result)

        # ── Panel 4: BLS Periodogram ──
        self._draw_bls(ax_bls, bls_result)

        # ── Panel 5: Residual Histogram ──
        self._draw_residual_hist(ax_resid, detrended, fit_result)

        # ── Panel 6: Parametre Kutusu ──
        self._draw_parameters(ax_params, candidate, fit_result)

        # ── Panel 7: Timing O-C ──
        self._draw_timing(ax_timing, candidate)

        # ── Panel 8: Yıldız Bilgisi ──
        self._draw_stellar(ax_stellar, stellar_props, detrended)

        # ── Ana Başlık ──
        fpp = vetting.false_positive_probability
        fpp_text = "NA" if fpp is None else f"{fpp:.3f}"
        class_color = Colors.class_color(score.candidate_class.value)
        fig.suptitle(
            f"{target_id}  |  Sektör {sector}  |  "
            f"Sınıf {score.candidate_class.value}  |  "
            f"Skor: {score.total_score:.0f}/100  |  "
            f"FPP: {fpp_text}",
            color=class_color,
            fontsize=13,
            fontweight="bold",
            y=0.97,
        )

        # ── Filigran ──
        fig.text(
            0.99, 0.01,
            "AstroTransit v0.1",
            ha="right", va="bottom",
            color=Colors.TEXT_SECONDARY,
            fontsize=7,
            alpha=0.3,
            style="italic",
        )

        if save:
            safe_id = target_id.replace(" ", "_")
            self.fm.save(
                fig,
                f"{safe_id}_S{sector:02d}_summary",
            )

        return fig

    # ──────────────────────────────────────
    # Panel çizim metodları
    # ──────────────────────────────────────

    def _draw_lightcurve(
        self,
        ax: plt.Axes,
        detrended: DetrendedLightCurve,
        candidate: CascadeCandidate,
    ) -> None:
        """Detrend light curve paneli."""

        ax.scatter(
            detrended.time,
            detrended.flux,
            s=2,
            color=Colors.DETRENDED,
            alpha=0.35,
            rasterized=True,
            label="Flatten Flux",
        )

        # Transit pencereleri
        if len(candidate.transit_times) > 0:
            half_dur = candidate.duration / 2.0
            for t_t in candidate.transit_times:
                ax.axvspan(
                    t_t - half_dur,
                    t_t + half_dur,
                    color=Colors.TRANSIT_MARK,
                    alpha=0.12,
                )

        ax.axhline(y=1.0, color=Colors.TEXT_SECONDARY,
                   linewidth=0.6, linestyle="--", alpha=0.5)

        ax.set_ylabel("Flatten Flux", color=Colors.TEXT_PRIMARY, fontsize=8)
        ax.set_xlabel("Zaman (BTJD)", color=Colors.TEXT_PRIMARY, fontsize=8)
        ax.set_title(
            f"Detrend Light Curve  |  {detrended.noise_ppm:.0f} ppm",
            color=Colors.TEXT_PRIMARY, fontsize=9, fontweight="bold",
        )

    def _draw_scorecard(
        self,
        ax: plt.Axes,
        score: QualityScore,
        vetting: VettingReport,
    ) -> None:
        """Skor kartı paneli."""

        ax.set_xticks([])
        ax.set_yticks([])

        class_color = Colors.class_color(score.candidate_class.value)

        # Büyük sınıf ikonu
        ax.text(
            0.5, 0.78,
            f"Sınıf {score.candidate_class.value}",
            transform=ax.transAxes,
            ha="center", va="center",
            color=class_color,
            fontsize=26,
            fontweight="bold",
        )

        # Toplam skor
        ax.text(
            0.5, 0.60,
            f"{score.total_score:.0f} / 100",
            transform=ax.transAxes,
            ha="center", va="center",
            color=Colors.TEXT_PRIMARY,
            fontsize=16,
        )

        # FPP
        fpp = vetting.false_positive_probability
        fpp_text = "NA" if fpp is None else f"{fpp:.3f}"
        fpp_color = (
            Colors.CLASS_A if fpp is not None and fpp < 0.1 else
            Colors.CLASS_C if fpp is not None and fpp < 0.3 else
            Colors.TEXT_SECONDARY if fpp is None else
            Colors.CLASS_D
        )
        ax.text(
            0.5, 0.44,
            f"FPP: {fpp_text}",
            transform=ax.transAxes,
            ha="center", va="center",
            color=fpp_color,
            fontsize=11,
        )

        # Vetting özeti
        ax.text(
            0.5, 0.28,
            f"✓{vetting.n_pass}  ⚠{vetting.n_warn}  ✗{vetting.n_fail}",
            transform=ax.transAxes,
            ha="center", va="center",
            color=Colors.TEXT_SECONDARY,
            fontsize=10,
        )

        # Anomali bayrağı
        if score.is_anomalous:
            ax.text(
                0.5, 0.12,
                "⚡ ANOMALY",
                transform=ax.transAxes,
                ha="center", va="center",
                color=Colors.CLASS_X,
                fontsize=10,
                fontweight="bold",
            )

        ax.set_title("Kalite", color=Colors.TEXT_PRIMARY,
                     fontsize=9, fontweight="bold")

    def _draw_folded(
        self,
        ax: plt.Axes,
        candidate: CascadeCandidate,
        tls_result: Optional[TLSResult],
    ) -> None:
        """Faz katlanmış transit paneli."""

        if (tls_result is not None and
                len(tls_result.folded_phase) > 0):

            ax.scatter(
                tls_result.folded_phase,
                tls_result.folded_flux,
                s=2,
                color=Colors.FLUX,
                alpha=0.25,
                rasterized=True,
            )

            # Binlenmiş
            from astrotransit.visualization.folded_plot import FoldedPlotter
            bp, bf, be = FoldedPlotter._bin_folded(
                tls_result.folded_phase,
                tls_result.folded_flux,
                n_bins=60,
            )
            ax.errorbar(bp, bf, yerr=be, fmt="o",
                        color=Colors.DETRENDED, markersize=3,
                        elinewidth=0.8, capsize=1)

            if len(tls_result.model_phase) > 0:
                ax.plot(
                    tls_result.model_phase,
                    tls_result.model_flux,
                    color=Colors.MODEL,
                    linewidth=1.5,
                )

        ax.axhline(y=1.0, color=Colors.TEXT_SECONDARY,
                   linewidth=0.6, linestyle="--", alpha=0.5)
        ax.set_xlim(0.3, 0.7)
        ax.set_xlabel("Faz", color=Colors.TEXT_PRIMARY, fontsize=8)
        ax.set_ylabel("Flux", color=Colors.TEXT_PRIMARY, fontsize=8)
        ax.set_title(
            f"Faz Katlanmış  |  P={candidate.period:.4f}d",
            color=Colors.TEXT_PRIMARY, fontsize=9, fontweight="bold",
        )

    def _draw_bls(
        self,
        ax: plt.Axes,
        bls_result: BLSResult,
    ) -> None:
        """BLS periodogram paneli."""

        if len(bls_result.periods_searched) > 0:
            ax.plot(
                bls_result.periods_searched,
                bls_result.power_array,
                color=Colors.BLS_POWER,
                linewidth=0.7,
                alpha=0.9,
                rasterized=True,
            )

            if bls_result.best is not None:
                ax.axvline(
                    x=bls_result.best.period,
                    color=Colors.PEAK_MARK,
                    linewidth=1.2,
                    linestyle="--",
                    alpha=0.9,
                )

        ax.axhline(y=7.0, color=Colors.TEXT_SECONDARY,
                   linewidth=0.6, linestyle="--", alpha=0.4)
        ax.set_xscale("log")
        ax.set_xlabel("Periyot (gün)", color=Colors.TEXT_PRIMARY, fontsize=8)
        ax.set_ylabel("BLS SDE", color=Colors.TEXT_PRIMARY, fontsize=8)
        ax.set_title("BLS Periodogram", color=Colors.TEXT_PRIMARY,
                     fontsize=9, fontweight="bold")

    def _draw_residual_hist(
        self,
        ax: plt.Axes,
        detrended: DetrendedLightCurve,
        fit_result: Optional[MAPFitResult],
    ) -> None:
        """Residual histogram paneli."""

        residuals = None

        if fit_result is not None:
            # Basit residual tahmini: detrended flux - 1.0
            residuals = (detrended.flux - 1.0) * 1e6

        if residuals is None:
            residuals = (detrended.flux - 1.0) * 1e6

        clean = residuals[np.isfinite(residuals)]

        if len(clean) > 5:
            n_bins = min(40, max(15, len(clean) // 50))
            ax.hist(
                clean,
                bins=n_bins,
                color=Colors.RESIDUAL,
                alpha=0.7,
                edgecolor=Colors.BORDER,
                density=True,
            )

            from scipy import stats as sp
            mu, sigma = sp.norm.fit(clean)
            x = np.linspace(clean.min(), clean.max(), 150)
            ax.plot(x, sp.norm.pdf(x, mu, sigma),
                    color=Colors.MODEL, linewidth=1.2)

        ax.set_xlabel("Residual (ppm)", color=Colors.TEXT_PRIMARY, fontsize=8)
        ax.set_ylabel("Yoğunluk", color=Colors.TEXT_PRIMARY, fontsize=8)
        ax.set_title("Residual Dağılımı", color=Colors.TEXT_PRIMARY,
                     fontsize=9, fontweight="bold")

    def _draw_parameters(
        self,
        ax: plt.Axes,
        candidate: CascadeCandidate,
        fit_result: Optional[MAPFitResult],
    ) -> None:
        """Parametre kutusu paneli."""

        ax.set_xticks([])
        ax.set_yticks([])

        lines = []

        if fit_result is not None and fit_result.success:
            lines = [
                ("Periyot", f"{fit_result.period:.6f} gün"),
                ("T₀", f"{fit_result.t0:.4f} BTJD"),
                ("Rp/Rs", f"{fit_result.rp_rs:.5f}"),
                ("b", f"{fit_result.impact_parameter:.4f}"),
                ("a/Rs", f"{fit_result.a_over_rs:.3f}"),
                ("i", f"{fit_result.inclination:.3f}°"),
                ("Rp", f"{fit_result.derived.planet_radius_rearth:.3f} Re"),
                ("Rp", f"{fit_result.derived.planet_radius_rjup:.4f} Rj"),
                ("a", f"{fit_result.derived.semi_major_axis_au:.5f} AU"),
                ("Teq", f"{fit_result.derived.equilibrium_temperature_k:.0f} K"),
                ("Log L", f"{fit_result.log_likelihood:.2f}"),
                ("Yöntem", fit_result.fit_method.upper()),
            ]
        else:
            lines = [
                ("Periyot (TLS)", f"{candidate.period:.6f} gün"),
                ("T₀", f"{candidate.t0:.4f} BTJD"),
                ("Rp/Rs", f"{candidate.rp_rs:.5f}"),
                ("Derinlik", f"{candidate.depth * 1e6:.0f} ppm"),
                ("Süre", f"{candidate.duration * 24:.3f} saat"),
                ("Transit N", f"{len(candidate.transit_times)}"),
                ("SNR", f"{candidate.snr:.2f}"),
                ("SDE", f"{candidate.sde:.2f}"),
                ("Durum", candidate.status.value),
            ]

        y = 0.96
        dy = 1.0 / (len(lines) + 1)

        for label, value in lines:
            ax.text(
                0.03, y, f"{label}:",
                transform=ax.transAxes,
                ha="left", va="top",
                color=Colors.TEXT_SECONDARY,
                fontsize=8,
            )
            ax.text(
                0.52, y, value,
                transform=ax.transAxes,
                ha="left", va="top",
                color=Colors.TEXT_PRIMARY,
                fontsize=8,
                fontweight="bold",
                family="monospace",
            )
            y -= dy

        ax.set_title("Parametreler", color=Colors.TEXT_PRIMARY,
                     fontsize=9, fontweight="bold")

    def _draw_timing(
        self,
        ax: plt.Axes,
        candidate: CascadeCandidate,
    ) -> None:
        """Transit zamanlama (O-C) paneli."""

        transit_times = candidate.transit_times

        if len(transit_times) < 3:
            ax.text(
                0.5, 0.5,
                f"N_transit={len(transit_times)}\n(min. 3 gerekli)",
                transform=ax.transAxes,
                ha="center", va="center",
                color=Colors.TEXT_SECONDARY,
                fontsize=9,
            )
        else:
            t0 = transit_times[0]
            n_vals = np.round(
                (transit_times - t0) / candidate.period
            ).astype(int)
            expected = t0 + n_vals * candidate.period
            oc = (transit_times - expected) * 1440

            ax.scatter(n_vals, oc, s=25,
                       color=Colors.FLUX, zorder=3)
            ax.plot(n_vals, oc, color=Colors.FLUX,
                    linewidth=0.8, alpha=0.5)
            ax.axhline(y=0, color=Colors.TEXT_SECONDARY,
                       linewidth=0.7, linestyle="--", alpha=0.6)

            rms = float(np.std(oc))
            ax.text(
                0.97, 0.05,
                f"RMS={rms:.1f}dk",
                transform=ax.transAxes,
                ha="right", va="bottom",
                color=Colors.TEXT_SECONDARY,
                fontsize=7,
            )

        ax.set_xlabel("Transit N", color=Colors.TEXT_PRIMARY, fontsize=8)
        ax.set_ylabel("O-C (dk)", color=Colors.TEXT_PRIMARY, fontsize=8)
        ax.set_title("Transit Zamanlama", color=Colors.TEXT_PRIMARY,
                     fontsize=9, fontweight="bold")

    def _draw_stellar(
        self,
        ax: plt.Axes,
        stellar_props,
        detrended: DetrendedLightCurve,
    ) -> None:
        """Yıldız bilgisi paneli."""

        ax.set_xticks([])
        ax.set_yticks([])

        if stellar_props is not None:
            lines = [
                ("TIC ID", f"{stellar_props.tic_id}"),
                ("Teff", f"{stellar_props.teff:.0f} K"),
                ("R★", f"{stellar_props.radius:.3f} R☉"),
                ("M★", f"{stellar_props.mass:.3f} M☉"),
                ("log g", f"{stellar_props.logg:.3f}"),
                ("Tmag", f"{stellar_props.tmag:.3f}"),
                ("RA", f"{stellar_props.ra:.5f}°"),
                ("Dec", f"{stellar_props.dec:.5f}°"),
                ("Kaynak", stellar_props.source),
            ]
        else:
            lines = [
                ("TIC ID", detrended.target_id),
                ("Sektör", str(detrended.sector)),
                ("N nokta", str(detrended.n_points)),
                ("Süre", f"{detrended.duration_days:.2f} gün"),
                ("Gürültü", f"{detrended.noise_ppm:.0f} ppm"),
                ("Kadans", f"{detrended.meta.get('CADENCE', '?')}"),
            ]

        y = 0.95
        dy = 0.10

        for label, value in lines:
            ax.text(
                0.03, y, f"{label}:",
                transform=ax.transAxes,
                ha="left", va="top",
                color=Colors.TEXT_SECONDARY,
                fontsize=8,
            )
            ax.text(
                0.50, y, str(value),
                transform=ax.transAxes,
                ha="left", va="top",
                color=Colors.TEXT_PRIMARY,
                fontsize=8,
                fontweight="bold",
                family="monospace",
            )
            y -= dy

        ax.set_title("Yıldız Bilgisi", color=Colors.TEXT_PRIMARY,
                     fontsize=9, fontweight="bold")