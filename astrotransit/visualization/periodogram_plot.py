"""
Periyodogram görselleştirme modülü.

BLS ve TLS periodogramlarını,
en güçlü sinyal tepesini ve
harmonik yapıları görselleştirir.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import matplotlib.pyplot as plt
from loguru import logger

from astrotransit.visualization.base import FigureManager, Colors
from astrotransit.detection.bls_search import BLSResult
from astrotransit.detection.tls_search import TLSResult
from astrotransit.detection.cascade import CascadeCandidate


class PeriodogramPlotter:
    """
    BLS ve TLS periodogram grafik üreticisi.

    Parameters
    ----------
    figure_manager : FigureManager
        Figür yöneticisi.
    """

    def __init__(self, figure_manager: FigureManager):
        self.fm = figure_manager

    def plot_bls(
        self,
        bls_result: BLSResult,
        save: bool = True,
    ) -> plt.Figure:
        """
        BLS güç spektrumu grafiği.

        Parameters
        ----------
        bls_result : BLSResult
            BLS arama sonucu.
        save : bool
            Diske kaydet.

        Returns
        -------
        plt.Figure
        """

        target_id = bls_result.target_id
        sector = bls_result.sector

        fig, ax = self.fm.create_figure(figsize=(14, 4))

        if len(bls_result.periods_searched) == 0:
            ax.text(
                0.5, 0.5, "BLS verisi yok",
                transform=ax.transAxes,
                ha="center", va="center",
                color=Colors.TEXT_SECONDARY,
            )
            if save:
                safe_id = target_id.replace(" ", "_")
                self.fm.save(fig, f"{safe_id}_S{sector:02d}_bls")
            return fig

        # Ana periodogram
        ax.plot(
            bls_result.periods_searched,
            bls_result.power_array,
            color=Colors.BLS_POWER,
            linewidth=0.8,
            alpha=0.9,
            label="BLS Gücü",
            rasterized=True,
        )

        # En güçlü tepeyi işaretle
        if bls_result.best is not None:
            best = bls_result.best
            ax.axvline(
                x=best.period,
                color=Colors.PEAK_MARK,
                linewidth=1.5,
                linestyle="--",
                alpha=0.9,
                label=(
                    f"En İyi: P={best.period:.4f}d  "
                    f"Güç={best.power:.2f}  "
                    f"Derinlik={best.depth * 1e6:.0f}ppm"
                ),
            )

            # Harmonikler
            for n, factor in [(2, 0.5), (3, 2.0)]:
                harmonic = best.period * factor
                if bls_result.periods_searched[0] < harmonic < bls_result.periods_searched[-1]:
                    ax.axvline(
                        x=harmonic,
                        color=Colors.TREND,
                        linewidth=0.8,
                        linestyle=":",
                        alpha=0.5,
                        label=f"P×{factor:.1f}" if n == 2 else None,
                    )

        # Eşik çizgisi
        ax.axhline(
            y=7.0,
            color=Colors.TEXT_SECONDARY,
            linewidth=0.8,
            linestyle="--",
            alpha=0.5,
            label="Eşik (SDE=7)",
        )

        ax.set_xlabel("Periyot (gün)", color=Colors.TEXT_PRIMARY)
        ax.set_ylabel("BLS Gücü (SDE)", color=Colors.TEXT_PRIMARY)
        ax.set_xscale("log")

        title = self.fm.format_target_title(
            target_id, sector,
            f"BLS  |  {bls_result.n_periods_searched} periyot"
        )
        ax.set_title(title, color=Colors.TEXT_PRIMARY, fontweight="bold")
        ax.legend(loc="upper right")
        self.fm.add_watermark(ax)

        if save:
            safe_id = target_id.replace(" ", "_")
            self.fm.save(fig, f"{safe_id}_S{sector:02d}_bls_periodogram")

        return fig

    def plot_tls(
        self,
        tls_result: TLSResult,
        save: bool = True,
    ) -> plt.Figure:
        """
        TLS SDE spektrumu grafiği.

        Parameters
        ----------
        tls_result : TLSResult
            TLS doğrulama sonucu.
        save : bool
            Diske kaydet.

        Returns
        -------
        plt.Figure
        """

        target_id = tls_result.target_id
        sector = tls_result.sector

        fig, ax = self.fm.create_figure(figsize=(14, 4))

        ax.set_xlabel("Periyot (gün)", color=Colors.TEXT_PRIMARY)
        ax.set_ylabel("TLS SDE", color=Colors.TEXT_PRIMARY)

        # TLS kendi güç dizisini döndürmez (sadece en iyi sonuç)
        # Bu yüzden sadece sonuç bilgilerini göster
        ax.text(
            0.5, 0.6,
            f"TLS Sonucu",
            transform=ax.transAxes,
            ha="center", va="center",
            color=Colors.TEXT_PRIMARY,
            fontsize=14,
            fontweight="bold",
        )

        info_lines = [
            f"Periyot: {tls_result.period:.6f} ± {tls_result.period_err:.6f} gün",
            f"SDE: {tls_result.sde:.3f}",
            f"SNR: {tls_result.snr:.3f}",
            f"Rp/Rs: {tls_result.rp_rs:.5f}",
            f"Süre: {tls_result.duration * 24:.3f} saat",
            f"Derinlik: {tls_result.depth * 1e6:.0f} ppm",
            f"Transit sayısı: {tls_result.transit_count}",
            f"Odd-Even: {tls_result.odd_even_mismatch:.3f}σ",
            f"FAP: {tls_result.false_alarm_probability:.2e}",
        ]

        ax.text(
            0.5, 0.42,
            "\n".join(info_lines),
            transform=ax.transAxes,
            ha="center", va="center",
            color=Colors.TEXT_SECONDARY,
            fontsize=9,
            family="monospace",
            linespacing=1.7,
        )

        # Durum ikonu
        status_color = Colors.CLASS_A if tls_result.passed_threshold else Colors.CLASS_D
        status_text = "✓ ONAYLANDI" if tls_result.passed_threshold else "✗ BAŞARISIZ"

        ax.text(
            0.5, 0.88,
            status_text,
            transform=ax.transAxes,
            ha="center", va="center",
            color=status_color,
            fontsize=12,
            fontweight="bold",
        )

        if not tls_result.passed_threshold and tls_result.reject_reason:
            ax.text(
                0.5, 0.08,
                f"Red: {tls_result.reject_reason}",
                transform=ax.transAxes,
                ha="center", va="center",
                color=Colors.CLASS_C,
                fontsize=8,
                style="italic",
                wrap=True,
            )

        title = self.fm.format_target_title(target_id, sector, "TLS")
        ax.set_title(title, color=Colors.TEXT_PRIMARY, fontweight="bold")
        ax.set_xticks([])
        ax.set_yticks([])
        self.fm.add_watermark(ax)

        if save:
            safe_id = target_id.replace(" ", "_")
            self.fm.save(fig, f"{safe_id}_S{sector:02d}_tls_result")

        return fig

    def plot_bls_tls_comparison(
        self,
        bls_result: BLSResult,
        tls_result: TLSResult,
        save: bool = True,
    ) -> plt.Figure:
        """
        BLS ve TLS sonuçlarının yan yana karşılaştırması.

        Parameters
        ----------
        bls_result : BLSResult
            BLS sonucu.
        tls_result : TLSResult
            TLS sonucu.
        save : bool
            Diske kaydet.

        Returns
        -------
        plt.Figure
        """

        target_id = bls_result.target_id
        sector = bls_result.sector

        fig, (ax1, ax2) = self.fm.create_figure(
            figsize=(16, 5),
            n_rows=1,
            n_cols=2,
        )

        # ── Sol: BLS periodogram ──
        if len(bls_result.periods_searched) > 0:
            ax1.plot(
                bls_result.periods_searched,
                bls_result.power_array,
                color=Colors.BLS_POWER,
                linewidth=0.8,
                alpha=0.9,
                rasterized=True,
            )

            if bls_result.best is not None:
                ax1.axvline(
                    x=bls_result.best.period,
                    color=Colors.PEAK_MARK,
                    linewidth=1.5,
                    linestyle="--",
                    label=f"P={bls_result.best.period:.4f}d",
                )

            ax1.axhline(
                y=7.0,
                color=Colors.TEXT_SECONDARY,
                linewidth=0.8,
                linestyle="--",
                alpha=0.5,
            )

        ax1.set_xlabel("Periyot (gün)", color=Colors.TEXT_PRIMARY)
        ax1.set_ylabel("BLS SDE", color=Colors.TEXT_PRIMARY)
        ax1.set_xscale("log")
        ax1.set_title("BLS Periodogram", color=Colors.TEXT_PRIMARY, fontweight="bold")
        ax1.legend(loc="upper right")

        # ── Sağ: TLS özet ──
        ax2.set_xticks([])
        ax2.set_yticks([])

        y_pos = 0.92
        dy = 0.09

        params = [
            ("BLS Periyot", f"{bls_result.best.period:.6f} gün"
             if bls_result.best else "—"),
            ("TLS Periyot", f"{tls_result.period:.6f} gün"),
            ("TLS SDE", f"{tls_result.sde:.3f}"),
            ("TLS SNR", f"{tls_result.snr:.3f}"),
            ("Rp/Rs", f"{tls_result.rp_rs:.5f}"),
            ("Süre", f"{tls_result.duration * 24:.3f} saat"),
            ("Transit", f"{tls_result.transit_count}"),
            ("Odd-Even", f"{tls_result.odd_even_mismatch:.2f}σ"),
            ("FAP", f"{tls_result.false_alarm_probability:.2e}"),
        ]

        for label, value in params:
            ax2.text(
                0.05, y_pos, label + ":",
                transform=ax2.transAxes,
                color=Colors.TEXT_SECONDARY,
                fontsize=9, ha="left",
            )
            ax2.text(
                0.55, y_pos, value,
                transform=ax2.transAxes,
                color=Colors.TEXT_PRIMARY,
                fontsize=9, ha="left",
                fontweight="bold",
                family="monospace",
            )
            y_pos -= dy

        # Periyot uyum kontrolü
        if bls_result.best is not None:
            rel_diff = abs(
                bls_result.best.period - tls_result.period
            ) / bls_result.best.period
            match_color = Colors.CLASS_A if rel_diff < 0.01 else Colors.CLASS_C
            match_text = (
                f"Periyot uyumu: Δ={rel_diff * 100:.3f}%"
            )
            ax2.text(
                0.5, 0.04, match_text,
                transform=ax2.transAxes,
                ha="center", color=match_color,
                fontsize=9, fontweight="bold",
            )

        status_color = Colors.CLASS_A if tls_result.passed_threshold else Colors.CLASS_D
        ax2.text(
            0.5, -0.04,
            "TLS: ✓ ONAY" if tls_result.passed_threshold else "TLS: ✗ RED",
            transform=ax2.transAxes,
            ha="center", color=status_color,
            fontsize=11, fontweight="bold",
        )

        ax2.set_title("TLS Özet", color=Colors.TEXT_PRIMARY, fontweight="bold")

        fig.suptitle(
            self.fm.format_target_title(target_id, sector, "BLS → TLS"),
            color=Colors.TEXT_PRIMARY,
            fontweight="bold",
            fontsize=12,
        )

        self.fm.add_watermark(ax2)

        if save:
            safe_id = target_id.replace(" ", "_")
            self.fm.save(
                fig,
                f"{safe_id}_S{sector:02d}_bls_tls_comparison",
            )

        return fig