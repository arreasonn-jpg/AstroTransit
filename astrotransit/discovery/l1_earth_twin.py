"""
Kol 1 motoru: L1 bölgesinde Dünya-benzeri, yaşanabilir gezegen adayı skorlama.

Akış
----
1. Yıldız–gezegen parametrelerinden L1 geometrisi hesaplanır
   (`astrotransit.dynamics.assess_l1`).
2. L1 noktasının yıldıza mesafesinden L1 ışınımı (S_earth biriminde)
   türetilir: S_L1 = L_star / d_L1^2.
3. L1 çevresindeki aday cisim için habitability ve Earth similarity skorları
   mevcut motorlarla (`quality.habitability`, `science.earth_similarity`)
   hesaplanır; L1 yarı-büyük ekseni olarak d_L1 kullanılır.
4. Sonuç tek bir "öncelik" skoruna indirgenmez; similarity, habitability ve
   L1 dinamikleri ayrı alanlarda raporlanır.

Epistemik notlar
----------------
- L1 kendi başına yaşanabilir bölge DEĞİLDİR. Ön koşul: ana gezegen HZ'de
  olmalı (`host_in_habitable_zone=True`); aksi halde aday elenir.
- Klasik L1 kararsızdır; doğal bir gezegenin L1'de uzun süre kalması farklı
  bir fiziksel açıklama (örn. rezonans/trojan benzeri) gerektirir. Bu modül
  bu açıklamayı üretmez, yalnızca not düşer.
- Eksik ölçümler None kalır; 0.0 asla "bilinmiyor" yerine yazılmaz.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger

from astrotransit.dynamics.lagrange import AU_M
from astrotransit.dynamics.system import L1System, assess_l1
from astrotransit.quality.habitability import HabitabilityScorer
from astrotransit.science.earth_similarity import score_earth_similarity

_SOLAR_LUM_W = 3.828e26
_SOLAR_FLUX_AT_1AU_W_M2 = _SOLAR_LUM_W / (4.0 * math.pi * (AU_M ** 2))


@dataclass(frozen=True)
class L1EarthTwinCandidate:
    """Kol 1 aday sonucu. Skorlar ayrı alanlardadır; tek bir olasılık yoktur."""

    target_id: str
    host_in_habitable_zone: Optional[bool]
    l1_distance_from_star_au: Optional[float]
    l1_insolation_s_earth: Optional[float]
    habitability_label: str
    habitability_score: Optional[float]
    earth_similarity_score: Optional[float]
    earth_similarity_class: str
    l1_stability_e_folding_days: Optional[float]
    eligible: bool
    rationale: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        def r(v: Optional[float]) -> Optional[float]:
            return None if v is None else round(v, 4)

        return {
            "target_id": self.target_id,
            "host_in_habitable_zone": self.host_in_habitable_zone,
            "l1_distance_from_star_au": r(self.l1_distance_from_star_au),
            "l1_insolation_s_earth": r(self.l1_insolation_s_earth),
            "habitability_label": self.habitability_label,
            "habitability_score": r(self.habitability_score),
            "earth_similarity_score": r(self.earth_similarity_score),
            "earth_similarity_class": self.earth_similarity_class,
            "l1_stability_e_folding_days": r(self.l1_stability_e_folding_days),
            "eligible": self.eligible,
            "rationale": list(self.rationale),
        }


class L1EarthTwinScorer:
    """L1 bölgesi Dünya-benzeri aday skorlayıcısı (Kol 1).

    Başarı kriteri: ana gezegen HZ'de + L1 adayı Dünya'ya yakın kütle/yarıçap
    + L1 ışınımı yaşanabilir aralıkta + uzun dönemli dinamikler not edilmiş.
    """

    def __init__(self, *, min_similarity: float = 90.0):
        if not 0.0 <= min_similarity <= 100.0:
            raise ValueError("min_similarity 0-100 aralığında olmalıdır.")
        self.min_similarity = float(min_similarity)
        self._habitability = HabitabilityScorer()

    def evaluate(
        self,
        target_id: str,
        *,
        m_star_kg: Optional[float] = None,
        m_planet_kg: Optional[float] = None,
        separation_au: Optional[float] = None,
        stellar_luminosity_lsun: Optional[float] = None,
        stellar_teff_k: Optional[float] = None,
        stellar_radius_rsun: Optional[float] = None,
        host_in_habitable_zone: Optional[bool] = None,
        # L1 çevresindeki aday cisim (Kol 1 hedefi)
        candidate_radius_rearth: Optional[float] = None,
        candidate_mass_mearth: Optional[float] = None,
        candidate_equilibrium_temperature_k: Optional[float] = None,
    ) -> L1EarthTwinCandidate:
        rationale: list[str] = []

        system = L1System(
            star_name=target_id,
            m_star_kg=m_star_kg,
            m_planet_kg=m_planet_kg,
            separation_au=separation_au,
            planet_in_habitable_zone=host_in_habitable_zone,
        )
        assessment = assess_l1(system)

        # L1 ışınımı: S_L1 = L / d_L1^2 (L Lsun, d AU → S_earth birimi)
        l1_insolation: Optional[float] = None
        if stellar_luminosity_lsun is not None and assessment.l1_distance_from_star_au is not None:
            d = assessment.l1_distance_from_star_au
            if d > 0.0:
                l1_insolation = float(stellar_luminosity_lsun / (d ** 2))

        # Habitability: L1 yarı-büyük ekseni olarak d_L1 ile
        hab = self._habitability.evaluate(
            planet_radius_rearth=candidate_radius_rearth,
            equilibrium_temperature_k=candidate_equilibrium_temperature_k,
            insolation_flux=l1_insolation,
            semi_major_axis_au=assessment.l1_distance_from_star_au,
            stellar_radius_rsun=stellar_radius_rsun,
            stellar_teff_k=stellar_teff_k,
        )

        # Earth similarity: L1 geometrisi yarı-büyük eksen olarak
        sim = score_earth_similarity(
            "strict_earth_twin",
            planet_radius_rearth=candidate_radius_rearth,
            planet_mass_mearth=candidate_mass_mearth,
            insolation_s_earth=l1_insolation,
            equilibrium_temperature_k=candidate_equilibrium_temperature_k,
            semi_major_axis_au=assessment.l1_distance_from_star_au,
            stellar_teff_k=stellar_teff_k,
        )

        eligible = True
        if host_in_habitable_zone is not True:
            eligible = False
            rationale.append(
                "ön koşul sağlanmadı: ana gezegen HZ'de değil veya HZ durumu bilinmiyor "
                "(L1 kendi başına yaşanabilir bölge değildir)"
            )
        if l1_insolation is None:
            eligible = False
            rationale.append("L1 ışınımı hesaplanamadı (yıldız ışınımı veya L1 mesafesi eksik)")
        elif not 0.25 <= l1_insolation <= 2.0:
            eligible = False
            rationale.append(f"L1 ışınımı yaşanabilir aralık dışı: S={l1_insolation:.3f} S_earth")
        if sim.score_p50 < self.min_similarity:
            eligible = False
            rationale.append(
                f"Earth similarity eşiğin altında: {sim.score_p50:.1f} < {self.min_similarity:.1f}"
            )
        if assessment.stability_e_folding_days is not None:
            rationale.append(
                f"L1 kararsız (e-katlama ~{assessment.stability_e_folding_days:.1f} gün); "
                "doğal gezegen için uzun dönem kalıcılık ek açıklama gerektirir"
            )
        if eligible:
            rationale.append("Kol 1 ön koşulları sağlandı: HZ ana gezegen + yaşanabilir L1 ışınımı + yüksek similarity")

        logger.debug(f"L1 Earth-twin skorlama: {target_id} eligible={eligible}")

        return L1EarthTwinCandidate(
            target_id=target_id,
            host_in_habitable_zone=host_in_habitable_zone,
            l1_distance_from_star_au=assessment.l1_distance_from_star_au,
            l1_insolation_s_earth=l1_insolation,
            habitability_label=hab.summary_label,
            habitability_score=hab.earth_similarity_score if hab.earth_similarity_score is not None else None,
            earth_similarity_score=sim.score_p50,
            earth_similarity_class=sim.classification,
            l1_stability_e_folding_days=assessment.stability_e_folding_days,
            eligible=eligible,
            rationale=tuple(rationale),
        )


__all__ = ["L1EarthTwinCandidate", "L1EarthTwinScorer"]
