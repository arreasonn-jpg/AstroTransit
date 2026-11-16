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
    l1_distance_from_star_au: Optional[float] = None
    l1_stability_e_folding_days: Optional[float] = None
    l1_earth_twin: dict[str, Any] = field(default_factory=dict)
    l1_structure: dict[str, Any] = field(default_factory=dict)
    l1_claim_label: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        def r(v: Optional[float]) -> Optional[float]:
            return None if v is None else round(v, 6)

        return {
            "target_id": self.target_id,
            "l1_assessed": self.l1_assessed,
            "l1_distance_from_planet_au": r(self.l1_distance_from_planet_au),
            "l1_distance_from_star_au": r(self.l1_distance_from_star_au),
            "l1_stability_e_folding_days": r(self.l1_stability_e_folding_days),
            "l1_earth_twin": self.l1_earth_twin,
            "l1_structure": self.l1_structure,
            "l1_claim_label": self.l1_claim_label,
        }


class L1TargetPoolBuilder:
    """Katalog satırlarından L1 hedef havuzu üretir (ağ gerektirmez).

    ``query_mast=True`` ile eksik yıldız parametreleri (mass/lum/teff/rad)
    MAST TIC kataloğundan tek tek tamamlanır; ağ hatasında satır olduğu gibi
    kalır (hedef ``l1_assessed=False`` olur, asla 0.0 yazılmaz).
    """

    def __init__(
        self,
        *,
        min_similarity: float = 90.0,
        min_review_score: float = 70.0,
        mast_client: Any = None,
    ):
        self.earth_scorer = L1EarthTwinScorer(min_similarity=min_similarity)
        self.structure_scorer = L1StructureScorer(min_review_score=min_review_score)
        self._mast_client = mast_client

    def build_from_rows(
        self,
        rows: Iterable[Mapping[str, Any]],
        *,
        query_mast: bool = False,
    ) -> list[L1PoolEntry]:
        entries: list[L1PoolEntry] = []
        for row in rows:
            entries.append(self.build_from_row(row, query_mast=query_mast))
        return entries

    def build_from_row(self, row: Mapping[str, Any], *, query_mast: bool = False) -> L1PoolEntry:
        row = dict(row)
        if query_mast:
            row = self._enrich_from_mast(row)
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
        claim_label: Optional[str] = None
        if assessed:
            from astrotransit.validation.l1_claims import infer_l1_claim

            claim_label = infer_l1_claim(
                {
                    "l1_assessed": True,
                    "l1_stationkeeping_review_score": structure.stationkeeping_review_score,
                    "station_keeping_budget_ok": (
                        structure.station_keeping_total_delta_v_m_per_s is not None
                        and structure.station_keeping_total_delta_v_m_per_s <= 100.0
                    ),
                    "host_in_habitable_zone": earth.host_in_habitable_zone,
                    "l1_insolation_in_habitable_range": earth.eligible,
                    "earth_similarity_score": earth.earth_similarity_score,
                    "l1_min_similarity": self.earth_scorer.min_similarity,
                }
            ).value
        return L1PoolEntry(
            target_id=target_id,
            l1_assessed=assessed,
            l1_distance_from_planet_au=structure.l1_distance_from_planet_au,
            l1_distance_from_star_au=earth.l1_distance_from_star_au,
            l1_stability_e_folding_days=structure.l1_stability_e_folding_days,
            l1_earth_twin=earth.to_dict(),
            l1_structure=structure.to_dict(),
            l1_claim_label=claim_label,
        )

    def write_json(self, entries: Iterable[L1PoolEntry], path: str | Path, *, branch: str = "both") -> Path:
        from astrotransit.outputs.l1_pool import write_l1_pool_json

        return write_l1_pool_json(entries, path, branch=branch)

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

    def _enrich_from_mast(self, row: Mapping[str, Any]) -> dict[str, Any]:
        """Eksik yıldız alanlarını MAST TIC kataloğundan doldurur.

        Ağ/bağımlılık hatasında orijinal satırı döndürür; None alanlar None kalır.
        """
        if self._mast_client is None:
            from astrotransit.data.mast_client import MASTClient

            self._mast_client = MASTClient()
        raw_id = next(
            (
                row.get(key)
                for key in ("target_id", "tic_id", "TIC", "ID", "id")
                if row.get(key) not in (None, "")
            ),
            None,
        )
        if raw_id is None:
            return row
        try:
            tic_id = int(str(raw_id).split()[-1])
        except (ValueError, IndexError):
            return row
        try:
            catalog = self._mast_client.query_tic_catalog(tic_id=tic_id)
        except Exception as exc:  # ağ/bağımlılık hatası: satır olduğu gibi kalır
            from loguru import logger

            logger.warning(f"MAST sorgusu başarısız ({raw_id}): {exc}")
            return row
        if catalog is None or len(catalog) == 0:
            return row
        first = catalog[0]
        names = getattr(first, "colnames", None)
        record = {name: first[name] for name in names} if names else dict(first)

        def pick(*keys: str) -> Any:
            for key in keys:
                if key in record and record[key] not in (None, "", 0, 0.0):
                    return record[key]
            return None

        enriched = dict(row)
        if self._opt_float(enriched, ("mass_msun", "stellar_mass_msun", "mass", "m_star_kg", "stellar_mass_kg")) is None:
            mass = pick("mass", "Mass")
            if mass is not None:
                enriched["mass_msun"] = float(mass)
        if self._opt_float(enriched, ("luminosity_lsun", "luminosity", "L_lsun")) is None:
            lum = pick("lum", "luminosity", "Lum")
            if lum is not None:
                enriched["luminosity_lsun"] = float(lum)
        if self._opt_float(enriched, ("teff_k", "stellar_teff_k")) is None:
            teff = pick("Teff", "teff")
            if teff is not None:
                enriched["teff_k"] = float(teff)
        if self._opt_float(enriched, ("radius_rsun", "stellar_radius_rsun")) is None:
            rad = pick("rad", "radius")
            if rad is not None:
                enriched["radius_rsun"] = float(rad)
        return enriched


__all__ = ["L1PoolEntry", "L1TargetPoolBuilder"]
