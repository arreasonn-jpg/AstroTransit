"""
Kol 2 motoru: L1 noktasında kontrollü uydu / mega yapı adayı analizi.

Akış
----
1. Yıldız–gezegen L1 geometrisi ve kararsızlık ölçeği hesaplanır
   (`astrotransit.dynamics.assess_l1`).
2. Gözlemsel işaretler (istasyon tutma benzeri davranışlar) girilirse
   `ArchitectureAnomalyScorer`'un `lagrange_stationkeeping_review_score`
   alanı ile birleştirilir.
3. Gerekli istasyon tutma delta-v bütçesi (`station_keeping_budget`)
   hesaplanır; bu, yapının L1'de kalabilmesi için gereken aktif kontrol
   maliyetinin model tahminidir.

Epistemik notlar
----------------
- Ana gezegenin büyüklüğü önemli değildir (Mars'tan Jüpiter'e kadar).
- "L1 yakınında görüldü" KONTROL KANITI DEĞİLDİR. Kontrol iddiası ancak
  istasyon tutma davranışının gözlemsel kanıtı + makul delta-v bütçesi ile
  desteklenir; bu modül bu kanıtı üretmez, yalnızca çerçeve ve öncelik üretir.
- Delta-v bütçesi model bir tahmindir; gerçek yörünge düzeltmeleri
  sayısal yörünge belirleme (orbit determination) gerektirir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger

from astrotransit.dynamics.system import L1System, assess_l1
from astrotransit.quality.architecture_anomalies import ArchitectureAnomalyScorer


@dataclass(frozen=True)
class L1StructureCandidate:
    """Kol 2 aday sonucu."""

    target_id: str
    l1_distance_from_planet_au: Optional[float]
    l1_stability_e_folding_days: Optional[float]
    station_keeping_total_delta_v_m_per_s: Optional[float]
    stationkeeping_review_score: Optional[float]
    review_flag: str
    controllable_candidate: bool
    rationale: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        def r(v: Optional[float]) -> Optional[float]:
            return None if v is None else round(v, 4)

        return {
            "target_id": self.target_id,
            "l1_distance_from_planet_au": r(self.l1_distance_from_planet_au),
            "l1_stability_e_folding_days": r(self.l1_stability_e_folding_days),
            "station_keeping_total_delta_v_m_per_s": r(self.station_keeping_total_delta_v_m_per_s),
            "stationkeeping_review_score": r(self.stationkeeping_review_score),
            "review_flag": self.review_flag,
            "controllable_candidate": self.controllable_candidate,
            "rationale": list(self.rationale),
        }


class L1StructureScorer:
    """L1'de kontrollü yapı adayı skorlayıcısı (Kol 2).

    Başarı kriteri: L1'de gözlemsel istasyon-tutma işaretleri (review skoru
    yüksek) + hesaplanan delta-v bütçesinin fiziksel olarak makul olması.
    Yalnızca "L1'de görüldü" asla yeterli değildir.
    """

    def __init__(
        self,
        *,
        min_review_score: float = 70.0,
        max_budget_delta_v_m_per_s: float = 100.0,
        correction_interval_days: float = 30.0,
        station_keeping_amplitude: float = 1e-4,
        mission_days: float = 365.25,
    ):
        if not 0.0 <= min_review_score <= 100.0:
            raise ValueError("min_review_score 0-100 aralığında olmalıdır.")
        if max_budget_delta_v_m_per_s <= 0.0:
            raise ValueError("max_budget_delta_v_m_per_s pozitif olmalıdır.")
        self.min_review_score = float(min_review_score)
        self.max_budget_delta_v_m_per_s = float(max_budget_delta_v_m_per_s)
        self.correction_interval_days = float(correction_interval_days)
        self.station_keeping_amplitude = float(station_keeping_amplitude)
        self.mission_days = float(mission_days)
        self._architecture = ArchitectureAnomalyScorer()

    def evaluate(
        self,
        target_id: str,
        *,
        m_star_kg: Optional[float] = None,
        m_planet_kg: Optional[float] = None,
        separation_au: Optional[float] = None,
        # Gözlemsel işaretler (opsiyonel; None = ölçülmemiş)
        timing_rms_min: Optional[float] = None,
        transit_symmetry: Optional[float] = None,
        residual_rms_ppm: Optional[float] = None,
        pre_post_dip_score: Optional[float] = None,
        shoulder_score: Optional[float] = None,
        folded_multipeak_score: Optional[float] = None,
        trojan_signal_score: Optional[float] = None,
        n_transits: Optional[int] = None,
    ) -> L1StructureCandidate:
        rationale: list[str] = []

        system = L1System(
            star_name=target_id,
            m_star_kg=m_star_kg,
            m_planet_kg=m_planet_kg,
            separation_au=separation_au,
        )
        assessment = assess_l1(
            system,
            correction_interval_days=self.correction_interval_days,
            station_keeping_amplitude=self.station_keeping_amplitude,
            mission_days=self.mission_days,
        )

        arch = self._architecture.evaluate(
            timing_rms_min=timing_rms_min,
            transit_symmetry=transit_symmetry,
            residual_rms_ppm=residual_rms_ppm,
            pre_post_dip_score=pre_post_dip_score,
            shoulder_score=shoulder_score,
            folded_multipeak_score=folded_multipeak_score,
            trojan_signal_score=trojan_signal_score,
            n_transits=n_transits,
        )
        review_score = arch.lagrange_stationkeeping_review_score

        budget_dv: Optional[float] = None
        if assessment.station_keeping is not None:
            budget_dv = assessment.station_keeping.get("total_delta_v_m_per_s")

        controllable = True
        if assessment.l1_distance_from_planet_au is None:
            controllable = False
            rationale.append("L1 geometrisi hesaplanamadı (kütle/mesafe eksik)")
        if review_score < self.min_review_score:
            controllable = False
            rationale.append(
                f"istasyon tutma işareti yetersiz: review={review_score:.1f} < {self.min_review_score:.1f} "
                "('L1'de görüldü' kontrol kanıtı değildir)"
            )
        if budget_dv is None:
            controllable = False
            rationale.append("delta-v bütçesi hesaplanamadı")
        elif budget_dv > self.max_budget_delta_v_m_per_s:
            controllable = False
            rationale.append(
                f"gerekli istasyon tutma bütçesi makul üst sınırın üzerinde: {budget_dv:.2f} > {self.max_budget_delta_v_m_per_s:.2f} m/s/yıl"
            )
        if assessment.stability_e_folding_days is not None:
            rationale.append(
                f"L1 kararsız (e-katlama ~{assessment.stability_e_folding_days:.1f} gün); "
                "kalıcılık ancak aktif kontrol ile mümkündür"
            )
        if controllable:
            rationale.append(
                "Kol 2 çerçevesi: istasyon tutma işareti + makul delta-v bütçesi; "
                "bu henüz kontrol kanıtı değil, follow-up önceliğidir"
            )

        logger.debug(f"L1 yapı skorlama: {target_id} controllable={controllable}")

        return L1StructureCandidate(
            target_id=target_id,
            l1_distance_from_planet_au=assessment.l1_distance_from_planet_au,
            l1_stability_e_folding_days=assessment.stability_e_folding_days,
            station_keeping_total_delta_v_m_per_s=budget_dv,
            stationkeeping_review_score=review_score,
            review_flag=arch.architecture_flag,
            controllable_candidate=controllable,
            rationale=tuple(rationale),
        )


__all__ = ["L1StructureCandidate", "L1StructureScorer"]
