"""L1 keşif havuzu için kalıcı çıktı şeması ve yazıcı.

`l1-search` CLI çıktısını standart çıktı katmanına (schema versiyonlu JSON)
bağlar. Kayıtlar `L1PoolEntry.to_dict()` ile birebir uyumludur; ek olarak
`metadata` bölümünde şema versiyonu ve oluşturulma zamanı tutulur.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from astrotransit.outputs.json_writer import NumpyEncoder
from astrotransit.version import __version__

# Bağımsız L1 havuzu şeması; ana TransitCandidateRecord şemasından ayrıdır.
L1_POOL_SCHEMA_VERSION = "1.0"


@dataclass
class L1PoolRecord:
    """Tek bir L1 havuzu girdisinin şema versiyonlu kaydı."""

    target_id: str
    l1_assessed: bool
    l1_distance_from_planet_au: Optional[float] = None
    l1_distance_from_star_au: Optional[float] = None
    l1_stability_e_folding_days: Optional[float] = None
    l1_earth_twin: dict[str, Any] = field(default_factory=dict)
    l1_structure: dict[str, Any] = field(default_factory=dict)
    l1_claim_label: Optional[str] = None
    schema_version: str = L1_POOL_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_l1_pool_record(entry: Any) -> L1PoolRecord:
    """`L1PoolEntry` (veya eşdeğer mapping) kaydını şema kaydına dönüştürür."""

    if hasattr(entry, "to_dict"):
        data = entry.to_dict()
    elif isinstance(entry, dict):
        data = dict(entry)
    else:
        data = {name: getattr(entry, name) for name in (
            "target_id", "l1_assessed", "l1_distance_from_planet_au",
            "l1_distance_from_star_au", "l1_stability_e_folding_days",
            "l1_earth_twin", "l1_structure", "l1_claim_label",
        )}
    return L1PoolRecord(
        target_id=str(data.get("target_id", "")),
        l1_assessed=bool(data.get("l1_assessed", False)),
        l1_distance_from_planet_au=data.get("l1_distance_from_planet_au"),
        l1_distance_from_star_au=data.get("l1_distance_from_star_au"),
        l1_stability_e_folding_days=data.get("l1_stability_e_folding_days"),
        l1_earth_twin=dict(data.get("l1_earth_twin") or {}),
        l1_structure=dict(data.get("l1_structure") or {}),
        l1_claim_label=data.get("l1_claim_label"),
    )


def build_l1_pool_payload(entries: Iterable[Any], *, branch: str = "both") -> dict[str, Any]:
    """Tüm havuz için şema versiyonlu JSON payload üretir."""

    records = [build_l1_pool_record(entry).to_dict() for entry in entries]
    return {
        "metadata": {
            "astrotransit_version": __version__,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "schema_version": L1_POOL_SCHEMA_VERSION,
            "kind": "l1_target_pool",
            "branch": branch,
        },
        "targets": records,
    }


def write_l1_pool_json(
    entries: Iterable[Any],
    path: str | Path,
    *,
    branch: str = "both",
) -> Path:
    """L1 havuzunu şema versiyonlu JSON olarak yazar (atomik)."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_l1_pool_payload(entries, branch=branch)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, cls=NumpyEncoder, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    temp_path.replace(path)
    return path


__all__ = [
    "L1_POOL_SCHEMA_VERSION",
    "L1PoolRecord",
    "build_l1_pool_payload",
    "build_l1_pool_record",
    "write_l1_pool_json",
]
