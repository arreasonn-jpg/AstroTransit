"""
Transit architecture anomaly scoring modülü.

Amaç
----
Klasik tek-gezegen transitinden sapabilecek ilginç mimari işaretleri
tek bir bilimsel-ilginçlik skorunda toplamak.

Örnek sinyaller
---------------
- yüksek TTV / timing anomalisi
- transit asimetrisi
- odd/even veya folded-structure sapmaları
- pre/post transit dip
- shoulder / multi-peak yapı
- trojan / co-orbital benzeri ek işaretler
- kararsız co-orbital / station-keeping review sınıfı

Önemli not
----------
`lagrange_stationkeeping_review_score` veya benzeri alanlar bir
"teknosignature review" follow-up önceliği doğurabilir, fakat bu
doğrudan yapay köken kanıtı değildir. Yalnızca doğal olarak kararsız
bölgelerde kalıcılık benzeri davranışların dikkatle incelenmesi gerektiğini
işaret eder.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from loguru import logger


@dataclass
class ArchitectureAssessment:
    ttv_score: float = 0.0
    asymmetry_score: float = 0.0
    residual_structure_score: float = 0.0
    pre_post_dip_score: float = 0.0
    shoulder_score: float = 0.0
    folded_multipeak_score: float = 0.0
    trojan_signal_score: float = 0.0
    exomoon_signal_score: float = 0.0
    lagrange_stationkeeping_review_score: float = 0.0
    architecture_anomaly_score: float = 0.0
    architecture_flag: str = "NONE"
    summary_label: str = "STANDARD_ARCHITECTURE"

    def to_dict(self) -> dict:
        return {
            "ttv_score": round(float(self.ttv_score), 4),
            "asymmetry_score": round(float(self.asymmetry_score), 4),
            "residual_structure_score": round(float(self.residual_structure_score), 4),
            "pre_post_dip_score": round(float(self.pre_post_dip_score), 4),
            "shoulder_score": round(float(self.shoulder_score), 4),
            "folded_multipeak_score": round(float(self.folded_multipeak_score), 4),
            "trojan_signal_score": round(float(self.trojan_signal_score), 4),
            "exomoon_signal_score": round(float(self.exomoon_signal_score), 4),
            "lagrange_stationkeeping_review_score": round(float(self.lagrange_stationkeeping_review_score), 4),
            "architecture_anomaly_score": round(float(self.architecture_anomaly_score), 4),
            "architecture_flag": self.architecture_flag,
            "summary_label": self.summary_label,
        }


class ArchitectureAnomalyScorer:
    def __init__(self):
        logger.debug("ArchitectureAnomalyScorer başlatıldı.")

    def evaluate(
        self,
        timing_rms_min: Optional[float] = None,
        transit_symmetry: Optional[float] = None,
        ingress_egress_ratio: Optional[float] = None,
        odd_even_mismatch: Optional[float] = None,
        residual_rms_ppm: Optional[float] = None,
        anomaly_flag: Optional[str] = None,
        pre_post_dip_score: Optional[float] = None,
        shoulder_score: Optional[float] = None,
        folded_multipeak_score: Optional[float] = None,
        trojan_signal_score: Optional[float] = None,
        exomoon_signal_score: Optional[float] = None,
        lagrange_stationkeeping_review_score: Optional[float] = None,
        n_transits: Optional[int] = None,
    ) -> ArchitectureAssessment:
        ttv = self._ttv_score(timing_rms_min, n_transits)
        asym = self._asymmetry_score(transit_symmetry, ingress_egress_ratio)
        resid = self._residual_score(residual_rms_ppm, anomaly_flag)

        pp = self._bound0_100(pre_post_dip_score)
        shoulder = self._bound0_100(shoulder_score)
        multi = self._bound0_100(folded_multipeak_score)
        trojan = self._bound0_100(trojan_signal_score)
        exomoon = self._bound0_100(exomoon_signal_score)

        # Eğer kullanıcı dışarıdan doğrudan vermediyse, türet
        if lagrange_stationkeeping_review_score is None:
            lagrange = np.clip(
                0.45 * trojan +
                0.20 * pp +
                0.15 * shoulder +
                0.10 * multi +
                0.10 * ttv,
                0.0,
                100.0,
            )
        else:
            lagrange = self._bound0_100(lagrange_stationkeeping_review_score)

        architecture_score = float(np.clip(
            0.22 * ttv +
            0.16 * asym +
            0.10 * resid +
            0.12 * pp +
            0.10 * shoulder +
            0.10 * multi +
            0.10 * trojan +
            0.10 * exomoon,
            0.0,
            100.0,
        ))

        if lagrange >= 70:
            flag = "UNSTABLE_COORBITAL_REVIEW"
            label = "STATIONKEEPING_REVIEW"
        elif architecture_score >= 70:
            flag = "ARCHITECTURE_ANOMALY"
            label = "EXOTIC_ARCHITECTURE"
        elif architecture_score >= 45:
            flag = "ARCHITECTURE_REVIEW"
            label = "REVIEW_WORTHY_ARCHITECTURE"
        else:
            flag = "NONE"
            label = "STANDARD_ARCHITECTURE"

        return ArchitectureAssessment(
            ttv_score=ttv,
            asymmetry_score=asym,
            residual_structure_score=resid,
            pre_post_dip_score=pp,
            shoulder_score=shoulder,
            folded_multipeak_score=multi,
            trojan_signal_score=trojan,
            exomoon_signal_score=exomoon,
            lagrange_stationkeeping_review_score=float(lagrange),
            architecture_anomaly_score=architecture_score,
            architecture_flag=flag,
            summary_label=label,
        )

    @staticmethod
    def _bound0_100(x: Optional[float]) -> float:
        if x is None:
            return 0.0
        try:
            x = float(x)
        except Exception:
            return 0.0
        if not np.isfinite(x):
            return 0.0
        return float(np.clip(x, 0.0, 100.0))

    @staticmethod
    def _ttv_score(timing_rms_min: Optional[float], n_transits: Optional[int]) -> float:
        if timing_rms_min is None or timing_rms_min <= 0:
            return 0.0

        t = float(timing_rms_min)

        if n_transits is not None and n_transits < 3:
            return 20.0 if t > 10 else 0.0

        if t < 5:
            return 0.0
        if t < 15:
            return 25.0
        if t < 30:
            return 55.0
        if t < 60:
            return 80.0
        return 100.0

    @staticmethod
    def _asymmetry_score(
        transit_symmetry: Optional[float],
        ingress_egress_ratio: Optional[float],
    ) -> float:
        parts = []

        if transit_symmetry is not None and transit_symmetry > 0:
            s = float(transit_symmetry)
            parts.append(float(np.clip((1.0 - s) * 120.0, 0.0, 100.0)))

        if ingress_egress_ratio is not None and ingress_egress_ratio > 0:
            r = float(ingress_egress_ratio)
            dev = abs(np.log(r))
            parts.append(float(np.clip(dev * 90.0, 0.0, 100.0)))

        if not parts:
            return 0.0

        return float(np.mean(parts))

    @staticmethod
    def _residual_score(
        residual_rms_ppm: Optional[float],
        anomaly_flag: Optional[str],
    ) -> float:
        score = 0.0

        if residual_rms_ppm is not None and residual_rms_ppm > 0:
            r = float(residual_rms_ppm)
            if r > 1000:
                score = max(score, 70.0)
            elif r > 500:
                score = max(score, 40.0)
            elif r > 200:
                score = max(score, 20.0)

        if anomaly_flag is not None:
            af = str(anomaly_flag).upper()
            if af == "REJECT":
                score = max(score, 50.0)
            elif af == "REVIEW":
                score = max(score, 25.0)

        return float(np.clip(score, 0.0, 100.0))
