# astrotransit/quality/anomaly_scorer.py
"""
Birleşik anomaly scoring modülü.

Amaç
----
Residual, transit consistency ve timing analizlerinden gelen
raporları tek bir anomaly skorunda birleştirmek.

Girdi modülleri
---------------
- ResidualReport
- TransitConsistencyReport
- TimingReport

Çıktı
-----
AnomalyReport
    anomaly_score : 0.0 → 1.0
    anomaly_flag  : CLEAN / REVIEW / REJECT

Not
---
Bu modül FPP hesaplamaz.
Sadece sinyalin şekilsel / istatistiksel anomali durumunu özetler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from loguru import logger

from astrotransit.quality.residual_analysis import ResidualReport
from astrotransit.quality.transit_consistency import TransitConsistencyReport
from astrotransit.quality.timing_analysis import TimingReport


# ──────────────────────────────────────────────────────────────
# Varsayılan ağırlıklar
# ──────────────────────────────────────────────────────────────

_DEFAULT_RESIDUAL_WEIGHT = 0.35
_DEFAULT_TRANSIT_WEIGHT = 0.40
_DEFAULT_TIMING_WEIGHT = 0.25


# ──────────────────────────────────────────────────────────────
# Yardımcı dataclass
# ──────────────────────────────────────────────────────────────

@dataclass
class AnomalyComponent:
    """
    Tek bir anomaly bileşeninin özeti.
    """

    name: str
    available: bool
    weight: float
    score: Optional[float] = None
    flag: str = "MISSING"
    severe: bool = False
    moderate: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "available": self.available,
            "weight": round(float(self.weight), 4),
            "score": None if self.score is None else round(float(self.score), 4),
            "flag": self.flag,
            "severe": self.severe,
            "moderate": self.moderate,
        }


# ──────────────────────────────────────────────────────────────
# Birleşik rapor
# ──────────────────────────────────────────────────────────────

@dataclass
class AnomalyReport:
    """
    Birleşik anomaly raporu.
    """

    target_id: str
    sector: int
    anomaly_score: float = 0.0
    anomaly_flag: str = "UNKNOWN"
    recommended_action: str = "none"
    components: list[AnomalyComponent] = field(default_factory=list)
    n_available: int = 0
    n_severe: int = 0
    n_moderate: int = 0
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "anomaly_score": round(float(self.anomaly_score), 4),
            "anomaly_flag": self.anomaly_flag,
            "recommended_action": self.recommended_action,
            "n_available": self.n_available,
            "n_severe": self.n_severe,
            "n_moderate": self.n_moderate,
            "details": self.details,
            "components": [c.to_dict() for c in self.components],
        }

    def summary(self) -> str:
        return (
            f"{self.target_id} S{self.sector} | "
            f"anomaly_flag={self.anomaly_flag} score={self.anomaly_score:.3f} | "
            f"available={self.n_available} severe={self.n_severe} moderate={self.n_moderate} | "
            f"action={self.recommended_action}"
        )


# ──────────────────────────────────────────────────────────────
# Scorer
# ──────────────────────────────────────────────────────────────

class AnomalyScorer:
    """
    Birleşik anomaly scorer.

    Parameters
    ----------
    residual_weight : float
        Residual analiz ağırlığı.
    transit_weight : float
        Transit consistency ağırlığı.
    timing_weight : float
        Timing analiz ağırlığı.
    """

    def __init__(
        self,
        residual_weight: float = _DEFAULT_RESIDUAL_WEIGHT,
        transit_weight: float = _DEFAULT_TRANSIT_WEIGHT,
        timing_weight: float = _DEFAULT_TIMING_WEIGHT,
    ):
        self.residual_weight = residual_weight
        self.transit_weight = transit_weight
        self.timing_weight = timing_weight

        logger.debug("AnomalyScorer başlatıldı.")

    def score(
        self,
        residual_report: Optional[ResidualReport] = None,
        transit_report: Optional[TransitConsistencyReport] = None,
        timing_report: Optional[TimingReport] = None,
    ) -> AnomalyReport:
        """
        Alt raporları birleştirerek tek anomaly raporu üretir.
        """

        target_id, sector = self._resolve_identity(
            residual_report=residual_report,
            transit_report=transit_report,
            timing_report=timing_report,
        )

        logger.info(f"Birleşik anomaly scoring başlıyor — {target_id} S{sector}")

        components = [
            self._build_residual_component(residual_report),
            self._build_transit_component(transit_report),
            self._build_timing_component(timing_report),
        ]

        anomaly_score = self._compute_weighted_score(components)
        anomaly_flag = self._compute_flag(components, anomaly_score)
        recommended_action = self._recommend_action(anomaly_flag, components)

        n_available = sum(1 for c in components if c.available)
        n_severe = sum(1 for c in components if c.severe)
        n_moderate = sum(1 for c in components if c.moderate)

        details = self._build_details(
            residual_report=residual_report,
            transit_report=transit_report,
            timing_report=timing_report,
            components=components,
            anomaly_score=anomaly_score,
        )

        report = AnomalyReport(
            target_id=target_id,
            sector=sector,
            anomaly_score=anomaly_score,
            anomaly_flag=anomaly_flag,
            recommended_action=recommended_action,
            components=components,
            n_available=n_available,
            n_severe=n_severe,
            n_moderate=n_moderate,
            details=details,
        )

        logger.info(f"Birleşik anomaly scoring tamamlandı — {report.summary()}")
        return report

    # ──────────────────────────────────────
    # Bileşen oluşturucular
    # ──────────────────────────────────────

    def _build_residual_component(
        self,
        report: Optional[ResidualReport],
    ) -> AnomalyComponent:
        if report is None:
            return AnomalyComponent(
                name="residual",
                available=False,
                weight=self.residual_weight,
                flag="MISSING",
            )

        severe = report.flag == "ANOMALOUS"
        moderate = report.flag == "SUSPECT"

        return AnomalyComponent(
            name="residual",
            available=True,
            weight=self.residual_weight,
            score=float(np.clip(report.score, 0.0, 1.0)),
            flag=report.flag,
            severe=severe,
            moderate=moderate,
        )

    def _build_transit_component(
        self,
        report: Optional[TransitConsistencyReport],
    ) -> AnomalyComponent:
        if report is None:
            return AnomalyComponent(
                name="transit_consistency",
                available=False,
                weight=self.transit_weight,
                flag="MISSING",
            )

        severe = report.flag == "EB_SUSPECT"
        moderate = report.flag == "VARIABLE"

        return AnomalyComponent(
            name="transit_consistency",
            available=True,
            weight=self.transit_weight,
            score=float(np.clip(report.score, 0.0, 1.0)),
            flag=report.flag,
            severe=severe,
            moderate=moderate,
        )

    def _build_timing_component(
        self,
        report: Optional[TimingReport],
    ) -> AnomalyComponent:
        if report is None:
            return AnomalyComponent(
                name="timing",
                available=False,
                weight=self.timing_weight,
                flag="MISSING",
            )

        severe = report.flag == "TIMING_UNSTABLE"
        moderate = report.flag == "TTV_CANDIDATE"

        return AnomalyComponent(
            name="timing",
            available=True,
            weight=self.timing_weight,
            score=float(np.clip(report.score, 0.0, 1.0)),
            flag=report.flag,
            severe=severe,
            moderate=moderate,
        )

    # ──────────────────────────────────────
    # Skor / flag
    # ──────────────────────────────────────

    @staticmethod
    def _compute_weighted_score(
        components: list[AnomalyComponent],
    ) -> float:
        """
        Ağırlıklı ortalama anomaly skoru.

        Yalnızca available olan bileşenler kullanılır.
        """

        active = [c for c in components if c.available and c.score is not None]
        if not active:
            return 0.0

        total_weight = sum(c.weight for c in active)
        if total_weight <= 0:
            return 0.0

        weighted_sum = sum(c.weight * float(c.score) for c in active)
        return float(np.clip(weighted_sum / total_weight, 0.0, 1.0))

    @staticmethod
    def _compute_flag(
        components: list[AnomalyComponent],
        anomaly_score: float,
    ) -> str:
        """
        Genel anomaly bayrağı.

        CLEAN
            Düşük skor, severe bileşen yok.
        REVIEW
            Orta seviye anomali / dikkat gerektirir.
        REJECT
            Güçlü şekilsel sorun / EB benzeri davranış / ağır instability.
        """

        n_available = sum(1 for c in components if c.available)
        n_severe = sum(1 for c in components if c.severe)
        n_moderate = sum(1 for c in components if c.moderate)

        if n_available == 0:
            return "UNKNOWN"

        severe_names = {c.name for c in components if c.severe}

        # Transit tarafında güçlü EB şüphesi varsa bunu ağır ele al
        if (
            "transit_consistency" in severe_names
            or n_severe >= 2
            or anomaly_score >= 0.60
        ):
            return "REJECT"

        if (
            n_severe == 1
            or n_moderate >= 1
            or anomaly_score >= 0.25
        ):
            return "REVIEW"

        return "CLEAN"

    @staticmethod
    def _recommend_action(
        anomaly_flag: str,
        components: list[AnomalyComponent],
    ) -> str:
        """
        Operasyonel sonraki adım önerisi.
        """

        if anomaly_flag == "CLEAN":
            return "proceed_to_followup"

        if anomaly_flag == "REVIEW":
            severe_names = {c.name for c in components if c.severe}
            moderate_names = {c.name for c in components if c.moderate}

            if "timing" in severe_names or "timing" in moderate_names:
                return "manual_timing_review"

            if "residual" in severe_names or "residual" in moderate_names:
                return "inspect_residuals_and_folded_transit"

            return "manual_vetting_review"

        if anomaly_flag == "REJECT":
            return "deprioritize_or_reinspect"

        return "insufficient_data"

    # ──────────────────────────────────────
    # Kimlik ve detaylar
    # ──────────────────────────────────────

    @staticmethod
    def _resolve_identity(
        residual_report: Optional[ResidualReport],
        transit_report: Optional[TransitConsistencyReport],
        timing_report: Optional[TimingReport],
    ) -> tuple[str, int]:
        """
        İlk mevcut rapordan target_id ve sector alır.
        """

        reports = [residual_report, transit_report, timing_report]
        available = [r for r in reports if r is not None]

        if not available:
            return "UNKNOWN_TARGET", -1

        target_id = available[0].target_id
        sector = available[0].sector

        for rep in available[1:]:
            if rep.target_id != target_id or rep.sector != sector:
                logger.warning(
                    "AnomalyScorer: rapor kimlikleri tam eşleşmiyor. "
                    f"İlk rapor kullanılacak: {target_id} S{sector}"
                )
                break

        return target_id, sector

    @staticmethod
    def _build_details(
        residual_report: Optional[ResidualReport],
        transit_report: Optional[TransitConsistencyReport],
        timing_report: Optional[TimingReport],
        components: list[AnomalyComponent],
        anomaly_score: float,
    ) -> dict:
        """
        Downstream kullanım için detay alanı.
        """

        details: dict = {
            "anomaly_score": float(anomaly_score),
            "weights": {
                c.name: float(c.weight) for c in components
            },
            "component_flags": {
                c.name: c.flag for c in components
            },
            "component_scores": {
                c.name: None if c.score is None else float(c.score)
                for c in components
            },
        }

        if residual_report is not None:
            details["residual_summary"] = residual_report.summary()

        if transit_report is not None:
            details["transit_summary"] = transit_report.summary()

        if timing_report is not None:
            details["timing_summary"] = timing_report.summary()

        return details