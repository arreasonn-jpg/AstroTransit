"""
EB (Eclipsing Binary) senaryosu için basit FPP/proxy modülü.

Amaç
----
Bir transit adayının self-eclipsing binary olma riskini
basit ama sistematik bir skorla özetlemek.

Kullanılan göstergeler
----------------------
1. Even/Odd transit depth farkı
2. V-shape metriği
3. Secondary eclipse oranı

Çıktı
-----
EBScenarioReport
    p_eb        : 0.0 → 0.95
    eb_risk_flag: LOW_EB_RISK / MODERATE_EB_RISK / HIGH_EB_RISK
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from loguru import logger

from astrotransit.quality.transit_consistency import TransitConsistencyReport
from astrotransit.quality.vetting import VettingReport, VettingVerdict


_EVEN_ODD_WARN = 0.15
_EVEN_ODD_FAIL = 0.30

_VSHAPE_WARN = 0.65
_VSHAPE_FAIL = 0.85

_SECONDARY_RATIO_WARN = 0.25
_SECONDARY_RATIO_FAIL = 0.50

_MAX_P_EB = 0.95
_MIN_TRANSITS_FOR_EVEN_ODD = 4


@dataclass
class EBIndicator:
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
class EBScenarioReport:
    target_id: str
    sector: int
    p_eb: float = 0.0
    eb_risk_flag: str = "UNKNOWN"
    recommended_action: str = "none"
    indicators: list[EBIndicator] = field(default_factory=list)
    n_available: int = 0
    n_warn: int = 0
    n_fail: int = 0
    evidence_flags: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "p_eb": round(float(self.p_eb), 4),
            "eb_risk_flag": self.eb_risk_flag,
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
            f"p_eb={self.p_eb:.3f} flag={self.eb_risk_flag} | "
            f"available={self.n_available} warn={self.n_warn} fail={self.n_fail} | "
            f"action={self.recommended_action}"
        )


class EBScenarioEvaluator:
    def __init__(
        self,
        even_odd_warn: float = _EVEN_ODD_WARN,
        even_odd_fail: float = _EVEN_ODD_FAIL,
        vshape_warn: float = _VSHAPE_WARN,
        vshape_fail: float = _VSHAPE_FAIL,
        secondary_ratio_warn: float = _SECONDARY_RATIO_WARN,
        secondary_ratio_fail: float = _SECONDARY_RATIO_FAIL,
    ):
        self.even_odd_warn = even_odd_warn
        self.even_odd_fail = even_odd_fail
        self.vshape_warn = vshape_warn
        self.vshape_fail = vshape_fail
        self.secondary_ratio_warn = secondary_ratio_warn
        self.secondary_ratio_fail = secondary_ratio_fail

        logger.debug("EBScenarioEvaluator başlatıldı.")

    def evaluate(
        self,
        target_id: Optional[str] = None,
        sector: Optional[int] = None,
        primary_depth: Optional[float] = None,
        odd_depth: Optional[float] = None,
        even_depth: Optional[float] = None,
        v_shape_score: Optional[float] = None,
        secondary_depth: Optional[float] = None,
        n_transits: Optional[int] = None,
        transit_report: Optional[TransitConsistencyReport] = None,
        vetting_report: Optional[VettingReport] = None,
    ) -> EBScenarioReport:
        target_id_resolved, sector_resolved = self._resolve_identity(
            target_id=target_id,
            sector=sector,
            transit_report=transit_report,
            vetting_report=vetting_report,
        )

        logger.info(
            f"EB scenario evaluation başlıyor — {target_id_resolved} S{sector_resolved}"
        )

        resolved = self._resolve_metrics(
            primary_depth=primary_depth,
            odd_depth=odd_depth,
            even_depth=even_depth,
            v_shape_score=v_shape_score,
            secondary_depth=secondary_depth,
            n_transits=n_transits,
            transit_report=transit_report,
            vetting_report=vetting_report,
        )

        indicators = [
            self._indicator_even_odd(
                primary_depth=resolved["primary_depth"],
                odd_depth=resolved["odd_depth"],
                even_depth=resolved["even_depth"],
                n_transits=resolved["n_transits"],
            ),
            self._indicator_vshape(
                v_shape_score=resolved["v_shape_score"],
            ),
            self._indicator_secondary(
                primary_depth=resolved["primary_depth"],
                secondary_depth=resolved["secondary_depth"],
            ),
        ]

        p_eb = self._compute_p_eb(indicators)
        eb_risk_flag = self._compute_flag(indicators, p_eb)
        recommended_action = self._recommend_action(eb_risk_flag)

        n_available = sum(1 for x in indicators if x.available)
        n_warn = sum(1 for x in indicators if x.verdict == VettingVerdict.WARN)
        n_fail = sum(1 for x in indicators if x.verdict == VettingVerdict.FAIL)
        evidence_flags = [x.name for x in indicators if x.verdict == VettingVerdict.FAIL]

        details = {
            "resolved_primary_depth": resolved["primary_depth"],
            "resolved_odd_depth": resolved["odd_depth"],
            "resolved_even_depth": resolved["even_depth"],
            "resolved_v_shape_score": resolved["v_shape_score"],
            "resolved_secondary_depth": resolved["secondary_depth"],
            "resolved_n_transits": resolved["n_transits"],
        }

        report = EBScenarioReport(
            target_id=target_id_resolved,
            sector=sector_resolved,
            p_eb=float(np.clip(p_eb, 0.0, _MAX_P_EB)),
            eb_risk_flag=eb_risk_flag,
            recommended_action=recommended_action,
            indicators=indicators,
            n_available=n_available,
            n_warn=n_warn,
            n_fail=n_fail,
            evidence_flags=evidence_flags,
            details=details,
        )

        logger.info(f"EB scenario evaluation tamamlandı — {report.summary()}")
        return report

    def _indicator_even_odd(
        self,
        primary_depth: Optional[float],
        odd_depth: Optional[float],
        even_depth: Optional[float],
        n_transits: Optional[int],
    ) -> EBIndicator:
        name = "even_odd_depth_difference"

        if n_transits is not None and int(n_transits) < _MIN_TRANSITS_FOR_EVEN_ODD:
            return EBIndicator(
                name=name,
                available=False,
                verdict=VettingVerdict.SKIP,
                description=f"Even/odd için yetersiz transit sayısı: {n_transits} < {_MIN_TRANSITS_FOR_EVEN_ODD}",
            )

        if (
            primary_depth is None
            or odd_depth is None
            or even_depth is None
            or primary_depth <= 0
        ):
            return EBIndicator(
                name=name,
                available=False,
                verdict=VettingVerdict.SKIP,
                description="Even/odd derinlik girdileri eksik.",
            )

        frac_diff = abs(float(odd_depth) - float(even_depth)) / float(primary_depth)

        if frac_diff > self.even_odd_fail:
            verdict = VettingVerdict.FAIL
            contrib = 0.35
            desc = f"Even/odd farkı yüksek: {frac_diff:.3f} > {self.even_odd_fail:.3f} (EB şüphesi)"
        elif frac_diff > self.even_odd_warn:
            verdict = VettingVerdict.WARN
            contrib = 0.18
            desc = f"Even/odd farkı uyarısı: {frac_diff:.3f}"
        elif frac_diff > 0.10:
            verdict = VettingVerdict.PASS
            contrib = 0.05
            desc = f"Even/odd farkı küçük ama sıfır değil: {frac_diff:.3f}"
        else:
            verdict = VettingVerdict.PASS
            contrib = 0.0
            desc = f"Even/odd farkı düşük: {frac_diff:.3f}"

        return EBIndicator(
            name=name,
            available=True,
            verdict=verdict,
            value=float(frac_diff),
            warn_threshold=self.even_odd_warn,
            fail_threshold=self.even_odd_fail,
            score_contribution=contrib,
            description=desc,
        )

    def _indicator_vshape(
        self,
        v_shape_score: Optional[float],
    ) -> EBIndicator:
        name = "v_shape_metric"

        if v_shape_score is None or not np.isfinite(v_shape_score):
            return EBIndicator(
                name=name,
                available=False,
                verdict=VettingVerdict.SKIP,
                description="V-shape girdisi eksik.",
            )

        score = float(v_shape_score)

        if score > self.vshape_fail:
            verdict = VettingVerdict.FAIL
            contrib = 0.30
            desc = f"Belirgin V-shape: {score:.3f} > {self.vshape_fail:.3f}"
        elif score > self.vshape_warn:
            verdict = VettingVerdict.WARN
            contrib = 0.15
            desc = f"V-shape uyarısı: {score:.3f}"
        elif score > 0.55:
            verdict = VettingVerdict.PASS
            contrib = 0.05
            desc = f"Hafif V-shape eğilimi: {score:.3f}"
        else:
            verdict = VettingVerdict.PASS
            contrib = 0.0
            desc = f"U-shape ile uyumlu: {score:.3f}"

        return EBIndicator(
            name=name,
            available=True,
            verdict=verdict,
            value=score,
            warn_threshold=self.vshape_warn,
            fail_threshold=self.vshape_fail,
            score_contribution=contrib,
            description=desc,
        )

    def _indicator_secondary(
        self,
        primary_depth: Optional[float],
        secondary_depth: Optional[float],
    ) -> EBIndicator:
        name = "secondary_eclipse_ratio"

        if (
            primary_depth is None
            or secondary_depth is None
            or primary_depth <= 0
            or secondary_depth < 0
        ):
            return EBIndicator(
                name=name,
                available=False,
                verdict=VettingVerdict.SKIP,
                description="Secondary eclipse girdileri eksik.",
            )

        ratio = float(secondary_depth) / float(primary_depth)

        if ratio > self.secondary_ratio_fail:
            verdict = VettingVerdict.FAIL
            contrib = 0.30
            desc = f"Secondary eclipse oranı yüksek: {ratio:.3f} > {self.secondary_ratio_fail:.3f}"
        elif ratio > self.secondary_ratio_warn:
            verdict = VettingVerdict.WARN
            contrib = 0.15
            desc = f"Secondary eclipse uyarısı: oran={ratio:.3f}"
        elif ratio > 0.10:
            verdict = VettingVerdict.PASS
            contrib = 0.05
            desc = f"Zayıf secondary sinyal: oran={ratio:.3f}"
        else:
            verdict = VettingVerdict.PASS
            contrib = 0.0
            desc = f"Secondary eclipse belirgin değil: oran={ratio:.3f}"

        return EBIndicator(
            name=name,
            available=True,
            verdict=verdict,
            value=ratio,
            warn_threshold=self.secondary_ratio_warn,
            fail_threshold=self.secondary_ratio_fail,
            score_contribution=contrib,
            description=desc,
        )

    @staticmethod
    def _resolve_identity(
        target_id: Optional[str],
        sector: Optional[int],
        transit_report: Optional[TransitConsistencyReport],
        vetting_report: Optional[VettingReport],
    ) -> tuple[str, int]:
        if target_id is not None and sector is not None:
            return target_id, int(sector)
        if transit_report is not None:
            return transit_report.target_id, int(transit_report.sector)
        if vetting_report is not None:
            return vetting_report.target_id, int(vetting_report.sector)
        return target_id or "UNKNOWN_TARGET", int(sector if sector is not None else -1)

    def _resolve_metrics(
        self,
        primary_depth: Optional[float],
        odd_depth: Optional[float],
        even_depth: Optional[float],
        v_shape_score: Optional[float],
        secondary_depth: Optional[float],
        n_transits: Optional[int],
        transit_report: Optional[TransitConsistencyReport],
        vetting_report: Optional[VettingReport],
    ) -> dict:
        resolved_primary = primary_depth
        resolved_odd = odd_depth
        resolved_even = even_depth
        resolved_vshape = v_shape_score
        resolved_secondary = secondary_depth
        resolved_n_transits = n_transits

        if transit_report is not None:
            details = transit_report.details or {}
            if resolved_n_transits is None:
                resolved_n_transits = details.get("n_transits")

            if resolved_primary is None:
                resolved_primary = details.get("per_transit_depth_median")
            if resolved_primary is None:
                resolved_primary = details.get("median_intransit_depth")

            if resolved_odd is None:
                resolved_odd = details.get("odd_depth_median")
            if resolved_even is None:
                resolved_even = details.get("even_depth_median")

            if resolved_vshape is None:
                resolved_vshape = self._get_test_value(transit_report, "v_shape_metric")

        if vetting_report is not None and resolved_secondary is None:
            resolved_secondary = self._get_test_value(vetting_report, "secondary_eclipse")

        return {
            "primary_depth": self._to_float_or_none(resolved_primary),
            "odd_depth": self._to_float_or_none(resolved_odd),
            "even_depth": self._to_float_or_none(resolved_even),
            "v_shape_score": self._to_float_or_none(resolved_vshape),
            "secondary_depth": self._to_float_or_none(resolved_secondary),
            "n_transits": None if resolved_n_transits is None else int(resolved_n_transits),
        }

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
    def _get_test_value(report, test_name: str) -> Optional[float]:
        tests = getattr(report, "tests", None)
        if not tests:
            return None

        for test in tests:
            if getattr(test, "name", None) == test_name:
                value = getattr(test, "value", None)
                try:
                    value = float(value)
                except Exception:
                    return None
                return value if np.isfinite(value) else None
        return None

    @staticmethod
    def _compute_p_eb(
        indicators: list[EBIndicator],
    ) -> float:
        total = sum(float(ind.score_contribution) for ind in indicators if ind.available)
        return float(np.clip(total, 0.0, _MAX_P_EB))

    @staticmethod
    def _compute_flag(
        indicators: list[EBIndicator],
        p_eb: float,
    ) -> str:
        n_fail = sum(1 for ind in indicators if ind.verdict == VettingVerdict.FAIL)
        n_warn = sum(1 for ind in indicators if ind.verdict == VettingVerdict.WARN)

        if n_fail >= 1 or p_eb >= 0.50:
            return "HIGH_EB_RISK"
        if n_warn >= 1 or p_eb >= 0.20:
            return "MODERATE_EB_RISK"

        active = sum(1 for ind in indicators if ind.available)
        if active == 0:
            return "UNKNOWN"

        return "LOW_EB_RISK"

    @staticmethod
    def _recommend_action(
        eb_risk_flag: str,
    ) -> str:
        if eb_risk_flag == "LOW_EB_RISK":
            return "planet_hypothesis_supported"
        if eb_risk_flag == "MODERATE_EB_RISK":
            return "manual_eb_review"
        if eb_risk_flag == "HIGH_EB_RISK":
            return "deprioritize_as_possible_eb"
        return "insufficient_data"
