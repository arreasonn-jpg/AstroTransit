"""
Basit FPP birleştirici modülü.

Amaç
----
EB, BEB ve NEB senaryo risklerini tek bir operasyonel
False Positive Probability (FPP) özetinde birleştirmek.

Girdi
-----
- EBScenarioReport
- BEBScenarioReport
- NEBScenarioReport

veya ham metrikler (opsiyonel)

Çıktı
-----
SimpleFPPReport
    p_eb
    p_beb
    p_neb
    fpp
    p_planet
    dominant_scenario
    confidence

Not
---
Bu formal bir Bayesian validasyon aracı değildir.
Amaç, triceratops yokken tutarlı bir karar-proxy üretmektir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from loguru import logger

from astrotransit.quality.fpp.eb_test import EBScenarioEvaluator, EBScenarioReport
from astrotransit.quality.fpp.beb_test import BEBScenarioEvaluator, BEBScenarioReport
from astrotransit.quality.fpp.neb_test import NEBScenarioEvaluator, NEBScenarioReport


@dataclass
class FPPComponent:
    name: str
    available: bool
    probability: Optional[float] = None
    risk_flag: str = "UNKNOWN"
    recommended_action: str = "none"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "available": self.available,
            "probability": None if self.probability is None else round(float(self.probability), 6),
            "risk_flag": self.risk_flag,
            "recommended_action": self.recommended_action,
        }


@dataclass
class SimpleFPPReport:
    target_id: str
    sector: int
    p_eb: float = 0.0
    p_beb: float = 0.0
    p_neb: float = 0.0
    fpp: float = 0.0
    p_planet: float = 1.0
    dominant_scenario: str = "none"
    confidence: str = "UNKNOWN"
    recommended_action: str = "none"
    components: list[FPPComponent] = field(default_factory=list)
    n_available: int = 0
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "p_eb": round(float(self.p_eb), 4),
            "p_beb": round(float(self.p_beb), 4),
            "p_neb": round(float(self.p_neb), 4),
            "fpp": round(float(self.fpp), 4),
            "p_planet": round(float(self.p_planet), 4),
            "dominant_scenario": self.dominant_scenario,
            "confidence": self.confidence,
            "recommended_action": self.recommended_action,
            "n_available": self.n_available,
            "details": self.details,
            "components": [c.to_dict() for c in self.components],
        }

    def summary(self) -> str:
        return (
            f"{self.target_id} S{self.sector} | "
            f"FPP={self.fpp:.3f} Pplanet={self.p_planet:.3f} | "
            f"dominant={self.dominant_scenario} confidence={self.confidence} | "
            f"available={self.n_available} action={self.recommended_action}"
        )


class SimpleFPPCalculator:
    """
    Basit FPP hesaplayıcı.

    İki kullanım yolu:
    1. Hazır EB/BEB/NEB raporlarını ver
    2. Ham metrikleri ver, gerekli alt raporlar otomatik üretilsin
    """

    def __init__(
        self,
        eb_evaluator: Optional[EBScenarioEvaluator] = None,
        beb_evaluator: Optional[BEBScenarioEvaluator] = None,
        neb_evaluator: Optional[NEBScenarioEvaluator] = None,
    ):
        self.eb_evaluator = eb_evaluator or EBScenarioEvaluator()
        self.beb_evaluator = beb_evaluator or BEBScenarioEvaluator()
        self.neb_evaluator = neb_evaluator or NEBScenarioEvaluator()

        logger.debug("SimpleFPPCalculator başlatıldı.")

    def calculate(
        self,
        target_id: Optional[str] = None,
        sector: Optional[int] = None,
        eb_report: Optional[EBScenarioReport] = None,
        beb_report: Optional[BEBScenarioReport] = None,
        neb_report: Optional[NEBScenarioReport] = None,
        primary_depth: Optional[float] = None,
        odd_depth: Optional[float] = None,
        even_depth: Optional[float] = None,
        v_shape_score: Optional[float] = None,
        secondary_depth: Optional[float] = None,
        n_transits: Optional[int] = None,
        centroid_shift_arcsec: Optional[float] = None,
        crowding_ratio: Optional[float] = None,
        gaia_neighbors_within_60arcsec: Optional[int] = None,
        brightest_neighbor_delta_mag: Optional[float] = None,
        nearest_neighbor_arcsec: Optional[float] = None,
    ) -> SimpleFPPReport:
        """
        Birleşik FPP raporu üretir.
        """

        target_id_resolved, sector_resolved = self._resolve_identity(
            target_id=target_id,
            sector=sector,
            eb_report=eb_report,
            beb_report=beb_report,
            neb_report=neb_report,
        )

        logger.info(
            f"Simple FPP calculation başlıyor — {target_id_resolved} S{sector_resolved}"
        )

        # Mevcut rapor yoksa ve ilgili ham girdiler varsa üret
        if eb_report is None and any(
            x is not None
            for x in [primary_depth, odd_depth, even_depth, v_shape_score, secondary_depth]
        ):
            eb_report = self.eb_evaluator.evaluate(
                target_id=target_id_resolved,
                sector=sector_resolved,
                primary_depth=primary_depth,
                odd_depth=odd_depth,
                even_depth=even_depth,
                v_shape_score=v_shape_score,
                secondary_depth=secondary_depth,
                n_transits=n_transits,
            )

        if beb_report is None and any(
            x is not None
            for x in [centroid_shift_arcsec, crowding_ratio, primary_depth]
        ):
            beb_report = self.beb_evaluator.evaluate(
                target_id=target_id_resolved,
                sector=sector_resolved,
                centroid_shift_arcsec=centroid_shift_arcsec,
                crowding_ratio=crowding_ratio,
                primary_depth=primary_depth,
            )

        if neb_report is None and any(
            x is not None
            for x in [
                gaia_neighbors_within_60arcsec,
                brightest_neighbor_delta_mag,
                nearest_neighbor_arcsec,
            ]
        ):
            neb_report = self.neb_evaluator.evaluate(
                target_id=target_id_resolved,
                sector=sector_resolved,
                gaia_neighbors_within_60arcsec=gaia_neighbors_within_60arcsec,
                brightest_neighbor_delta_mag=brightest_neighbor_delta_mag,
                nearest_neighbor_arcsec=nearest_neighbor_arcsec,
            )

        p_eb = self._safe_prob(getattr(eb_report, "p_eb", 0.0) if eb_report else 0.0)
        p_beb = self._safe_prob(getattr(beb_report, "p_beb", 0.0) if beb_report else 0.0)
        p_neb = self._safe_prob(getattr(neb_report, "p_neb", 0.0) if neb_report else 0.0)

        fpp = self._combine_probabilities([p_eb, p_beb, p_neb])
        p_planet = float(np.clip(1.0 - fpp, 0.0, 1.0))

        components = [
            FPPComponent(
                name="eb",
                available=eb_report is not None,
                probability=p_eb if eb_report is not None else None,
                risk_flag=getattr(eb_report, "eb_risk_flag", "UNKNOWN") if eb_report else "MISSING",
                recommended_action=getattr(eb_report, "recommended_action", "none") if eb_report else "none",
            ),
            FPPComponent(
                name="beb",
                available=beb_report is not None,
                probability=p_beb if beb_report is not None else None,
                risk_flag=getattr(beb_report, "beb_risk_flag", "UNKNOWN") if beb_report else "MISSING",
                recommended_action=getattr(beb_report, "recommended_action", "none") if beb_report else "none",
            ),
            FPPComponent(
                name="neb",
                available=neb_report is not None,
                probability=p_neb if neb_report is not None else None,
                risk_flag=getattr(neb_report, "neb_risk_flag", "UNKNOWN") if neb_report else "MISSING",
                recommended_action=getattr(neb_report, "recommended_action", "none") if neb_report else "none",
            ),
        ]

        dominant_scenario = self._dominant_scenario(
            p_eb=p_eb,
            p_beb=p_beb,
            p_neb=p_neb,
            components=components,
        )
        confidence = self._compute_confidence(fpp=fpp, components=components)
        recommended_action = self._recommend_action(confidence=confidence, fpp=fpp, components=components)

        details = {
            "combination_method": "1 - product(1 - p_i)",
            "raw_probabilities": {
                "p_eb": float(p_eb),
                "p_beb": float(p_beb),
                "p_neb": float(p_neb),
            },
            "component_flags": {
                "eb": getattr(eb_report, "eb_risk_flag", "MISSING") if eb_report else "MISSING",
                "beb": getattr(beb_report, "beb_risk_flag", "MISSING") if beb_report else "MISSING",
                "neb": getattr(neb_report, "neb_risk_flag", "MISSING") if neb_report else "MISSING",
            },
        }

        if eb_report is not None:
            details["eb_summary"] = eb_report.summary()
        if beb_report is not None:
            details["beb_summary"] = beb_report.summary()
        if neb_report is not None:
            details["neb_summary"] = neb_report.summary()

        report = SimpleFPPReport(
            target_id=target_id_resolved,
            sector=sector_resolved,
            p_eb=p_eb,
            p_beb=p_beb,
            p_neb=p_neb,
            fpp=fpp,
            p_planet=p_planet,
            dominant_scenario=dominant_scenario,
            confidence=confidence,
            recommended_action=recommended_action,
            components=components,
            n_available=sum(1 for c in components if c.available),
            details=details,
        )

        logger.info(f"Simple FPP calculation tamamlandı — {report.summary()}")
        return report

    @staticmethod
    def _resolve_identity(
        target_id: Optional[str],
        sector: Optional[int],
        eb_report: Optional[EBScenarioReport],
        beb_report: Optional[BEBScenarioReport],
        neb_report: Optional[NEBScenarioReport],
    ) -> tuple[str, int]:
        if target_id is not None and sector is not None:
            return target_id, int(sector)

        for rep in [eb_report, beb_report, neb_report]:
            if rep is not None:
                return rep.target_id, int(rep.sector)

        return target_id or "UNKNOWN_TARGET", int(sector if sector is not None else -1)

    @staticmethod
    def _safe_prob(x: float) -> float:
        try:
            x = float(x)
        except Exception:
            return 0.0
        if not np.isfinite(x):
            return 0.0
        return float(np.clip(x, 0.0, 0.999))

    @staticmethod
    def _combine_probabilities(probs: list[float]) -> float:
        active = [float(np.clip(p, 0.0, 0.999)) for p in probs if p is not None]
        if not active:
            return 0.0

        survival = 1.0
        for p in active:
            survival *= (1.0 - p)

        return float(np.clip(1.0 - survival, 0.0, 0.999))

    @staticmethod
    def _dominant_scenario(
        p_eb: float,
        p_beb: float,
        p_neb: float,
        components: list[FPPComponent],
    ) -> str:
        available = {c.name: c.available for c in components}
        probs = {
            "eb": p_eb if available.get("eb", False) else -1.0,
            "beb": p_beb if available.get("beb", False) else -1.0,
            "neb": p_neb if available.get("neb", False) else -1.0,
        }

        best_name = max(probs, key=probs.get)
        if probs[best_name] < 0:
            return "none"
        return best_name

    @staticmethod
    def _compute_confidence(
        fpp: float,
        components: list[FPPComponent],
    ) -> str:
        available = [c for c in components if c.available]
        if not available:
            return "UNKNOWN"

        high_risk = any("HIGH_" in c.risk_flag for c in available)
        moderate_risk = any("MODERATE_" in c.risk_flag for c in available)

        if not high_risk and not moderate_risk and fpp < 0.05:
            return "HIGH"

        if not high_risk and fpp < 0.20:
            return "MEDIUM"

        return "LOW"

    @staticmethod
    def _recommend_action(
        confidence: str,
        fpp: float,
        components: list[FPPComponent],
    ) -> str:
        if confidence == "HIGH":
            return "proceed_to_followup"

        if confidence == "MEDIUM":
            return "manual_fp_review"

        if confidence == "LOW":
            dominant = None
            available = [c for c in components if c.available and c.probability is not None]
            if available:
                dominant = max(available, key=lambda c: float(c.probability)).name
            return f"deprioritize_or_inspect_{dominant or 'fp_scenario'}"

        return "insufficient_data"
