"""
Kalite değerlendirme pipeline orkestratörü.

Metrik → SNR → Vetting → Skor → Sınıf
adımlarını tek çağrıda birleştirir.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from loguru import logger

from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve
from astrotransit.detection.cascade import CascadeCandidate
from astrotransit.quality.metrics import QualityMetrics, QualityMetricsCalculator
from astrotransit.quality.snr import SNRBreakdown, SNRCalculator
from astrotransit.quality.vetting import VettingReport, FalsePositiveVetter
from astrotransit.quality.scorer import QualityScore, CandidateScorer
from astrotransit.settings import Settings, get_settings

from astrotransit.quality.anomaly_scorer import AnomalyScorer, AnomalyReport
from astrotransit.quality.residual_analysis import ResidualAnalyzer, ResidualReport
from astrotransit.quality.transit_consistency import TransitConsistencyAnalyzer, TransitConsistencyReport
from astrotransit.quality.timing_analysis import TimingAnalyzer, TimingReport
from astrotransit.quality.fpp import SimpleFPPCalculator, SimpleFPPReport



@dataclass
class QualityEvaluationResult:
    """
    Kalite değerlendirme pipeline'ının tam çıktısı.

    Attributes
    ----------
    target_id : str
        Hedef TIC ID.
    sector : int
        Sektör numarası.
    metrics : QualityMetrics
        Kalite metrikleri.
    snr : SNRBreakdown
        SNR breakdown.
    vetting : VettingReport
        Vetting raporu.
    score : QualityScore
        Kalite skoru ve sınıf.
    """

    target_id: str
    sector: int
    metrics: QualityMetrics
    snr: SNRBreakdown
    vetting: VettingReport
    score: QualityScore

    anomaly: Optional[AnomalyReport] = None
    anomaly_residual: Optional[ResidualReport] = None
    anomaly_transit: Optional[TransitConsistencyReport] = None
    anomaly_timing: Optional[TimingReport] = None
    fpp_report: Optional[SimpleFPPReport] = None


    def to_dict(self) -> dict:
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "metrics": self.metrics.to_dict(),
            "snr": self.snr.to_dict(),
            "vetting": self.vetting.to_dict(),
            "score": self.score.to_dict(),
            "anomaly": self.anomaly.to_dict() if self.anomaly else None,
            "anomaly_residual": self.anomaly_residual.to_dict() if self.anomaly_residual else None,
            "anomaly_transit": self.anomaly_transit.to_dict() if self.anomaly_transit else None,
            "anomaly_timing": self.anomaly_timing.to_dict() if self.anomaly_timing else None,
            "fpp_report": self.fpp_report.to_dict() if self.fpp_report else None,
        }

    def summary(self) -> dict:
        summary_fpp = (
            self.fpp_report.fpp
            if self.fpp_report is not None
            else self.vetting.false_positive_probability
        )
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "snr_adopted": round(self.snr.snr_adopted, 2),
            "total_score": round(self.score.total_score, 2),
            "candidate_class": self.score.candidate_class.value,
            "fpp": round(summary_fpp, 4),
            "false_positive_probability": round(summary_fpp, 4),
            "detection_confidence": (
                self.fpp_report.confidence if self.fpp_report is not None else "UNKNOWN"
            ),
            "is_false_positive": self.vetting.is_false_positive,
            "is_anomalous": self.score.is_anomalous,
        }


class QualityEvaluationPipeline:
    """
    Kalite değerlendirme pipeline'ı.

    Parameters
    ----------
    settings : Settings, opsiyonel
        Proje konfigürasyonu.
    cadence_sec : float
        Gözlem kadansı (saniye).
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        cadence_sec: float = 120.0,
    ):
        if settings is None:
            settings = get_settings()

        self.settings = settings

        q_cfg = settings.quality

        self._metrics_calc = QualityMetricsCalculator(cadence_sec=cadence_sec)

        self._snr_calc = SNRCalculator(cadence_sec=cadence_sec)

        self._vetter = FalsePositiveVetter(
            odd_even_threshold=3.0,
            secondary_eclipse_threshold=0.5,
            variability_amplitude_threshold=5000.0,
        )

        self._scorer = CandidateScorer(
            snr_min=q_cfg.min_snr,
            snr_max=q_cfg.min_snr * 6,
        )

        
        self._residual_analyzer = ResidualAnalyzer()
        self._transit_consistency_analyzer = TransitConsistencyAnalyzer()
        self._timing_analyzer = TimingAnalyzer()
        self._anomaly_scorer = AnomalyScorer()
        self._fpp_calculator = SimpleFPPCalculator()

        logger.info("QualityEvaluationPipeline başlatıldı.")

    def evaluate(
        self,
        detrended: DetrendedLightCurve,
        candidate: CascadeCandidate,
        fit_result=None,
        anomaly_data: Optional[dict] = None,
        fpp_data: Optional[dict] = None,
    ) -> QualityEvaluationResult:
        """
        Transit adayı için tam kalite değerlendirmesi yapar.

        Parameters
        ----------
        detrended : DetrendedLightCurve
            Detrend edilmiş light curve.
        candidate : CascadeCandidate
            Cascade tespit sonucu.
        fit_result : opsiyonel
            Fit sonucu.

        Returns
        -------
        QualityEvaluationResult
            Tam kalite değerlendirme sonucu.
        """

        target_id = candidate.target_id
        sector = candidate.sector

        logger.info(
            f"Kalite değerlendirmesi — "
            f"{target_id} sektör {sector}"
        )

        # ── Adım 1: Metrikler ──
        metrics = self._metrics_calc.compute_all(
            detrended, candidate, fit_result
        )

        # ── Adım 2: SNR ──
        snr = self._snr_calc.compute(detrended, candidate)

        # ── Adım 3: Vetting ──
        vetting = self._vetter.vet(candidate, metrics)

        # ── Adım 4: Skor ve Sınıf ──
        score = self._scorer.score(
            candidate, metrics, snr, vetting, fit_result
        )


        # ── Adım 5: Anomaly analizi (opsiyonel) ──
        anomaly_residual = None
        anomaly_transit = None
        anomaly_timing = None
        anomaly = None
        fpp_report = None

        if anomaly_data is not None:
            try:
                if anomaly_data.get("residuals") is not None:
                    anomaly_residual = self._residual_analyzer.analyze(
                        target_id=target_id,
                        sector=sector,
                        time=anomaly_data["time"],
                        residuals=anomaly_data["residuals"],
                        in_transit_mask=anomaly_data["in_transit_mask"],
                    )

                if anomaly_data.get("phase") is not None:
                    anomaly_transit = self._transit_consistency_analyzer.analyze(
                        target_id=target_id,
                        sector=sector,
                        phase=anomaly_data["phase"],
                        flux=anomaly_data["flux"],
                        in_transit_mask=anomaly_data["in_transit_mask"],
                        transit_event_ids=anomaly_data.get("transit_event_ids"),
                        per_transit_depths=anomaly_data.get("per_transit_depths"),
                    )

                if anomaly_data.get("period") is not None:
                    anomaly_timing = self._timing_analyzer.analyze(
                        target_id=target_id,
                        sector=sector,
                        period=anomaly_data["period"],
                        observed_midtimes=anomaly_data.get("observed_midtimes"),
                        t0=anomaly_data.get("t0"),
                        oc_values=anomaly_data.get("oc_values"),
                    )

                anomaly = self._anomaly_scorer.score(
                    residual_report=anomaly_residual,
                    transit_report=anomaly_transit,
                    timing_report=anomaly_timing,
                )
            except Exception as exc:
                logger.warning(f"Anomaly analizi başarısız: {exc}")

        if fpp_data is not None:
            try:
                fpp_report = self._fpp_calculator.calculate(
                    target_id=target_id,
                    sector=sector,
                    primary_depth=fpp_data.get("primary_depth"),
                    odd_depth=fpp_data.get("odd_depth"),
                    even_depth=fpp_data.get("even_depth"),
                    v_shape_score=fpp_data.get("v_shape_score"),
                    secondary_depth=fpp_data.get("secondary_depth"),
                    centroid_shift_arcsec=fpp_data.get("centroid_shift_arcsec"),
                    crowding_ratio=fpp_data.get("crowding_ratio"),
                    gaia_neighbors_within_60arcsec=fpp_data.get("gaia_neighbors_within_60arcsec"),
                    brightest_neighbor_delta_mag=fpp_data.get("brightest_neighbor_delta_mag"),
                    nearest_neighbor_arcsec=fpp_data.get("nearest_neighbor_arcsec"),
                )
            except Exception as exc:
                logger.warning(f"FPP hesabı başarısız: {exc}")

        result = QualityEvaluationResult(
            target_id=target_id,
            sector=sector,
            metrics=metrics,
            snr=snr,
            vetting=vetting,
            score=score,
            anomaly=anomaly,
            anomaly_residual=anomaly_residual,
            anomaly_transit=anomaly_transit,
            anomaly_timing=anomaly_timing,
            fpp_report=fpp_report,

        )

        logger.info(
            f"Kalite değerlendirme tamamlandı — "
            f"{target_id}: "
            f"skor={score.total_score:.1f}, "
            f"sınıf={score.candidate_class.value}, "
            f"FPP={vetting.false_positive_probability:.3f}"
        )

        return result