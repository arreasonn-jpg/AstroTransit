"""
BEB (Background Eclipsing Binary) senaryosu için basit FPP/proxy modülü.

Amaç
----
Arka plan kaynaklı eclipsing binary senaryosunun riskini
operasyonel bir skorla özetlemek.

Kullanılan göstergeler
----------------------
1. Centroid shift
2. Crowding ratio
3. Shallow + crowded transit kombinasyonu

Çıktı
-----
BEBScenarioReport
    p_beb         : 0.0 → 0.95
    beb_risk_flag : LOW_BEB_RISK / MODERATE_BEB_RISK / HIGH_BEB_RISK

Notlar
------
- Bu formal bir olasılık modeli değildir.
- primary_depth birimi relative flux fraction olmalıdır.
- crowding_ratio tipik olarak 0–1 aralığındadır; düşük değer daha kötü.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from loguru import logger

from astrotransit.quality.vetting import VettingVerdict


_CENTROID_WARN_ARCSEC = 5.0
_CENTROID_FAIL_ARCSEC = 10.0

_CROWDING_WARN = 0.90
_CROWDING_FAIL = 0.85

_SHALLOW_DEPTH_WARN_PPM = 500.0
_SHALLOW_DEPTH_FAIL_PPM = 300.0

_MAX_P_BEB = 0.95


@dataclass
class BEBIndicator:
    name: str
    available: bool
    verdict: VettingVerdict
    value: Optional[float] = None
    warn_threshold: Optional[float] = None
    fail_threshold: Optional[float] = None
    score_contribution: float = 0.0
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "available": self.available,
            "verdict": self.verdict.value,
            "value": None if self.value is None else round(float(self.value), 6),
            "warn_threshold": None if self.warn_threshold is None else round(float(self.warn_threshold), 6),
            "fail_threshold": None if self.fail_threshold is None else round(float(self.fail_threshold), 6),
            "score_contribution": round(float(self.score_contribution), 6),
            "description": self.description,
        }


@dataclass
class BEBScenarioReport:
    target_id: str
    sector: int
    p_beb: float = 0.0
    beb_risk_flag: str = "UNKNOWN"
    recommended_action: str = "none"
    indicators: list[BEBIndicator] = field(default_factory=list)
    n_available: int = 0
    n_warn: int = 0
    n_fail: int = 0
    evidence_flags: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "p_beb": round(float(self.p_beb), 4),
            "beb_risk_flag": self.beb_risk_flag,
            "recommended_action": self.recommended_action,
            "n_available": self.n_available,
            "n_warn": self.n_warn,
            "n_fail": self.n_fail,
            "evidence_flags": self.evidence_flags,
            "details": self.details,
            "indicators": [x.to_dict() for x in self.indicators],
        }

    def summary(self) -> str:
        return (
            f"{self.target_id} S{self.sector} | "
            f"p_beb={self.p_beb:.3f} flag={self.beb_risk_flag} | "
            f"available={self.n_available} warn={self.n_warn} fail={self.n_fail} | "
            f"action={self.recommended_action}"
        )


class BEBScenarioEvaluator:
    def __init__(
        self,
        centroid_warn_arcsec: float = _CENTROID_WARN_ARCSEC,
        centroid_fail_arcsec: float = _CENTROID_FAIL_ARCSEC,
        crowding_warn: float = _CROWDING_WARN,
        crowding_fail: float = _CROWDING_FAIL,
        shallow_depth_warn_ppm: float = _SHALLOW_DEPTH_WARN_PPM,
        shallow_depth_fail_ppm: float = _SHALLOW_DEPTH_FAIL_PPM,
    ):
        self.centroid_warn_arcsec = centroid_warn_arcsec
        self.centroid_fail_arcsec = centroid_fail_arcsec
        self.crowding_warn = crowding_warn
        self.crowding_fail = crowding_fail
        self.shallow_depth_warn_ppm = shallow_depth_warn_ppm
        self.shallow_depth_fail_ppm = shallow_depth_fail_ppm

        logger.debug("BEBScenarioEvaluator başlatıldı.")

    def evaluate(
        self,
        target_id: str,
        sector: int,
        centroid_shift_arcsec: Optional[float] = None,
        crowding_ratio: Optional[float] = None,
        primary_depth: Optional[float] = None,
    ) -> BEBScenarioReport:
        logger.info(f"BEB scenario evaluation başlıyor — {target_id} S{sector}")

        centroid_shift_arcsec = self._to_float_or_none(centroid_shift_arcsec)
        crowding_ratio = self._to_float_or_none(crowding_ratio)
        primary_depth = self._to_float_or_none(primary_depth)

        indicators = [
            self._indicator_centroid_shift(centroid_shift_arcsec),
            self._indicator_crowding_ratio(crowding_ratio),
            self._indicator_shallow_crowded(primary_depth, crowding_ratio),
        ]

        p_beb = self._compute_p_beb(indicators)
        beb_risk_flag = self._compute_flag(indicators, p_beb)
        recommended_action = self._recommend_action(beb_risk_flag)

        n_available = sum(1 for x in indicators if x.available)
        n_warn = sum(1 for x in indicators if x.verdict == VettingVerdict.WARN)
        n_fail = sum(1 for x in indicators if x.verdict == VettingVerdict.FAIL)
        evidence_flags = [x.name for x in indicators if x.verdict == VettingVerdict.FAIL]

        depth_ppm = None if primary_depth is None else float(primary_depth * 1e6)

        details = {
            "centroid_shift_arcsec": centroid_shift_arcsec,
            "crowding_ratio": crowding_ratio,
            "primary_depth": primary_depth,
            "primary_depth_ppm": depth_ppm,
        }

        report = BEBScenarioReport(
            target_id=target_id,
            sector=int(sector),
            p_beb=float(np.clip(p_beb, 0.0, _MAX_P_BEB)),
            beb_risk_flag=beb_risk_flag,
            recommended_action=recommended_action,
            indicators=indicators,
            n_available=n_available,
            n_warn=n_warn,
            n_fail=n_fail,
            evidence_flags=evidence_flags,
            details=details,
        )

        logger.info(f"BEB scenario evaluation tamamlandı — {report.summary()}")
        return report

    def _indicator_centroid_shift(
        self,
        centroid_shift_arcsec: Optional[float],
    ) -> BEBIndicator:
        name = "centroid_shift"

        if centroid_shift_arcsec is None or centroid_shift_arcsec < 0:
            return BEBIndicator(
                name=name,
                available=False,
                verdict=VettingVerdict.SKIP,
                description="Centroid shift girdisi eksik.",
            )

        value = float(centroid_shift_arcsec)

        if value > self.centroid_fail_arcsec:
            verdict = VettingVerdict.FAIL
            contrib = 0.40
            desc = f"Centroid shift yüksek: {value:.2f} arcsec > {self.centroid_fail_arcsec:.2f}"
        elif value > self.centroid_warn_arcsec:
            verdict = VettingVerdict.WARN
            contrib = 0.20
            desc = f"Centroid shift uyarısı: {value:.2f} arcsec"
        elif value > 2.5:
            verdict = VettingVerdict.PASS
            contrib = 0.08
            desc = f"Hafif centroid shift: {value:.2f} arcsec"
        else:
            verdict = VettingVerdict.PASS
            contrib = 0.0
            desc = f"Centroid shift düşük: {value:.2f} arcsec"

        return BEBIndicator(
            name=name,
            available=True,
            verdict=verdict,
            value=value,
            warn_threshold=self.centroid_warn_arcsec,
            fail_threshold=self.centroid_fail_arcsec,
            score_contribution=contrib,
            description=desc,
        )

    def _indicator_crowding_ratio(
        self,
        crowding_ratio: Optional[float],
    ) -> BEBIndicator:
        name = "crowding_ratio"

        if crowding_ratio is None or crowding_ratio <= 0:
            return BEBIndicator(
                name=name,
                available=False,
                verdict=VettingVerdict.SKIP,
                description="Crowding ratio girdisi eksik.",
            )

        value = float(crowding_ratio)

        if value < self.crowding_fail:
            verdict = VettingVerdict.FAIL
            contrib = 0.25
            desc = f"Crowding kötü: {value:.3f} < {self.crowding_fail:.3f}"
        elif value < self.crowding_warn:
            verdict = VettingVerdict.WARN
            contrib = 0.12
            desc = f"Crowding uyarısı: {value:.3f}"
        elif value < 0.95:
            verdict = VettingVerdict.PASS
            contrib = 0.05
            desc = f"Crowding ideal değil ama kabul edilebilir: {value:.3f}"
        else:
            verdict = VettingVerdict.PASS
            contrib = 0.0
            desc = f"Crowding iyi: {value:.3f}"

        return BEBIndicator(
            name=name,
            available=True,
            verdict=verdict,
            value=value,
            warn_threshold=self.crowding_warn,
            fail_threshold=self.crowding_fail,
            score_contribution=contrib,
            description=desc,
        )

    def _indicator_shallow_crowded(
        self,
        primary_depth: Optional[float],
        crowding_ratio: Optional[float],
    ) -> BEBIndicator:
        name = "shallow_crowded_combination"

        if (
            primary_depth is None
            or primary_depth <= 0
            or crowding_ratio is None
            or crowding_ratio <= 0
        ):
            return BEBIndicator(
                name=name,
                available=False,
                verdict=VettingVerdict.SKIP,
                description="Depth/crowding kombinasyon girdileri eksik.",
            )

        depth_ppm = float(primary_depth * 1e6)

        if depth_ppm < self.shallow_depth_fail_ppm and crowding_ratio < self.crowding_fail:
            verdict = VettingVerdict.FAIL
            contrib = 0.20
            desc = (
                f"Çok sığ + kötü crowding: depth={depth_ppm:.1f} ppm, "
                f"crowding={crowding_ratio:.3f}"
            )
        elif depth_ppm < self.shallow_depth_warn_ppm and crowding_ratio < self.crowding_warn:
            verdict = VettingVerdict.WARN
            contrib = 0.15
            desc = (
                f"Sığ + kalabalık alan uyarısı: depth={depth_ppm:.1f} ppm, "
                f"crowding={crowding_ratio:.3f}"
            )
        elif depth_ppm < 1000.0 and crowding_ratio < 0.92:
            verdict = VettingVerdict.PASS
            contrib = 0.05
            desc = (
                f"Hafif sığ/kontamine kombinasyon: depth={depth_ppm:.1f} ppm, "
                f"crowding={crowding_ratio:.3f}"
            )
        else:
            verdict = VettingVerdict.PASS
            contrib = 0.0
            desc = (
                f"Depth/crowding kombinasyonu temiz: depth={depth_ppm:.1f} ppm, "
                f"crowding={crowding_ratio:.3f}"
            )

        return BEBIndicator(
            name=name,
            available=True,
            verdict=verdict,
            value=depth_ppm,
            warn_threshold=self.shallow_depth_warn_ppm,
            fail_threshold=self.shallow_depth_fail_ppm,
            score_contribution=contrib,
            description=desc,
        )

    @staticmethod
    def _to_float_or_none(x: Optional[float]) -> Optional[float]:
        if x is None:
            return None
        try:
            x = float(x)
        except Exception:
            return None
        if not np.isfinite(x):
            return None
        return x

    @staticmethod
    def _compute_p_beb(
        indicators: list[BEBIndicator],
    ) -> float:
        total = sum(float(ind.score_contribution) for ind in indicators if ind.available)
        return float(np.clip(total, 0.0, _MAX_P_BEB))

    @staticmethod
    def _compute_flag(
        indicators: list[BEBIndicator],
        p_beb: float,
    ) -> str:
        n_fail = sum(1 for ind in indicators if ind.verdict == VettingVerdict.FAIL)
        n_warn = sum(1 for ind in indicators if ind.verdict == VettingVerdict.WARN)

        if n_fail >= 1 or p_beb >= 0.50:
            return "HIGH_BEB_RISK"
        if n_warn >= 1 or p_beb >= 0.20:
            return "MODERATE_BEB_RISK"

        active = sum(1 for ind in indicators if ind.available)
        if active == 0:
            return "UNKNOWN"

        return "LOW_BEB_RISK"

    @staticmethod
    def _recommend_action(
        beb_risk_flag: str,
    ) -> str:
        if beb_risk_flag == "LOW_BEB_RISK":
            return "background_eb_not_supported"
        if beb_risk_flag == "MODERATE_BEB_RISK":
            return "inspect_centroid_and_crowding"
        if beb_risk_flag == "HIGH_BEB_RISK":
            return "deprioritize_as_possible_background_eb"
        return "insufficient_data"
