"""
Görsel rapor üreticisi.

Bir transit adayı için tüm grafikleri
sıralı olarak üretir ve dosya yollarını
döndürür.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from loguru import logger

from astrotransit.visualization.base import FigureManager
from astrotransit.visualization.lightcurve_plot import LightCurvePlotter
from astrotransit.visualization.periodogram_plot import PeriodogramPlotter
from astrotransit.visualization.folded_plot import FoldedPlotter
from astrotransit.visualization.diagnostic_plots import DiagnosticPlotter
from astrotransit.visualization.summary_panel import SummaryPanelPlotter
from astrotransit.settings import Settings, get_settings
from astrotransit.utils.paths import ProjectPaths


@dataclass
class VisualizationReport:
    """
    Üretilen tüm grafiklerin yol listesi.

    Attributes
    ----------
    target_id : str
        Hedef TIC ID.
    sector : int
        Sektör numarası.
    summary_panel : Optional[Path]
        Özet panel grafiği.
    lightcurve : Optional[Path]
        Light curve grafiği.
    periodogram : Optional[Path]
        Periodogram grafiği.
    folded : Optional[Path]
        Faz katlanmış transit grafiği.
    residuals : Optional[Path]
        Residual grafiği.
    timing : Optional[Path]
        Timing O-C grafiği.
    scorecard : Optional[Path]
        Kalite kartı grafiği.
    """

    target_id: str
    sector: int
    summary_panel: Optional[Path] = None
    lightcurve: Optional[Path] = None
    periodogram: Optional[Path] = None
    folded: Optional[Path] = None
    residuals: Optional[Path] = None
    timing: Optional[Path] = None
    scorecard: Optional[Path] = None

    def to_dict(self) -> dict:
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "figures": {
                k: str(v) if v else None
                for k, v in {
                    "summary_panel": self.summary_panel,
                    "lightcurve": self.lightcurve,
                    "periodogram": self.periodogram,
                    "folded": self.folded,
                    "residuals": self.residuals,
                    "timing": self.timing,
                    "scorecard": self.scorecard,
                }.items()
            },
        }


class VisualizationReportGenerator:
    """
    Transit aday görsel rapor üreticisi.

    Tüm grafikleri sıralı olarak oluşturur
    ve dosya yollarını döndürür.

    Parameters
    ----------
    settings : Settings, opsiyonel
        Proje konfigürasyonu.
    """

    def __init__(self, settings: Optional[Settings] = None):
        if settings is None:
            settings = get_settings()

        self.settings = settings
        out_cfg = settings.outputs

        paths = ProjectPaths(
            output_dir=settings.general.output_dir,
            temp_dir=settings.general.temp_dir,
        )

        self._figure_dir = paths.figures

        self._fm = FigureManager(
            output_dir=self._figure_dir,
            figure_format=out_cfg.figure_format,
            dpi=out_cfg.figure_dpi,
            apply_style=True,
        )

        # Alt çiziciler
        self._lc_plotter = LightCurvePlotter(self._fm)
        self._period_plotter = PeriodogramPlotter(self._fm)
        self._fold_plotter = FoldedPlotter(self._fm)
        self._diag_plotter = DiagnosticPlotter(self._fm)
        self._summary_plotter = SummaryPanelPlotter(self._fm)

        logger.debug("VisualizationReportGenerator başlatıldı.")

    def generate(
        self,
        detrended,
        normalized=None,
        candidate=None,
        bls_result=None,
        tls_result=None,
        score=None,
        vetting=None,
        fit_result=None,
        stellar_props=None,
    ) -> VisualizationReport:
        """
        Transit adayı için tüm grafikleri üretir.

        Parameters
        ----------
        detrended : DetrendedLightCurve
            Trend giderilmiş light curve.
        normalized : NormalizedLightCurve, opsiyonel
            Normalize edilmiş veri.
        candidate : CascadeCandidate, opsiyonel
            Cascade sonucu.
        bls_result : BLSResult, opsiyonel
            BLS sonucu.
        tls_result : TLSResult, opsiyonel
            TLS sonucu.
        score : QualityScore, opsiyonel
            Kalite skoru.
        vetting : VettingReport, opsiyonel
            Vetting raporu.
        fit_result : opsiyonel
            Fit sonucu.
        stellar_props : opsiyonel
            Yıldız özellikleri.

        Returns
        -------
        VisualizationReport
            Üretilen grafiklerin yol listesi.
        """

        target_id = detrended.target_id
        sector = detrended.sector

        if not self.settings.outputs.save_figures:
            logger.debug("Grafik kaydetme devre dışı.")
            return VisualizationReport(target_id=target_id, sector=sector)

        logger.info(f"Görsel rapor üretiliyor — {target_id} sektör {sector}")

        report = VisualizationReport(
            target_id=target_id,
            sector=sector,
        )

        # ── 1: Light curve ──
        try:
            if normalized is not None:
                self._lc_plotter.plot_raw_and_detrended(
                    normalized, detrended, candidate, save=True
                )
            else:
                self._lc_plotter.plot_detrended_only(detrended, candidate, save=True)
            safe_id = target_id.replace(" ", "_")
            report.lightcurve = (
                self._figure_dir
                / f"{safe_id}_S{sector:02d}_lightcurve.{self.settings.outputs.figure_format}"
            )
        except Exception as e:
            logger.warning(f"Light curve grafiği başarısız: {e}")

        # ── 2: Periodogram ──
        try:
            if bls_result is not None and tls_result is not None:
                self._period_plotter.plot_bls_tls_comparison(bls_result, tls_result, save=True)
                safe_id = target_id.replace(" ", "_")
                report.periodogram = (
                    self._figure_dir
                    / f"{safe_id}_S{sector:02d}_bls_tls_comparison.{self.settings.outputs.figure_format}"
                )
            elif bls_result is not None:
                self._period_plotter.plot_bls(bls_result, save=True)
        except Exception as e:
            logger.warning(f"Periodogram grafiği başarısız: {e}")

        # ── 3: Faz katlanmış ──
        try:
            if candidate is not None:
                self._fold_plotter.plot_folded_transit(candidate, tls_result, fit_result, save=True)
                safe_id = target_id.replace(" ", "_")
                report.folded = (
                    self._figure_dir
                    / f"{safe_id}_S{sector:02d}_folded.{self.settings.outputs.figure_format}"
                )
        except Exception as e:
            logger.warning(f"Faz katlanmış grafiği başarısız: {e}")

        # ── 4b: Residual (fit varsa) ──
        try:
            if fit_result is not None and fit_result.success:
                from astrotransit.modeling.transit_model import (
                    TransitModel,
                    TransitModelParams,
                )

                # Model flux'unu yeniden hesapla
                a_over_rs = getattr(fit_result, "a_over_rs", 15.0)
                params = TransitModelParams(
                    period=fit_result.period,
                    t0=fit_result.t0,
                    rp=fit_result.rp_rs,
                    a=a_over_rs,
                    inc=fit_result.inclination,
                    u1=fit_result.u1,
                    u2=fit_result.u2,
                    baseline=fit_result.baseline,
                )
                model = TransitModel(detrended.time)
                model_flux = model.flux(params)
                residuals = detrended.flux - model_flux

                self._diag_plotter.plot_residuals(
                    time=detrended.time,
                    residuals=residuals,
                    target_id=target_id,
                    sector=sector,
                    save=True,
                )
                safe_id = target_id.replace(" ", "_")
                report.residuals = (
                    self._figure_dir
                    / f"{safe_id}_S{sector:02d}_residuals.{self.settings.outputs.figure_format}"
                )
        except Exception as e:
            logger.warning(f"Residual grafiği başarısız: {e}")

        # ── 4: Timing ──
        try:
            if candidate is not None:
                self._diag_plotter.plot_transit_timing(candidate, save=True)
                safe_id = target_id.replace(" ", "_")
                report.timing = (
                    self._figure_dir
                    / f"{safe_id}_S{sector:02d}_timing.{self.settings.outputs.figure_format}"
                )
        except Exception as e:
            logger.warning(f"Timing grafiği başarısız: {e}")

        # ── 5: Scorecard ──
        try:
            if score is not None and vetting is not None:
                self._diag_plotter.plot_quality_scorecard(score, vetting, save=True)
                safe_id = target_id.replace(" ", "_")
                report.scorecard = (
                    self._figure_dir
                    / f"{safe_id}_S{sector:02d}_scorecard.{self.settings.outputs.figure_format}"
                )
        except Exception as e:
            logger.warning(f"Scorecard grafiği başarısız: {e}")

        # ── 6: Özet panel (en son) ──
        try:
            if (
                candidate is not None
                and bls_result is not None
                and score is not None
                and vetting is not None
            ):
                self._summary_plotter.plot(
                    detrended=detrended,
                    candidate=candidate,
                    bls_result=bls_result,
                    tls_result=tls_result,
                    score=score,
                    vetting=vetting,
                    fit_result=fit_result,
                    stellar_props=stellar_props,
                    save=True,
                )
                safe_id = target_id.replace(" ", "_")
                report.summary_panel = (
                    self._figure_dir
                    / f"{safe_id}_S{sector:02d}_summary.{self.settings.outputs.figure_format}"
                )
        except Exception as e:
            logger.warning(f"Özet panel başarısız: {e}")

        n_produced = sum(
            1
            for v in [
                report.summary_panel,
                report.lightcurve,
                report.periodogram,
                report.folded,
                report.residuals,
                report.timing,
                report.scorecard,
            ]
            if v is not None
        )

        logger.info(f"Görsel rapor tamamlandı — {target_id}: {n_produced} grafik üretildi")

        return report
