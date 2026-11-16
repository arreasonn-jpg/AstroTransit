"""
L1 keşif kolları için hedef havuzu: katalog satırlarından her hedef için
L1 değerlendirmesi üretir ve iki kolu AYRI ayrı puanlar.

- Kol 1 (`L1EarthTwinScorer`): ana gezegen HZ'de + L1 ışınımı yaşanabilir +
  yüksek Earth similarity → `l1_earth_twin_eligible`
- Kol 2 (`L1StructureScorer`): L1 geometrisi + istasyon tutma review skoru +
  makul delta-v bütçesi → `l1_structure_candidate`

İki kol aynı L1 geometrisini paylaşır ama aynı başarı kriterini değil.
Eksik alanlar None/false kalır; 0.0 asla "bilinmiyor" yerine yazılmaz.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from astrotransit.discovery.l1_earth_twin import L1EarthTwinScorer
from astrotransit.discovery.l1_structure import L1StructureScorer
from astrotransit.dynamics.lagrange import M_EARTH_KG, M_JUP_KG, M_SUN_KG


@dataclass
class L1PoolEntry:
    """Tek hedefin L1 havuz kaydı."""

    target_id: str
    l1_assessed: bool = False
    l1_distance_from_planet_au: Optional[float] = None
    l1_stability_e_folding_days: Optional[float] = None
    l1_earth_twin: dict[str, Any] = field(default_factory=dict)
    l1_structure: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        def r(v: Optional[float]) -> Optional[float]:
            return None if v is None else round(v, 6)

        return {
            "target_id": self.target_id,
            "l1_assessed": self.l1_assessed,
            "l1_distance_from_planet_au": r(self.l1_distance_from_planet_au),
            "l1_stability_e_folding_days": r(self.l1_stability_e_folding_days),
            "l1_earth_twin": self.l1_earth_twin,
            "l1_structure": self.l1_structure,
        }


class L1TargetPoolBuilder:
    """Katalog satırlarından L1 hedef havuzu üretir (ağ gerektirmez)."""

    def __init__(
        self,
        *,
        min_similarity: float = 90.0,
        min_review_score: float = 70.0,
    ):
        self.earth_scorer = L1EarthTwinScorer(min_similarity=min_similarity)
        self.structure_scorer = L1StructureScorer(min_review_score=min_review_score)

    def build_from_rows(self, rows: Iterable[Mapping[str, Any]]) -> list[L1PoolEntry]:
        entries: list[L1PoolEntry] = []
        for row in rows:
            entries.append(self.build_from_row(row))
        return entries

    def build_from_row(self, row: Mapping[str, Any]) -> L1PoolEntry:
        raw_id = next(
            (
                row.get(key)
                for key in ("target_id", "tic_id", "TIC", "ID", "id")
                if row.get(key) not in (None, "")
            ),
            "",
        )
        target_id = str(raw_id)

        m_star_kg = self._mass_kg(row, ("m_star_kg", "stellar_mass_kg"))
        if m_star_kg is None:
            mass_msun = self._opt_float(row, ("mass_msun", "stellar_mass_msun", "mass"))
            if mass_msun is not None and mass_msun > 0:
                m_star_kg = mass_msun * M_SUN_KG
        m_planet_kg = self._mass_kg(row, ("m_planet_kg", "planet_mass_kg"))
        if m_planet_kg is None:
            mp_mearth = self._opt_float(row, ("planet_mass_mearth", "m_planet_mearth"))
            if mp_mearth is not None and mp_mearth > 0:
                m_planet_kg = mp_mearth * M_EARTH_KG
            else:
                mp_mjup = self._opt_float(row, ("planet_mass_mjup", "m_planet_mjup"))
                if mp_mjup is not None and mp_mjup > 0:
                    m_planet_kg = mp_mjup * M_JUP_KG
        separation_au = self._opt_float(row, ("separation_au", "semi_major_axis_au", "a_au"))
        luminosity_lsun = self._opt_float(row, ("luminosity_lsun", "luminosity", "L_lsun"))
        teff_k = self._opt_float(row, ("teff_k", "stellar_teff_k"))
        radius_rsun = self._opt_float(row, ("radius_rsun", "stellar_radius_rsun"))
        host_hz_raw = row.get("host_in_habitable_zone", row.get("planet_in_habitable_zone"))
        host_hz = None if host_hz_raw is None else bool(host_hz_raw)

        earth = self.earth_scorer.evaluate(
            target_id,
            m_star_kg=m_star_kg,
            m_planet_kg=m_planet_kg,
            separation_au=separation_au,
            stellar_luminosity_lsun=luminosity_lsun,
            stellar_teff_k=teff_k,
            stellar_radius_rsun=radius_rsun,
            host_in_habitable_zone=host_hz,
            candidate_radius_rearth=self._opt_float(row, ("candidate_radius_rearth", "radius_rearth")),
            candidate_mass_mearth=self._opt_float(row, ("candidate_mass_mearth", "mass_mearth")),
            candidate_equilibrium_temperature_k=self._opt_float(row, ("candidate_equilibrium_temperature_k", "teq_k")),
        )
        structure = self.structure_scorer.evaluate(
            target_id,
            m_star_kg=m_star_kg,
            m_planet_kg=m_planet_kg,
            separation_au=separation_au,
            timing_rms_min=self._opt_float(row, ("timing_rms_min",)),
            transit_symmetry=self._opt_float(row, ("transit_symmetry",)),
            residual_rms_ppm=self._opt_float(row, ("residual_rms_ppm",)),
            pre_post_dip_score=self._opt_float(row, ("pre_post_dip_score",)),
            shoulder_score=self._opt_float(row, ("shoulder_score",)),
            folded_multipeak_score=self._opt_float(row, ("folded_multipeak_score",)),
            trojan_signal_score=self._opt_float(row, ("trojan_signal_score",)),
            n_transits=self._opt_int(row, ("n_transits",)),
        )

        assessed = earth.l1_distance_from_star_au is not None or structure.l1_distance_from_planet_au is not None
        return L1PoolEntry(
            target_id=target_id,
            l1_assessed=assessed,
            l1_distance_from_planet_au=structure.l1_distance_from_planet_au,
            l1_stability_e_folding_days=structure.l1_stability_e_folding_days,
            l1_earth_twin=earth.to_dict(),
            l1_structure=structure.to_dict(),
        )

    def write_json(self, entries: Iterable[L1PoolEntry], path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps([entry.to_dict() for entry in entries], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output

    @staticmethod
    def _opt_float(row: Mapping[str, Any], keys: tuple[str, ...]) -> Optional[float]:
        for key in keys:
            value = row.get(key)
            if value is None or value == "":
                continue
            try:
                result = float(value)
            except (TypeError, ValueError):
                continue
            if result == result and result not in (float("inf"), float("-inf")):
                return result
        return None

    @staticmethod
    def _opt_int(row: Mapping[str, Any], keys: tuple[str, ...]) -> Optional[int]:
        value = L1TargetPoolBuilder._opt_float(row, keys)
        return None if value is None else int(value)

    @staticmethod
    def _mass_kg(row: Mapping[str, Any], keys: tuple[str, ...]) -> Optional[float]:
        value = L1TargetPoolBuilder._opt_float(row, keys)
        return value if value is not None and value > 0 else None


__all__ = ["L1PoolEntry", "L1TargetPoolBuilder"]
