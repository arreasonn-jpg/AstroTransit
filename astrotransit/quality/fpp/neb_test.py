"""
NEB (Nearby Eclipsing Binary) senaryosu için basit FPP/proxy modülü.

Amaç
----
Yakın komşu yıldızlardan kaynaklanabilecek eclipsing binary
senaryosunun riskini operasyonel bir skorla özetlemek.

Kullanılan göstergeler
----------------------
1. Yakın + parlak komşu kombinasyonu
2. Yerel komşu yoğunluğu
3. En yakın komşu uzaklığı

Çıktı
-----
NEBScenarioReport
    p_neb         : 0.0 → 0.95
    neb_risk_flag : LOW_NEB_RISK / MODERATE_NEB_RISK / HIGH_NEB_RISK

Notlar
------
- Bu formal bir olasılık modeli değildir.
- brightest_neighbor_delta_mag:
    hedef - komşu parlaklık farkı gibi düşünülür.
    Küçük değer = komşu daha parlak/benzer parlaklıkta = daha riskli.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from loguru import logger

from astrotransit.quality.vetting import VettingVerdict


_NEIGHBOR_COUNT_WARN = 5
_NEIGHBOR_COUNT_FAIL = 10

_CLOSE_BRIGHT_NEAREST_WARN_ARCSEC = 30.0
_CLOSE_BRIGHT_NEAREST_FAIL_ARCSEC = 20.0

_CLOSE_BRIGHT_DELTA_MAG_WARN = 4.0
_CLOSE_BRIGHT_DELTA_MAG_FAIL = 3.0

_NEAREST_WARN_ARCSEC = 30.0
_NEAREST_FAIL_ARCSEC = 15.0

_MAX_P_NEB = 0.95


@dataclass
class NEBIndicator:
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
class NEBScenarioReport:
    target_id: str
    sector: int
    p_neb: Optional[float] = None
    neb_risk_flag: str = "UNKNOWN"
    recommended_action: str = "none"
    indicators: list[NEBIndicator] = field(default_factory=list)
    n_available: int = 0
    n_warn: int = 0
    n_fail: int = 0
    evidence_flags: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "p_neb": None if self.p_neb is None else round(float(self.p_neb), 4),
            "neb_risk_flag": self.neb_risk_flag,
            "recommended_action": self.recommended_action,
            "n_available": self.n_available,
            "n_warn": self.n_warn,
            "n_fail": self.n_fail,
            "evidence_flags": self.evidence_flags,
            "details": self.details,
            "indicators": [x.to_dict() for x in self.indicators],
        }

    def summary(self) -> str:
        p_neb = "NA" if self.p_neb is None else f"{self.p_neb:.3f}"
        return (
            f"{self.target_id} S{self.sector} | "
            f"p_neb={p_neb} flag={self.neb_risk_flag} | "
            f"available={self.n_available} warn={self.n_warn} fail={self.n_fail} | "
            f"action={self.recommended_action}"
        )


class NEBScenarioEvaluator:
    def __init__(
        self,
        neighbor_count_warn: int = _NEIGHBOR_COUNT_WARN,
        neighbor_count_fail: int = _NEIGHBOR_COUNT_FAIL,
        close_bright_nearest_warn_arcsec: float = _CLOSE_BRIGHT_NEAREST_WARN_ARCSEC,
        close_bright_nearest_fail_arcsec: float = _CLOSE_BRIGHT_NEAREST_FAIL_ARCSEC,
        close_bright_delta_mag_warn: float = _CLOSE_BRIGHT_DELTA_MAG_WARN,
        close_bright_delta_mag_fail: float = _CLOSE_BRIGHT_DELTA_MAG_FAIL,
        nearest_warn_arcsec: float = _NEAREST_WARN_ARCSEC,
        nearest_fail_arcsec: float = _NEAREST_FAIL_ARCSEC,
    ):
        self.neighbor_count_warn = int(neighbor_count_warn)
        self.neighbor_count_fail = int(neighbor_count_fail)
        self.close_bright_nearest_warn_arcsec = close_bright_nearest_warn_arcsec
        self.close_bright_nearest_fail_arcsec = close_bright_nearest_fail_arcsec
        self.close_bright_delta_mag_warn = close_bright_delta_mag_warn
        self.close_bright_delta_mag_fail = close_bright_delta_mag_fail
        self.nearest_warn_arcsec = nearest_warn_arcsec
        self.nearest_fail_arcsec = nearest_fail_arcsec

        logger.debug("NEBScenarioEvaluator başlatıldı.")

    def evaluate(
        self,
        target_id: str,
        sector: int,
        gaia_neighbors_within_60arcsec: Optional[int] = None,
        brightest_neighbor_delta_mag: Optional[float] = None,
        nearest_neighbor_arcsec: Optional[float] = None,
    ) -> NEBScenarioReport:
        logger.info(f"NEB scenario evaluation başlıyor — {target_id} S{sector}")

        neighbor_count = self._to_int_or_none(gaia_neighbors_within_60arcsec)
        delta_mag = self._to_float_or_none(brightest_neighbor_delta_mag)
        nearest_arcsec = self._to_float_or_none(nearest_neighbor_arcsec)

        indicators = [
            self._indicator_close_bright_neighbor(nearest_arcsec, delta_mag),
            self._indicator_neighbor_density(neighbor_count),
            self._indicator_nearest_neighbor_proximity(
                nearest_arcsec,
                delta_mag,
            ),
        ]

        p_neb = self._compute_p_neb(indicators)
        neb_risk_flag = self._compute_flag(indicators, p_neb)
        recommended_action = self._recommend_action(neb_risk_flag)

        n_available = sum(1 for x in indicators if x.available)
        n_warn = sum(1 for x in indicators if x.verdict == VettingVerdict.WARN)
        n_fail = sum(1 for x in indicators if x.verdict == VettingVerdict.FAIL)
        evidence_flags = [x.name for x in indicators if x.verdict == VettingVerdict.FAIL]

        details = {
            "gaia_neighbors_within_60arcsec": neighbor_count,
            "brightest_neighbor_delta_mag": delta_mag,
            "nearest_neighbor_arcsec": nearest_arcsec,
            "is_isolated": bool(
                neighbor_count is not None
                and neighbor_count <= 1
                and nearest_arcsec is not None
                and nearest_arcsec > 40.0
            ),
        }

        report = NEBScenarioReport(
            target_id=target_id,
            sector=int(sector),
            p_neb=None if p_neb is None else float(np.clip(p_neb, 0.0, _MAX_P_NEB)),
            neb_risk_flag=neb_risk_flag,
            recommended_action=recommended_action,
            indicators=indicators,
            n_available=n_available,
            n_warn=n_warn,
            n_fail=n_fail,
            evidence_flags=evidence_flags,
            details=details,
        )

        logger.info(f"NEB scenario evaluation tamamlandı — {report.summary()}")
        return report

    def _indicator_close_bright_neighbor(
        self,
        nearest_neighbor_arcsec: Optional[float],
        brightest_neighbor_delta_mag: Optional[float],
    ) -> NEBIndicator:
        name = "close_bright_neighbor"

        if (
            nearest_neighbor_arcsec is None
            or brightest_neighbor_delta_mag is None
            or nearest_neighbor_arcsec <= 0
        ):
            return NEBIndicator(
                name=name,
                available=False,
                verdict=VettingVerdict.SKIP,
                description="Yakın/parlak komşu girdileri eksik.",
            )

        r = float(nearest_neighbor_arcsec)
        dm = float(brightest_neighbor_delta_mag)

        if r < self.close_bright_nearest_fail_arcsec and dm < self.close_bright_delta_mag_fail:
            verdict = VettingVerdict.FAIL
            contrib = 0.30
            desc = f"Yakın ve parlak komşu: r={r:.2f} arcsec, Δmag={dm:.2f}"
        elif r < self.close_bright_nearest_warn_arcsec and dm < self.close_bright_delta_mag_warn:
            verdict = VettingVerdict.WARN
            contrib = 0.18
            desc = f"Yakın/parlak komşu uyarısı: r={r:.2f} arcsec, Δmag={dm:.2f}"
        elif r < 40.0 and dm < 5.0:
            verdict = VettingVerdict.PASS
            contrib = 0.06
            desc = f"Hafif komşu baskısı: r={r:.2f} arcsec, Δmag={dm:.2f}"
        else:
            verdict = VettingVerdict.PASS
            contrib = 0.0
            desc = f"Yakın parlak komşu göstergesi temiz: r={r:.2f} arcsec, Δmag={dm:.2f}"

        return NEBIndicator(
            name=name,
            available=True,
            verdict=verdict,
            value=r,
            warn_threshold=self.close_bright_nearest_warn_arcsec,
            fail_threshold=self.close_bright_nearest_fail_arcsec,
            score_contribution=contrib,
            description=desc,
        )

    def _indicator_neighbor_density(
        self,
        neighbor_count: Optional[int],
    ) -> NEBIndicator:
        name = "neighbor_density"

        if neighbor_count is None or neighbor_count < 0:
            return NEBIndicator(
                name=name,
                available=False,
                verdict=VettingVerdict.SKIP,
                description="Komşu sayısı girdisi eksik.",
            )

        value = int(neighbor_count)

        if value > self.neighbor_count_fail:
            verdict = VettingVerdict.FAIL
            contrib = 0.25
            desc = f"Alan çok kalabalık: N={value} > {self.neighbor_count_fail}"
        elif value > self.neighbor_count_warn:
            verdict = VettingVerdict.WARN
            contrib = 0.15
            desc = f"Komşu yoğunluğu uyarısı: N={value}"
        elif value > 2:
            verdict = VettingVerdict.PASS
            contrib = 0.05
            desc = f"Orta yoğunlukta alan: N={value}"
        else:
            verdict = VettingVerdict.PASS
            contrib = 0.0
            desc = f"Komşu alanı temiz/seyrek: N={value}"

        return NEBIndicator(
            name=name,
            available=True,
            verdict=verdict,
            value=float(value),
            warn_threshold=float(self.neighbor_count_warn),
            fail_threshold=float(self.neighbor_count_fail),
            score_contribution=contrib,
            description=desc,
        )

    def _indicator_nearest_neighbor_proximity(
        self,
        nearest_neighbor_arcsec: Optional[float],
        brightest_neighbor_delta_mag: Optional[float],
    ) -> NEBIndicator:
        name = "nearest_neighbor_proximity"

        if nearest_neighbor_arcsec is None or nearest_neighbor_arcsec <= 0:
            return NEBIndicator(
                name=name,
                available=False,
                verdict=VettingVerdict.SKIP,
                description="En yakın komşu uzaklığı girdisi eksik.",
            )

        value = float(nearest_neighbor_arcsec)
        dm = brightest_neighbor_delta_mag
        dm = None if dm is None else float(dm)

        if value < self.nearest_fail_arcsec:
            if dm is not None and dm < 3.5:
                verdict = VettingVerdict.FAIL
                contrib = 0.25
                desc = f"En yakın komşu çok yakın ve parlak: {value:.2f} arcsec, Δmag={dm:.2f}"
            elif dm is not None and dm < 5.0:
                verdict = VettingVerdict.WARN
                contrib = 0.10
                desc = f"En yakın komşu çok yakın ama daha sönük: {value:.2f} arcsec, Δmag={dm:.2f}"
            else:
                verdict = VettingVerdict.PASS
                contrib = 0.03
                desc = f"En yakın komşu çok yakın ama belirgin sönük: {value:.2f} arcsec, Δmag={dm}"
        elif value < self.nearest_warn_arcsec:
            if dm is not None and dm < 4.0:
                verdict = VettingVerdict.WARN
                contrib = 0.12
                desc = f"Yakın komşu uyarısı: {value:.2f} arcsec, Δmag={dm:.2f}"
            else:
                verdict = VettingVerdict.PASS
                contrib = 0.04
                desc = f"Yakın ama yeterince sönük komşu: {value:.2f} arcsec, Δmag={dm}"
        elif value < 45.0:
            verdict = VettingVerdict.PASS
            contrib = 0.04
            desc = f"Komşu nispeten yakın ama kritik değil: {value:.2f} arcsec"
        else:
            verdict = VettingVerdict.PASS
            contrib = 0.0
            desc = f"En yakın komşu yeterince uzak: {value:.2f} arcsec"

        return NEBIndicator(
            name=name,
            available=True,
            verdict=verdict,
            value=value,
            warn_threshold=self.nearest_warn_arcsec,
            fail_threshold=self.nearest_fail_arcsec,
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
    def _to_int_or_none(x: Optional[int]) -> Optional[int]:
        if x is None:
            return None
        try:
            x = int(x)
        except Exception:
            return None
        return x

    @staticmethod
    def _compute_p_neb(
        indicators: list[NEBIndicator],
    ) -> Optional[float]:
        active = [ind for ind in indicators if ind.available]
        if not active:
            return None
        total = sum(float(ind.score_contribution) for ind in active)
        return float(np.clip(total, 0.0, _MAX_P_NEB))

    @staticmethod
    def _compute_flag(
        indicators: list[NEBIndicator],
        p_neb: float,
    ) -> str:
        n_fail = sum(1 for ind in indicators if ind.verdict == VettingVerdict.FAIL)
        n_warn = sum(1 for ind in indicators if ind.verdict == VettingVerdict.WARN)

        if n_fail >= 1 or (p_neb is not None and p_neb >= 0.50):
            return "HIGH_NEB_RISK"
        if n_warn >= 1 or (p_neb is not None and p_neb >= 0.20):
            return "MODERATE_NEB_RISK"

        active = sum(1 for ind in indicators if ind.available)
        if active == 0:
            return "UNKNOWN"

        return "LOW_NEB_RISK"

    @staticmethod
    def _recommend_action(
        neb_risk_flag: str,
    ) -> str:
        if neb_risk_flag == "LOW_NEB_RISK":
            return "nearby_eb_not_supported"
        if neb_risk_flag == "MODERATE_NEB_RISK":
            return "inspect_gaia_neighbors"
        if neb_risk_flag == "HIGH_NEB_RISK":
            return "deprioritize_as_possible_nearby_eb"
        return "insufficient_data"
