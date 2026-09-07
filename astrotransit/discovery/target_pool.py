"""TIC/MAST tabanlı Earth-like hedef havuzu oluşturma.

Bu modül tüm gökyüzünü tek çağrıda tarama iddiasında bulunmaz; kullanıcıdan
TIC kimlikleri veya katalog satırları alır, yıldız uygunluğunu ve TESS coverage
provenance'ını standart bir havuz dosyasına çevirir. Ağ erişimi olmayan
çalışmalar aynı akışta kayıtlı katalog satırlarıyla yürütülebilir.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from astrotransit.data.catalog_client import CatalogClient, StellarProperties
from astrotransit.data.mast_client import MASTClient, MASTConnectionError, MASTQueryError
from astrotransit.utils.identifiers import normalize_tic_id


@dataclass(frozen=True)
class TargetPoolConfig:
    """Hedef havuzu için konservatif yıldız/coverage filtreleri."""

    min_teff_k: float = 3500.0
    max_teff_k: float = 6500.0
    min_radius_rsun: float = 0.1
    max_radius_rsun: float = 2.0
    max_tmag: float = 13.0
    min_tess_sectors: int = 1
    require_stellar_mass: bool = False

    def validate(self) -> None:
        if self.min_teff_k <= 0 or self.max_teff_k <= self.min_teff_k:
            raise ValueError("Teff aralığı pozitif ve min < max olmalıdır.")
        if self.min_radius_rsun <= 0 or self.max_radius_rsun <= self.min_radius_rsun:
            raise ValueError("Yıldız yarıçapı aralığı geçersiz.")
        if self.max_tmag <= 0 or self.min_tess_sectors < 1:
            raise ValueError("Tmag ve sektör eşikleri geçersiz.")


@dataclass
class TargetPoolEntry:
    """Tek bir hedefin uygunluk ve coverage kaydı."""

    target_id: str
    tic_id: int
    eligible: bool = False
    reasons: list[str] = field(default_factory=list)
    teff_k: Optional[float] = None
    radius_rsun: Optional[float] = None
    mass_msun: Optional[float] = None
    tmag: Optional[float] = None
    luminosity_lsun: Optional[float] = None
    sectors: tuple[int, ...] = ()
    n_sectors: int = 0
    coverage_baseline_days: Optional[float] = None
    source: str = "TIC/MAST"

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["sectors"] = list(self.sectors)
        return row


class EarthTargetPoolBuilder:
    """TIC katalog ve MAST coverage bilgilerini Earth-search girdisine çevirir."""

    def __init__(
        self,
        config: Optional[TargetPoolConfig] = None,
        *,
        catalog_client: Optional[CatalogClient] = None,
        mast_client: Optional[MASTClient] = None,
    ):
        self.config = config or TargetPoolConfig()
        self.config.validate()
        self.catalog_client = catalog_client or CatalogClient()
        self.mast_client = mast_client or MASTClient()

    def build_from_tic_ids(
        self,
        tic_ids: Iterable[str | int],
        *,
        query_coverage: bool = True,
    ) -> list[TargetPoolEntry]:
        entries: list[TargetPoolEntry] = []
        for tic_id in tic_ids:
            target_id = normalize_tic_id(tic_id)
            numeric_id = int(target_id.split()[1])
            try:
                properties = self.catalog_client.get_stellar_properties(target_id)
            except Exception as exc:
                entries.append(
                    TargetPoolEntry(
                        target_id=target_id,
                        tic_id=numeric_id,
                        reasons=[f"catalog_error: {exc}"],
                    )
                )
                continue
            coverage = self._query_coverage(target_id) if query_coverage else ((), None)
            entries.append(self.evaluate(properties, *coverage))
        return entries

    def build_from_mast_catalog(
        self,
        *,
        coordinates: str,
        radius: str = "1 deg",
        query_coverage: bool = True,
    ) -> list[TargetPoolEntry]:
        """MAST TIC kataloğunu sorgulayıp filtrelenmiş hedef havuzu üretir."""

        catalog = self.mast_client.query_tic_catalog(
            coordinates=coordinates,
            radius=radius,
        )
        rows = []
        for row in catalog:
            names = getattr(row, "colnames", None)
            if names:
                rows.append({name: row[name] for name in names})
            elif isinstance(row, Mapping):
                rows.append(dict(row))
            else:
                rows.append({})
        return self.build_from_rows(rows, query_coverage=query_coverage)

    def build_from_rows(
        self,
        rows: Iterable[Mapping[str, Any]],
        *,
        query_coverage: bool = False,
    ) -> list[TargetPoolEntry]:
        """Ağsız/reproducible çalıştırmalar için TIC-benzeri satırları değerlendirir."""

        entries: list[TargetPoolEntry] = []
        for row in rows:
            raw_id = next(
                (
                    row.get(key)
                    for key in ("target_id", "tic_id", "TIC", "ID", "id")
                    if row.get(key) not in (None, "")
                ),
                "",
            )
            target_id = normalize_tic_id(raw_id)
            tic_id = int(target_id.split()[1])
            properties = self._properties_from_row(row, tic_id)
            if query_coverage:
                sectors, baseline = self._query_coverage(target_id)
            else:
                sectors = self._sectors_from_value(row.get("sectors", ()))
                baseline = self._optional_float(row.get("coverage_baseline_days"))
            entries.append(self.evaluate(properties, sectors, baseline))
        return entries

    def evaluate(
        self,
        properties: StellarProperties,
        sectors: Iterable[int] = (),
        coverage_baseline_days: Optional[float] = None,
    ) -> TargetPoolEntry:
        target_id = normalize_tic_id(properties.tic_id)
        reasons: list[str] = []
        if not properties.teff > 0:
            reasons.append("missing_teff")
        elif not self.config.min_teff_k <= properties.teff <= self.config.max_teff_k:
            reasons.append("teff_out_of_range")
        if not properties.radius > 0:
            reasons.append("missing_radius")
        elif not self.config.min_radius_rsun <= properties.radius <= self.config.max_radius_rsun:
            reasons.append("radius_out_of_range")
        if properties.tmag <= 0:
            reasons.append("missing_tmag")
        elif properties.tmag > self.config.max_tmag:
            reasons.append("tmag_too_faint")
        if self.config.require_stellar_mass and not properties.mass > 0:
            reasons.append("missing_stellar_mass")

        sector_tuple = tuple(sorted(set(int(value) for value in sectors)))
        if len(sector_tuple) < self.config.min_tess_sectors:
            reasons.append("insufficient_tess_sectors")
        return TargetPoolEntry(
            target_id=target_id,
            tic_id=int(properties.tic_id),
            eligible=not reasons,
            reasons=reasons,
            teff_k=properties.teff if properties.teff > 0 else None,
            radius_rsun=properties.radius if properties.radius > 0 else None,
            mass_msun=properties.mass if properties.mass > 0 else None,
            tmag=properties.tmag if properties.tmag > 0 else None,
            luminosity_lsun=properties.luminosity if properties.luminosity > 0 else None,
            sectors=sector_tuple,
            n_sectors=len(sector_tuple),
            coverage_baseline_days=coverage_baseline_days,
            source=properties.source or "TIC/MAST",
        )

    def write_json(self, entries: Iterable[TargetPoolEntry], path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps([entry.to_dict() for entry in entries], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output

    def write_csv(self, entries: Iterable[TargetPoolEntry], path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        rows = [entry.to_dict() for entry in entries]
        fieldnames = list(TargetPoolEntry.__dataclass_fields__)
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                row["sectors"] = json.dumps(row["sectors"])
                row["reasons"] = json.dumps(row["reasons"], ensure_ascii=False)
                writer.writerow(row)
        return output

    def _query_coverage(self, target_id: str) -> tuple[tuple[int, ...], Optional[float]]:
        try:
            observations = self.mast_client.query_observations(
                target_name=target_id,
                obs_collection="TESS",
                dataproduct_type="timeseries",
            )
        except (MASTConnectionError, MASTQueryError):
            return (), None
        sectors: set[int] = set()
        starts: list[float] = []
        ends: list[float] = []
        for row in observations:
            colnames = getattr(row, "colnames", None)
            if colnames is None and isinstance(row, Mapping):
                colnames = row.keys()
            colnames = tuple(colnames or ())
            try:
                if "sequence_number" in colnames:
                    sectors.add(int(row["sequence_number"]))
                elif "sector" in colnames:
                    sectors.add(int(row["sector"]))
            except (TypeError, ValueError):
                pass
            for start_key, end_key in (
                ("t_min", "t_max"),
                ("t_start", "t_end"),
                ("start_time", "end_time"),
            ):
                colnames = getattr(row, "colnames", [])
                if start_key in colnames and end_key in colnames:
                    try:
                        starts.append(float(row[start_key]))
                        ends.append(float(row[end_key]))
                    except (TypeError, ValueError):
                        pass
                    break
        baseline = max(ends) - min(starts) if starts and ends and max(ends) >= min(starts) else None
        return tuple(sorted(sectors)), baseline

    @staticmethod
    def _sectors_from_value(value: Any) -> tuple[int, ...]:
        if value in (None, ""):
            return ()
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = value.replace(";", ",").split(",")
            value = parsed if isinstance(parsed, (list, tuple)) else (parsed,)
        try:
            return tuple(int(item) for item in value)
        except (TypeError, ValueError):
            return ()

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        try:
            result = float(value)
            return result if result > 0 else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _properties_from_row(row: Mapping[str, Any], tic_id: int) -> StellarProperties:
        def value(*keys: str) -> float:
            for key in keys:
                if key in row:
                    try:
                        return float(row[key])
                    except (TypeError, ValueError):
                        continue
            return 0.0

        return StellarProperties(
            tic_id=tic_id,
            teff=value("teff", "Teff", "teff_k"),
            radius=value("radius", "rad", "radius_rsun"),
            mass=value("mass", "mass_msun"),
            tmag=value("tmag", "Tmag"),
            luminosity=value("luminosity", "lum", "luminosity_lsun"),
            source=str(row.get("source", "catalog_row")),
        )


__all__ = ["EarthTargetPoolBuilder", "TargetPoolConfig", "TargetPoolEntry"]
