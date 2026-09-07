"""
Habitability / temperate-world scoring modülü.

Amaç
----
Bir transit adayının:
- yaşanabilir bölgeye yakın olup olmadığını
- Dünya-benzerlik yönünden ne kadar ilginç olduğunu
- ılıman (temperate) küçük dünya adayı olup olmadığını

ölçmek.

Not
---
Bu modül yaşanabilirlik "kanıtlamaz".
Sadece follow-up önceliği için bilimsel skor üretir.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from loguru import logger


_SOLAR_TEFF_K = 5772.0
_CONSERVATIVE_HZ_INNER_S = 1.10
_CONSERVATIVE_HZ_OUTER_S = 0.35
_OPTIMISTIC_HZ_INNER_S = 1.78
_OPTIMISTIC_HZ_OUTER_S = 0.25


@dataclass
class HabitabilityAssessment:
    stellar_luminosity_lsun: Optional[float] = None
    insolation_s_earth: Optional[float] = None
    hz_inner_au: Optional[float] = None
    hz_outer_au: Optional[float] = None
    optimistic_hz_inner_au: Optional[float] = None
    optimistic_hz_outer_au: Optional[float] = None
    hz_score: float = 0.0
    temperate_score: float = 0.0
    earth_radius_score: float = 0.0
    earth_similarity_score: float = 0.0
    hz_zone: str = "unknown"
    temperate_flag: bool = False
    earthlike_flag: bool = False
    summary_label: str = "NON_TEMPERATE"

    def to_dict(self) -> dict:
        return {
            "stellar_luminosity_lsun": self.stellar_luminosity_lsun,
            "insolation_s_earth": self.insolation_s_earth,
            "hz_inner_au": self.hz_inner_au,
            "hz_outer_au": self.hz_outer_au,
            "optimistic_hz_inner_au": self.optimistic_hz_inner_au,
            "optimistic_hz_outer_au": self.optimistic_hz_outer_au,
            "hz_score": round(float(self.hz_score), 4),
            "temperate_score": round(float(self.temperate_score), 4),
            "earth_radius_score": round(float(self.earth_radius_score), 4),
            "earth_similarity_score": round(float(self.earth_similarity_score), 4),
            "hz_zone": self.hz_zone,
            "temperate_flag": self.temperate_flag,
            "earthlike_flag": self.earthlike_flag,
            "summary_label": self.summary_label,
        }


class HabitabilityScorer:
    """
    Temperate / Earthlike öncelik skorlayıcısı.
    """

    def __init__(self):
        logger.debug("HabitabilityScorer başlatıldı.")

    def evaluate(
        self,
        planet_radius_rearth: Optional[float] = None,
        equilibrium_temperature_k: Optional[float] = None,
        insolation_flux: Optional[float] = None,
        semi_major_axis_au: Optional[float] = None,
        stellar_radius_rsun: Optional[float] = None,
        stellar_teff_k: Optional[float] = None,
    ) -> HabitabilityAssessment:
        lum = self._estimate_luminosity(
            stellar_radius_rsun=stellar_radius_rsun,
            stellar_teff_k=stellar_teff_k,
        )

        s_earth = self._resolve_insolation(
            insolation_flux=insolation_flux,
            stellar_luminosity_lsun=lum,
            semi_major_axis_au=semi_major_axis_au,
        )

        hz_inner_au = None
        hz_outer_au = None
        opt_inner_au = None
        opt_outer_au = None

        if lum is not None and lum > 0:
            hz_inner_au = float(np.sqrt(lum / _CONSERVATIVE_HZ_INNER_S))
            hz_outer_au = float(np.sqrt(lum / _CONSERVATIVE_HZ_OUTER_S))
            opt_inner_au = float(np.sqrt(lum / _OPTIMISTIC_HZ_INNER_S))
            opt_outer_au = float(np.sqrt(lum / _OPTIMISTIC_HZ_OUTER_S))

        hz_score = self._compute_hz_score(s_earth)
        temperate_score = self._compute_temperate_score(
            equilibrium_temperature_k=equilibrium_temperature_k,
            insolation_s_earth=s_earth,
        )
        earth_radius_score = self._compute_earth_radius_score(planet_radius_rearth)
        earth_similarity_score = (
            0.40 * hz_score +
            0.30 * temperate_score +
            0.30 * earth_radius_score
        )

        hz_zone = self._classify_hz_zone(
            semi_major_axis_au=semi_major_axis_au,
            hz_inner_au=hz_inner_au,
            hz_outer_au=hz_outer_au,
            opt_inner_au=opt_inner_au,
            opt_outer_au=opt_outer_au,
            insolation_s_earth=s_earth,
        )

        temperate_flag = (
            (s_earth is not None and 0.25 <= s_earth <= 2.0)
            or (equilibrium_temperature_k is not None and 180.0 <= equilibrium_temperature_k <= 330.0)
        )

        earthlike_flag = (
            planet_radius_rearth is not None
            and 0.8 <= planet_radius_rearth <= 1.4
            and temperate_flag
        )

        if earthlike_flag and earth_similarity_score >= 70:
            summary_label = "EARTHLIKE_TEMPERATE"
        elif temperate_flag and planet_radius_rearth is not None and planet_radius_rearth <= 1.8:
            summary_label = "TEMPERATE_SMALL_WORLD"
        elif temperate_flag:
            summary_label = "TEMPERATE_NONTERRESTRIAL"
        else:
            summary_label = "NON_TEMPERATE"

        return HabitabilityAssessment(
            stellar_luminosity_lsun=lum,
            insolation_s_earth=s_earth,
            hz_inner_au=hz_inner_au,
            hz_outer_au=hz_outer_au,
            optimistic_hz_inner_au=opt_inner_au,
            optimistic_hz_outer_au=opt_outer_au,
            hz_score=hz_score,
            temperate_score=temperate_score,
            earth_radius_score=earth_radius_score,
            earth_similarity_score=earth_similarity_score,
            hz_zone=hz_zone,
            temperate_flag=temperate_flag,
            earthlike_flag=earthlike_flag,
            summary_label=summary_label,
        )

    @staticmethod
    def _estimate_luminosity(
        stellar_radius_rsun: Optional[float],
        stellar_teff_k: Optional[float],
    ) -> Optional[float]:
        if (
            stellar_radius_rsun is None or stellar_teff_k is None
            or stellar_radius_rsun <= 0 or stellar_teff_k <= 0
        ):
            return None

        return float((stellar_radius_rsun ** 2) * ((stellar_teff_k / _SOLAR_TEFF_K) ** 4))

    @staticmethod
    def _resolve_insolation(
        insolation_flux: Optional[float],
        stellar_luminosity_lsun: Optional[float],
        semi_major_axis_au: Optional[float],
    ) -> Optional[float]:
        if insolation_flux is not None and insolation_flux > 0:
            return float(insolation_flux)

        if (
            stellar_luminosity_lsun is not None and stellar_luminosity_lsun > 0
            and semi_major_axis_au is not None and semi_major_axis_au > 0
        ):
            return float(stellar_luminosity_lsun / (semi_major_axis_au ** 2))

        return None

    @staticmethod
    def _compute_hz_score(insolation_s_earth: Optional[float]) -> float:
        if insolation_s_earth is None or insolation_s_earth <= 0:
            return 0.0

        x = np.log10(insolation_s_earth)
        # 1 S_earth civarı en iyi
        score = 100.0 * np.exp(-0.5 * (x / 0.28) ** 2)
        return float(np.clip(score, 0.0, 100.0))

    @staticmethod
    def _compute_temperate_score(
        equilibrium_temperature_k: Optional[float],
        insolation_s_earth: Optional[float],
    ) -> float:
        scores = []

        if equilibrium_temperature_k is not None and equilibrium_temperature_k > 0:
            # 255–290 K aralığı çevresi en yüksek, 180–330 K geniş kabul
            center = 272.0
            width = 45.0
            s = 100.0 * np.exp(-0.5 * ((equilibrium_temperature_k - center) / width) ** 2)
            scores.append(float(np.clip(s, 0.0, 100.0)))

        if insolation_s_earth is not None and insolation_s_earth > 0:
            x = np.log10(insolation_s_earth)
            s = 100.0 * np.exp(-0.5 * (x / 0.33) ** 2)
            scores.append(float(np.clip(s, 0.0, 100.0)))

        if not scores:
            return 0.0

        return float(np.mean(scores))

    @staticmethod
    def _compute_earth_radius_score(planet_radius_rearth: Optional[float]) -> float:
        if planet_radius_rearth is None or planet_radius_rearth <= 0:
            return 0.0

        r = float(planet_radius_rearth)

        # 1 R_earth merkezli Gaussian benzeri skor
        score = 100.0 * np.exp(-0.5 * ((r - 1.0) / 0.35) ** 2)

        # 2.2 R_earth üstünde Dünya-benzerlik hızla düşsün
        if r > 2.2:
            score *= 0.35

        return float(np.clip(score, 0.0, 100.0))

    @staticmethod
    def _classify_hz_zone(
        semi_major_axis_au: Optional[float],
        hz_inner_au: Optional[float],
        hz_outer_au: Optional[float],
        opt_inner_au: Optional[float],
        opt_outer_au: Optional[float],
        insolation_s_earth: Optional[float],
    ) -> str:
        if (
            semi_major_axis_au is not None
            and hz_inner_au is not None and hz_outer_au is not None
        ):
            a = float(semi_major_axis_au)
            if hz_inner_au <= a <= hz_outer_au:
                return "conservative_hz"
            if opt_inner_au is not None and opt_outer_au is not None and opt_inner_au <= a <= opt_outer_au:
                return "optimistic_hz"
            if a < opt_inner_au:
                return "too_hot"
            if a > opt_outer_au:
                return "too_cold"

        if insolation_s_earth is not None and insolation_s_earth > 0:
            if _CONSERVATIVE_HZ_OUTER_S <= insolation_s_earth <= _CONSERVATIVE_HZ_INNER_S:
                return "conservative_hz"
            if _OPTIMISTIC_HZ_OUTER_S <= insolation_s_earth <= _OPTIMISTIC_HZ_INNER_S:
                return "optimistic_hz"
            if insolation_s_earth > _OPTIMISTIC_HZ_INNER_S:
                return "too_hot"
            if insolation_s_earth < _OPTIMISTIC_HZ_OUTER_S:
                return "too_cold"

        return "unknown"
