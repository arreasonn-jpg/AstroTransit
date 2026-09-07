"""
EB vs Co-orbital Discriminator

Amaç: Faz uzayında off-primary sinyal tespit edilen sistemlerin
      eclipsing binary mi yoksa co-orbital/trojan yapı mı
      olduğunu sistematik kriterlerle ayırt etmek.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
from loguru import logger

@dataclass
class DiscriminatorInput:
    target_id: str
    sector: int
    primary_depth_ppm: float
    primary_sig: float
    secondary_depth_ppm: float
    secondary_sig: float
    l4_depth_ppm: float
    l4_sig: float
    l5_depth_ppm: float
    l5_sig: float
    odd_even_mismatch: float = 0.0
    l5_repeatability: str = "UNKNOWN"
    l4_repeatability: str = "UNKNOWN"
    dur_phase: float = 0.0  # Yeni eklenen field

@dataclass
class DiscriminatorResult:
    target_id: str
    sector: int
    eb_score: float = 0.0
    coorbital_score: float = 0.0
    verdict: str = "INCONCLUSIVE"
    confidence: str = "LOW"
    triggered_rules: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "eb_score": round(self.eb_score, 2),
            "coorbital_score": round(self.coorbital_score, 2),
            "verdict": self.verdict,
            "confidence": self.confidence,
            "triggered_rules": self.triggered_rules,
            "notes": self.notes,
        }

    def summary(self) -> str:
        return (
            f"{self.target_id} S{self.sector} | "
            f"EB={self.eb_score:.1f} CO={self.coorbital_score:.1f} | "
            f"verdict={self.verdict} conf={self.confidence}"
        )

class EBCooorbitalDiscriminator:
    _SHORT_PERIOD_THRESHOLD = 0.08

    def discriminate(self, inp: DiscriminatorInput) -> DiscriminatorResult:
        logger.debug(f"Discriminating: {inp.target_id} S{inp.sector}")

        eb_score = 0.0
        co_score = 0.0
        rules: list[str] = []
        notes: list[str] = []

        prim = abs(inp.primary_depth_ppm)
        sec = abs(inp.secondary_depth_ppm)
        sec_sig = inp.secondary_sig
        l4_sig = inp.l4_sig
        l5_sig = inp.l5_sig
        l4_depth = inp.l4_depth_ppm
        l5_depth = inp.l5_depth_ppm

        # Guard: Kısa periyot kontrolü
        short_period_mode = inp.dur_phase > self._SHORT_PERIOD_THRESHOLD
        if short_period_mode:
            notes.append(f"Short-period mode active (dur_phase={inp.dur_phase:.3f} > {self._SHORT_PERIOD_THRESHOLD}): L4/L5 windows overlap with transit zone; co-orbital scoring suppressed.")

        # ── EB Kriterleri ──
        if prim > 0 and sec / prim > 0.40:
            eb_score += 40.0
            rules.append(f"EB_R1: sec/prim={sec/prim:.2f} > 0.40")
        elif prim > 0 and sec / prim > 0.20:
            eb_score += 20.0
            rules.append(f"EB_R1_MILD: sec/prim={sec/prim:.2f}")

        if sec_sig < -2.0:
            eb_score += 20.0
            rules.append(f"EB_R2: secondary_sig={sec_sig:.1f} (flux increase)")
            notes.append("Negative secondary may indicate ellipsoidal modulation or reflection")

        if inp.odd_even_mismatch > 3.0:
            eb_score += 25.0
            rules.append(f"EB_R3: odd_even={inp.odd_even_mismatch:.1f} > 3.0")
        elif inp.odd_even_mismatch > 1.5:
            eb_score += 12.0
            rules.append(f"EB_R3_MILD: odd_even={inp.odd_even_mismatch:.1f}")

        if l4_depth * l5_depth < 0 and abs(l4_sig) > 2.0 and abs(l5_sig) > 2.0:
            eb_score += 15.0
            rules.append("EB_R4: L4/L5 opposite signs → likely modulation artifact")

        if abs(sec_sig) > 6.0:
            eb_score += 15.0
            rules.append(f"EB_R5: |sec_sig|={abs(sec_sig):.1f} very strong")

        # ── Co-orbital Kriterleri ──
        if not short_period_mode:
            if inp.l5_repeatability == "REPEATABLE ★":
                co_score += 40.0
                rules.append("CO_R6: L5 REPEATABLE across LC halves")
            elif inp.l5_repeatability == "PARTIALLY REPEATABLE":
                co_score += 20.0
                rules.append("CO_R6_PARTIAL: L5 partially repeatable")
            elif inp.l5_repeatability in {"FIRST HALF ONLY", "SECOND HALF ONLY"}:
                co_score -= 20.0
                rules.append(f"CO_R6_NEG: L5 {inp.l5_repeatability} → not co-orbital")

            if prim > 0 and 0 < l5_depth < prim * 0.35:
                co_score += 15.0
                rules.append(f"CO_R7: L5/primary ratio={l5_depth/prim:.2f}")

            if abs(sec_sig) < 3.0:
                co_score += 20.0
                rules.append("CO_R8: Weak secondary → EB less likely")

            if l5_sig > 5.0 and l5_depth > 0:
                co_score += 15.0
                rules.append(f"CO_R9: L5 positive deep: {l5_depth:.0f} ppm / {l5_sig:.1f}σ")

            if inp.odd_even_mismatch < 1.0:
                co_score += 10.0
                rules.append("CO_R10: Low odd-even → not EB-like")
        else:
            rules.append("CO_R6-10_SKIP: Short-period mode — co-orbital rules suppressed")

        eb_score = float(np.clip(eb_score, 0.0, 100.0))
        co_score = float(np.clip(co_score, 0.0, 100.0))
        diff = co_score - eb_score

        if eb_score >= 60 and co_score < 40:
            verdict = "LIKELY_EB"
        elif eb_score >= 40 and co_score < 30:
            verdict = "POSSIBLE_EB"
        elif co_score >= 60 and eb_score < 40:
            verdict = "POSSIBLE_COORBITAL"
        elif co_score >= 40 and eb_score < 30:
            verdict = "WEAK_COORBITAL_HINT"
        elif eb_score >= 40 and co_score >= 40:
            verdict = "AMBIGUOUS"
        else:
            verdict = "INCONCLUSIVE"

        max_score = max(eb_score, co_score)
        gap = abs(diff)
        if max_score >= 60 and gap >= 30:
            confidence = "HIGH"
        elif max_score >= 40 and gap >= 15:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        if short_period_mode and verdict == "AMBIGUOUS":
            verdict = "INCONCLUSIVE"

        return DiscriminatorResult(
            target_id=inp.target_id,
            sector=inp.sector,
            eb_score=eb_score,
            coorbital_score=co_score,
            verdict=verdict,
            confidence=confidence,
            triggered_rules=rules,
            notes=notes,
        )
