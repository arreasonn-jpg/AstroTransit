"""
Tanısal görselleştirme modülü.

Residual dağılımı, transit zamanlama,
derinlik varyansı ve kalite özeti grafikleri.
"""

from __future__ import annotations


import numpy as np
import matplotlib.pyplot as plt
from scipy import stats as scipy_stats

from astrotransit.visualization.base import FigureManager, Colors
from astrotransit.detection.cascade import CascadeCandidate
from astrotransit.quality.vetting import VettingReport
from astrotransit.quality.scorer import QualityScore


class DiagnosticPlotter:
    """
    Tanısal grafik üreticisi.

    Parameters
    ----------
    figure_manager : FigureManager
        Figür yöneticisi.
    """

    def __init__(self, figure_manager: FigureManager):
        self.fm = figure_manager

    def plot_residuals(
        self,
        time: np.ndarray,
        residuals: np.ndarray,
        target_id: str,
        sector: int,
        save: bool = True,
    ) -> plt.Figure:
        """
        Residual zaman serisi ve dağılım grafiği.

        Sol: residual vs zaman.
        Sağ: residual histogram + normal fit.

        Parameters
        ----------
        time : np.ndarray
            Zaman dizisi.
        residuals : np.ndarray
            Gözlenen - model residual dizisi.
        target_id : str
            Hedef ID.
        sector : int
            Sektör numarası.
        save : bool
            Diske kaydet.

        Returns
        -------
        plt.Figure
        """

        fig, (ax1, ax2) = self.fm.create_figure(
            figsize=(14, 4),
            n_rows=1,
            n_cols=2,
        )

        fig.subplots_adjust(wspace=0.3)

        rms = float(np.std(residuals))
        rms_ppm = rms * 1e6

        # ── Sol: Residual vs zaman ──
        ax1.scatter(
            time,
            residuals * 1e6,
            s=2,
            color=Colors.RESIDUAL,
            alpha=0.4,
            rasterized=True,
        )

        ax1.axhline(
            y=0,
            color=Colors.TEXT_SECONDARY,
            linewidth=0.8,
            linestyle="--",
            alpha=0.7,
        )

        # ±1 sigma band
        ax1.axhspan(
            -rms_ppm, rms_ppm,
            color=Colors.RESIDUAL,
            alpha=0.07,
            label=f"±1σ = ±{rms_ppm:.0f} ppm",
        )

        ax1.set_xlabel("Zaman (BTJD)", color=Colors.TEXT_PRIMARY)
        ax1.set_ylabel("Residual (ppm)", color=Colors.TEXT_PRIMARY)
        ax1.set_title("Residual vs Zaman", color=Colors.TEXT_PRIMARY)
        ax1.legend(loc="upper right")

        # ── Sağ: Histogram ──
        clean = residuals[np.isfinite(residuals)] * 1e6

        if len(clean) > 10:
            n_bins = min(50, max(20, len(clean) // 30))
            ax2.hist(
                clean,
                bins=n_bins,
                color=Colors.RESIDUAL,
                alpha=0.7,
                edgecolor=Colors.BORDER,
                density=True,
            )

            # Normal fit
            mu, sigma = scipy_stats.norm.fit(clean)
            x_fit = np.linspace(clean.min(), clean.max(), 200)
            pdf_fit = scipy_stats.norm.pdf(x_fit, mu, sigma)

            ax2.plot(
                x_fit, pdf_fit,
                color=Colors.MODEL,
                linewidth=1.5,
                label=f"N(μ={mu:.1f}, σ={sigma:.1f}) ppm",
            )

            # Shapiro-Wilk normallik testi
            if len(clean) < 5000:
                stat, p_val = scipy_stats.shapiro(clean)
                normality_text = f"Shapiro-Wilk p={p_val:.3f}"
                color = Colors.CLASS_A if p_val > 0.05 else Colors.CLASS_C
                ax2.text(
                    0.97, 0.95, normality_text,
                    transform=ax2.transAxes,
                    ha="right", va="top",
                    color=color,
                    fontsize=8,
                )

        ax2.set_xlabel("Residual (ppm)", color=Colors.TEXT_PRIMARY)
        ax2.set_ylabel("Yoğunluk", color=Colors.TEXT_PRIMARY)
        ax2.set_title("Residual Dağılımı", color=Colors.TEXT_PRIMARY)
        ax2.legend(loc="upper left")

        fig.suptitle(
            self.fm.format_target_title(target_id, sector, "Residual"),
            color=Colors.TEXT_PRIMARY,
            fontweight="bold",
        )

        self.fm.add_watermark(ax2)

        if save:
            safe_id = target_id.replace(" ", "_")
            self.fm.save(fig, f"{safe_id}_S{sector:02d}_residuals")

        return fig

    def plot_transit_timing(
        self,
        candidate: CascadeCandidate,
        save: bool = True,
    ) -> plt.Figure:
        """
        Transit zamanlama varyasyonu (O-C) grafiği.

        Parameters
        ----------
        candidate : CascadeCandidate
            Cascade tespit sonucu.
        save : bool
            Diske kaydet.

        Returns
        -------
        plt.Figure
        """

        target_id = candidate.target_id
        sector = candidate.sector

        fig, ax = self.fm.create_figure(figsize=(12, 4))

        transit_times = candidate.transit_times

        if len(transit_times) < 3:
            ax.text(
                0.5, 0.5,
                f"Zamanlama analizi için yeterli transit yok\n"
                f"(n={len(transit_times)}, minimum=3)",
                transform=ax.transAxes,
                ha="center", va="center",
                color=Colors.TEXT_SECONDARY,
                fontsize=11,
            )
            if save:
                safe_id = target_id.replace(" ", "_")
                self.fm.save(fig, f"{safe_id}_S{sector:02d}_timing")
            return fig

        # Lineer efemeris (O-C)
        t0 = transit_times[0]
        n_vals = np.round(
            (transit_times - t0) / candidate.period
        ).astype(int)
        expected = t0 + n_vals * candidate.period
        o_minus_c = (transit_times - expected) * 1440  # gün → dakika

        ax.errorbar(
            n_vals,
            o_minus_c,
            fmt="o",
            color=Colors.FLUX,
            markersize=6,
            elinewidth=1.5,
            capsize=3,
            label="O-C",
        )

        ax.axhline(
            y=0,
            color=Colors.TEXT_SECONDARY,
            linewidth=0.8,
            linestyle="--",
            alpha=0.7,
        )

        # ±1 sigma band
        rms = float(np.std(o_minus_c))
        ax.axhspan(-rms, rms, color=Colors.FLUX, alpha=0.08, label=f"±RMS ({rms:.1f} dk)")

        ax.set_xlabel("Transit Sayısı (N)", color=Colors.TEXT_PRIMARY)
        ax.set_ylabel("O-C (dakika)", color=Colors.TEXT_PRIMARY)

        title = self.fm.format_target_title(
            target_id, sector,
            f"Transit Zamanlama  |  RMS={rms:.2f} dk"
        )
        ax.set_title(title, color=Colors.TEXT_PRIMARY, fontweight="bold")
        ax.legend(loc="upper right")
        self.fm.add_watermark(ax)

        if save:
            safe_id = target_id.replace(" ", "_")
            self.fm.save(fig, f"{safe_id}_S{sector:02d}_timing")

        return fig

    def plot_quality_scorecard(
        self,
        score: QualityScore,
        vetting: VettingReport,
        save: bool = True,
    ) -> plt.Figure:
        """
        Kalite skoru ve vetting sonuçlarını görselleştirir.

        Sol: bileşen skor çubuk grafiği.
        Sağ: vetting test sonuçları.

        Parameters
        ----------
        score : QualityScore
            Kalite skoru nesnesi.
        vetting : VettingReport
            Vetting raporu.
        save : bool
            Diske kaydet.

        Returns
        -------
        plt.Figure
        """

        target_id = score.target_id
        sector = score.sector

        fig, (ax1, ax2) = self.fm.create_figure(
            figsize=(14, 5),
            n_rows=1,
            n_cols=2,
        )

        fig.subplots_adjust(wspace=0.4)

        # ── Sol: Bileşen skorları ──
        if score.components:
            names = [c.name for c in score.components]
            values = [c.score for c in score.components]
            contributions = [c.contribution for c in score.components]

            bar_colors = [
                Colors.CLASS_A if v >= 70 else
                Colors.CLASS_B if v >= 50 else
                Colors.CLASS_C if v >= 30 else
                Colors.CLASS_D
                for v in values
            ]

            bars = ax1.barh(
                names,
                values,
                color=bar_colors,
                alpha=0.8,
                edgecolor=Colors.BORDER,
            )

            # Katkı etiketleri
            for bar, contrib in zip(bars, contributions):
                ax1.text(
                    bar.get_width() + 1,
                    bar.get_y() + bar.get_height() / 2,
                    f"+{contrib:.1f}",
                    va="center",
                    color=Colors.TEXT_SECONDARY,
                    fontsize=8,
                )

            ax1.set_xlim(0, 110)
            ax1.axvline(
                x=score.total_score / len(score.components) * 1,
                color=Colors.TEXT_SECONDARY,
                linewidth=0.5,
                linestyle=":",
                alpha=0.5,
            )

        # Toplam skor
        class_color = Colors.class_color(score.candidate_class.value)
        ax1.text(
            105, len(score.components) - 0.5,
            f"{score.total_score:.0f}/100\nSınıf {score.candidate_class.value}",
            ha="center", va="center",
            color=class_color,
            fontsize=12,
            fontweight="bold",
        )

        ax1.set_xlabel("Skor (0-100)", color=Colors.TEXT_PRIMARY)
        ax1.set_title("Kalite Bileşenleri", color=Colors.TEXT_PRIMARY, fontweight="bold")

        # ── Sağ: Vetting testleri ──
        from astrotransit.quality.vetting import VettingVerdict

        verdict_colors = {
            VettingVerdict.PASS: Colors.CLASS_A,
            VettingVerdict.WARN: Colors.CLASS_C,
            VettingVerdict.FAIL: Colors.CLASS_D,
            VettingVerdict.SKIP: Colors.TEXT_SECONDARY,
        }

        verdict_symbols = {
            VettingVerdict.PASS: "✓",
            VettingVerdict.WARN: "⚠",
            VettingVerdict.FAIL: "✗",
            VettingVerdict.SKIP: "–",
        }

        ax2.set_xticks([])
        ax2.set_yticks([])

        y = 0.95
        dy = 0.10

        for test in vetting.tests:
            color = verdict_colors.get(test.verdict, Colors.TEXT_SECONDARY)
            symbol = verdict_symbols.get(test.verdict, "?")

            ax2.text(
                0.05, y, f"{symbol}",
                transform=ax2.transAxes,
                ha="left", va="top",
                color=color,
                fontsize=11,
                fontweight="bold",
            )
            ax2.text(
                0.15, y, test.name.replace("_", " ").title(),
                transform=ax2.transAxes,
                ha="left", va="top",
                color=Colors.TEXT_PRIMARY,
                fontsize=8,
            )
            ax2.text(
                0.70, y, f"{test.value:.3f}",
                transform=ax2.transAxes,
                ha="left", va="top",
                color=Colors.TEXT_SECONDARY,
                fontsize=8,
                family="monospace",
            )

            y -= dy

        # FPP
        fpp = vetting.false_positive_probability
        fpp_text = "NA" if fpp is None else f"{fpp:.3f}"
        fpp_color = (
            Colors.CLASS_A if fpp is not None and fpp < 0.1 else
            Colors.CLASS_C if fpp is not None and fpp < 0.3 else
            Colors.TEXT_SECONDARY if fpp is None else
            Colors.CLASS_D
        )
        ax2.text(
            0.5, 0.04,
            f"FPP = {fpp_text}",
            transform=ax2.transAxes,
            ha="center", va="bottom",
            color=fpp_color,
            fontsize=10,
            fontweight="bold",
        )

        ax2.set_title("Vetting Testleri", color=Colors.TEXT_PRIMARY, fontweight="bold")

        fig.suptitle(
            self.fm.format_target_title(target_id, sector, "Kalite Kartı"),
            color=Colors.TEXT_PRIMARY,
            fontweight="bold",
        )

        self.fm.add_watermark(ax2)

        if save:
            safe_id = target_id.replace(" ", "_")
            self.fm.save(fig, f"{safe_id}_S{sector:02d}_scorecard")

        return fig