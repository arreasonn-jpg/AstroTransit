"""
Potential habitable-moon host scoring modülü.

Amaç
----
Dev / büyük gezegenlerin:
- yaşanabilir bölge civarında olup olmadığını
- büyük ve kararlı uydu taşıma potansiyelini
- Hill sphere bazlı moon-host ilgisini

ölçmek.

Not
---
Bu modül "uydu bulundu" demez.
Sadece "uydu taşıma potansiyeli yüksek" follow-up önceliği verir.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from loguru import logger


_MSTAR_TO_MEARTH = 332946.0
_REARTH_TO_AU = 4.26352e-5


@dataclass
class MoonHostAssessment:
    estimated_planet_mass_mearth: Optional[float] = None
    hill_radius_au: Optional[float] = None
    stable_prograde_zone_au: Optional[float] = None
    stable_prograde_zone_planet_radii: Optional[float] = None
    giant_host_score: float = 0.0
    temperate_host_score: float = 0.0
    hill_stability_score: float = 0.0
    moon_host_score: float = 0.0
    moon_host_flag: bool = False
    summary_label: str = "STANDARD_PLANET"

    def to_dict(self) -> dict:
        return {
            "estimated_planet_mass_mearth": self.estimated_planet_mass_mearth,
            "hill_radius_au": self.hill_radius_au,
            "stable_prograde_zone_au": self.stable_prograde_zone_au,
            "stable_prograde_zone_planet_radii": self.stable_prograde_zone_planet_radii,
            "giant_host_score": round(float(self.giant_host_score), 4),
            "temperate_host_score": round(float(self.temperate_host_score), 4),
            "hill_stability_score": round(float(self.hill_stability_score), 4),
            "moon_host_score": round(float(self.moon_host_score), 4),
            "moon_host_flag": self.moon_host_flag,
            "summary_label": self.summary_label,
        }


class MoonHostScorer:
    def __init__(self):
        logger.debug("MoonHostScorer başlatıldı.")

    def evaluate(
        self,
        planet_radius_rearth: Optional[float] = None,
        stellar_mass_msun: Optional[float] = None,
        semi_major_axis_au: Optional[float] = None,
        equilibrium_temperature_k: Optional[float] = None,
        insolation_flux: Optional[float] = None,
        crowding_ratio: Optional[float] = None,
    ) -> MoonHostAssessment:
        mp = self._estimate_planet_mass_mearth(planet_radius_rearth)

        hill_radius_au = None
        stable_zone_au = None
        stable_zone_rp = None

        if (
            mp is not None and mp > 0
            and stellar_mass_msun is not None and stellar_mass_msun > 0
            and semi_major_axis_au is not None and semi_major_axis_au > 0
        ):
            mstar_mearth = float(stellar_mass_msun) * _MSTAR_TO_MEARTH
            hill_radius_au = float(semi_major_axis_au * ((mp / (3.0 * mstar_mearth)) ** (1.0 / 3.0)))
            stable_zone_au = float(0.49 * hill_radius_au)

            if planet_radius_rearth is not None and planet_radius_rearth > 0:
                rp_au = float(planet_radius_rearth) * _REARTH_TO_AU
                if rp_au > 0:
                    stable_zone_rp = float(stable_zone_au / rp_au)

        giant_host_score = self._compute_giant_host_score(planet_radius_rearth)
        temperate_host_score = self._compute_temperate_host_score(
            equilibrium_temperature_k=equilibrium_temperature_k,
            insolation_flux=insolation_flux,
        )
        hill_stability_score = self._compute_hill_stability_score(stable_zone_rp)
        cleanliness_bonus = self._compute_cleanliness_bonus(crowding_ratio)

        moon_host_score = (
            0.40 * giant_host_score +
            0.30 * temperate_host_score +
            0.25 * hill_stability_score +
            0.05 * cleanliness_bonus
        )

        moon_host_flag = (
            moon_host_score >= 65.0
            and giant_host_score >= 50.0
            and hill_stability_score >= 40.0
        )

        if moon_host_flag and temperate_host_score >= 60:
            summary_label = "POTENTIAL_HABITABLE_MOON_HOST"
        elif moon_host_flag:
            summary_label = "POTENTIAL_MOON_HOST"
        elif giant_host_score >= 50:
            summary_label = "GIANT_WORLD"
        else:
            summary_label = "STANDARD_PLANET"

        return MoonHostAssessment(
            estimated_planet_mass_mearth=mp,
            hill_radius_au=hill_radius_au,
            stable_prograde_zone_au=stable_zone_au,
            stable_prograde_zone_planet_radii=stable_zone_rp,
            giant_host_score=giant_host_score,
            temperate_host_score=temperate_host_score,
            hill_stability_score=hill_stability_score,
            moon_host_score=moon_host_score,
            moon_host_flag=moon_host_flag,
            summary_label=summary_label,
        )

    @staticmethod
    def _estimate_planet_mass_mearth(planet_radius_rearth: Optional[float]) -> Optional[float]:
        if planet_radius_rearth is None or planet_radius_rearth <= 0:
            return None

        r = float(planet_radius_rearth)

        if r < 1.5:
            m = r ** 3.7
        elif r < 4.0:
            m = 2.7 * (r ** 1.3)
        elif r < 10.0:
            m = 17.0 * (r / 3.88) ** 1.0
        else:
            m = 95.0 * (r / 11.2) ** 1.0

        return float(np.clip(m, 0.1, 1000.0))

    @staticmethod
    def _compute_giant_host_score(planet_radius_rearth: Optional[float]) -> float:
        if planet_radius_rearth is None or planet_radius_rearth <= 0:
            return 0.0

        r = float(planet_radius_rearth)

        if r < 2.5:
            return 0.0
        if r < 3.5:
            return 35.0
        if r < 6.0:
            return 70.0
        if r < 12.0:
            return 100.0
        return 85.0

    @staticmethod
    def _compute_temperate_host_score(
        equilibrium_temperature_k: Optional[float],
        insolation_flux: Optional[float],
    ) -> float:
        scores = []

        if equilibrium_temperature_k is not None and equilibrium_temperature_k > 0:
            center = 260.0
            width = 55.0
            scores.append(float(100.0 * np.exp(-0.5 * ((equilibrium_temperature_k - center) / width) ** 2)))

        if insolation_flux is not None and insolation_flux > 0:
            x = np.log10(insolation_flux)
            scores.append(float(100.0 * np.exp(-0.5 * (x / 0.35) ** 2)))

        if not scores:
            return 0.0

        return float(np.clip(np.mean(scores), 0.0, 100.0))

    @staticmethod
    def _compute_hill_stability_score(stable_zone_rp: Optional[float]) -> float:
        if stable_zone_rp is None or stable_zone_rp <= 0:
            return 0.0

        z = float(stable_zone_rp)

        if z < 10:
            return 5.0
        if z < 20:
            return 20.0
        if z < 40:
            return 45.0
        if z < 80:
            return 75.0
        return 100.0

    @staticmethod
    def _compute_cleanliness_bonus(crowding_ratio: Optional[float]) -> float:
        if crowding_ratio is None or crowding_ratio <= 0:
            return 0.0

        c = float(crowding_ratio)
        if c < 0.80:
            return 0.0
        if c < 0.90:
            return 35.0
        if c < 0.97:
            return 70.0
        return 100.0
