"""Kampanya satırlarından hedef bazında FPP proxy telemetrisi çıkarır.

Bu modülün tek işi, pipeline'ın aday başına ürettiği heuristik risk
proxy'sini (`fpp` / `false_positive_probability`, bkz. ``fpp_method``)
doğrulama kampanyalarının satır kayıtlarından okunabilir bir kalibrasyon
vakasına dönüştürmektir. İki kural sözleşmedir:

1. **Ölçülmeyen FPP sıfır değildir.** Bir hedefte kayıt yoksa, kalite adımı
   başarısız olduysa veya kampanya telemetri sürümünden önce koştuysa, değer
   ``None`` kalır ve nedeni ``reason`` alanıyla birlikte taşınır.
2. **``quiet_star`` bir etiket değildir.** Katalog-negatif kontroller gezegen
   yokluğunu kanıtlamaz; bu yüzden Brier/precision kümesine dahil edilmez,
   ayrı ve tek yönlü bir metrik olarak raporlanır.

Etiketli kalibrasyon metriklerinin kendisi ``astrotransit.validation.
fpp_benchmark`` içindedir; bu modül yalnızca girdi hazırlığını yapar.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Optional

#: FPP proxy'sinin tanımlı olduğu tek kaynak çıktı sözleşmesi sürümü.
FPP_TELEMETRY_VERSION = "1.0"

#: Kalibrasyona giren etiketler → ``is_false_positive`` karşılığı.
CALIBRATION_LABELS: dict[str, bool] = {"false_positive": True, "planet": False}

#: Raporlanan ama kalibrasyon etiketi olmayan kohortlar.
NON_CALIBRATION_LABELS: frozenset[str] = frozenset({"quiet_star"})

#: ``reason`` alanının alabileceği değerler (sözleşme; testler bunu doğrular).
FPP_REASONS: frozenset[str] = frozenset(
    {
        "ok",
        "label_outside_calibration_set",
        "telemetry_absent",
        "no_candidate_record",
        "not_evaluated",
        "fpp_null",
        "fpp_out_of_range",
    }
)

_TELEMETRY_ABSENT = "telemetry_absent"


def finite_unit_interval(value: Any) -> Optional[float]:
    """``value``'yı sonlu ve ``[0, 1]`` aralığında bir float'a çevirir."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        return None
    return number


def _field(obj: Any, name: str, default: Any = None) -> Any:
    """Hem ``Mapping`` hem dataclass nesnelerinden alan okur."""

    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _candidate_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, "", 0):
        return False
    return bool(value)


def sector_fpp_telemetry(sector_result: Any) -> dict[str, Any]:
    """Tek bir sektör sonucundan FPP telemetrisi çıkarır.

    Kaynak, sektörün ``record`` alanıdır (çıktı sözleşmesi v1.7). Kayıt
    yoksa — yani o sektörde puanlanmış bir aday üretilmemişse — değer
    ``None`` ve neden ``no_candidate_record`` olur.
    """

    record = _field(sector_result, "record")
    sector_value = _field(sector_result, "sector", _field(record, "sector", -1))
    try:
        sector = int(sector_value)
    except (TypeError, ValueError):
        sector = -1
    accepted = _candidate_flag(
        _field(sector_result, "candidate_confirmed", _field(record, "candidate_confirmed", False))
    )
    if record is None:
        return {
            "sector": sector,
            "accepted": accepted,
            "fpp": None,
            "fpp_method": "",
            "detection_confidence": "",
            "claim_status": "",
            "candidate_class": "",
            "flags": [],
            "is_false_positive": False,
            "total_score": None,
            "fpp_available": False,
            "fpp_availability_reason": "no_candidate_record",
        }

    raw = _field(record, "false_positive_probability", _field(record, "fpp"))
    value = finite_unit_interval(raw)
    if raw is None:
        reason = "fpp_null"
    elif value is None:
        reason = "fpp_out_of_range"
    else:
        reason = "ok"
    flags = str(_field(record, "flags", "") or "")
    return {
        "sector": sector,
        "accepted": accepted,
        "fpp": value if reason == "ok" else None,
        "fpp_method": str(_field(record, "fpp_method", "") or ""),
        "detection_confidence": str(_field(record, "detection_confidence", "") or ""),
        "claim_status": str(_field(record, "claim_status", "") or ""),
        "candidate_class": str(_field(record, "candidate_class", "") or ""),
        "flags": [item.strip() for item in flags.split(",") if item.strip()],
        "is_false_positive": _candidate_flag(_field(record, "is_false_positive", False)),
        "total_score": _score_value(_field(record, "total_score")),
        "fpp_available": reason == "ok",
        "fpp_availability_reason": reason,
    }


def _score_value(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def adopt_target_fpp(sector_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Sektör telemetrilerini tek bir hedef seviyesi gözleme indirger.

    Kural deterministiktir: en yüksek ``total_score``, eşitlikte en küçük
    sektör. Böylece çok sektörlü hedeflerde seçim, sonucu üreten tespitten
    bağımsız ve yeniden üretilebilir kalır.
    """

    rows = list(sector_rows)
    available = [row for row in rows if row.get("fpp_available") and row.get("fpp") is not None]
    observed = [
        {"sector": row.get("sector"), "fpp": row.get("fpp"), "accepted": bool(row.get("accepted"))}
        for row in rows
        if row.get("fpp") is not None
    ]
    if not rows:
        return {
            "fpp": None,
            "fpp_method": "",
            "fpp_source_sector": None,
            "fpp_available": False,
            "fpp_availability_reason": _TELEMETRY_ABSENT,
            "fpp_sector_count": 0,
            "fpp_observations": observed,
        }
    if not available:
        # Telemetri kaydedildi ama hiçbir sektörde FPP yok: aday yoksa
        # "no_candidate_record", aday varsa ama FPP hesaplanmadıysa nedeni
        # sektör kayıtlarından birine düşürüyoruz.
        reasons = {str(row.get("fpp_availability_reason", "")) for row in rows}
        if reasons <= {"no_candidate_record"}:
            reason = "no_candidate_record"
        elif "fpp_out_of_range" in reasons:
            reason = "fpp_out_of_range"
        else:
            reason = "fpp_null"
        return {
            "fpp": None,
            "fpp_method": "",
            "fpp_source_sector": None,
            "fpp_available": False,
            "fpp_availability_reason": reason,
            "fpp_sector_count": len(rows),
            "fpp_observations": observed,
        }
    best = sorted(
        available,
        key=lambda row: (
            -(row.get("total_score") if row.get("total_score") is not None else float("-inf")),
            int(row.get("sector") if row.get("sector") is not None else -1),
        ),
    )[0]
    return {
        "fpp": float(best["fpp"]),
        "fpp_method": str(best.get("fpp_method", "") or ""),
        "fpp_source_sector": best.get("sector"),
        "fpp_available": True,
        "fpp_availability_reason": "ok",
        "fpp_sector_count": len(rows),
        "fpp_observations": observed,
    }


def attach_row_fpp(row: dict[str, Any]) -> dict[str, Any]:
    """Kampanya satırına hedef seviyesi FPP alanlarını ekler.

    ``sector_results`` içindeki her sektöre telemetri eklenir ve satır
    seviyesine benimsenen gözlemin alanları yazılır. Satır mutasyon yerine
    kopya üzerinde güncellenir.
    """

    updated = dict(row)
    sectors = [sector_fpp_telemetry(item) for item in updated.get("sector_results", []) or []]
    if not sectors:
        # Aday üretilmemiş hedef: sektör kaydı yok. Neden net olsun ki
        # aggregator bunu "ölçülmedi" sayabilsin.
        sectors = [
            {
                "sector": updated.get("processed_sectors", [None])[0]
                if updated.get("processed_sectors")
                else None,
                "accepted": bool(updated.get("accepted_candidate")),
                "fpp": None,
                "fpp_method": "",
                "fpp_available": False,
                "fpp_availability_reason": "no_candidate_record",
                "total_score": None,
                "flags": [],
                "candidate_class": "",
                "detection_confidence": "",
                "claim_status": "",
                "is_false_positive": False,
            }
        ]
    updated["sector_results"] = sectors
    adopted = adopt_target_fpp(sectors)
    for key, value in adopted.items():
        updated[f"target_{key}"] = value
    if updated.get("evaluated") is False and not adopted["fpp_available"]:
        # Hiçbir sektör çalışmadıysa nedeni ölçüm yokluğu olarak taşı.
        updated["target_fpp_availability_reason"] = "not_evaluated"
    updated["fpp_telemetry_version"] = FPP_TELEMETRY_VERSION
    return updated


def read_row_fpp(row: Mapping[str, Any]) -> tuple[Optional[float], str, str]:
    """Satırdan ``(fpp, fpp_method, reason)`` okur.

    Alan adları iki biçimi de kabul eder: satır seviyesi ``target_fpp*``
    alanları (yeni kampanyalar) ve düz ``fpp*`` alanları (elle yazılmış
    predictions dosyaları). Hiçbiri yoksa neden ``telemetry_absent`` olur.
    """

    label = str(row.get("label", "") or "")
    if label not in CALIBRATION_LABELS:
        return None, "", "label_outside_calibration_set"

    if "target_fpp_available" in row:
        available = bool(row.get("target_fpp_available"))
        value = finite_unit_interval(row.get("target_fpp"))
        reason = str(row.get("target_fpp_availability_reason", "") or "")
        if available and value is not None:
            return value, str(row.get("target_fpp_method", "") or ""), "ok"
        if reason == "not_evaluated":
            return None, "", "not_evaluated"
        return None, "", reason or _TELEMETRY_ABSENT

    if "fpp" in row or "false_positive_probability" in row:
        raw = row.get("fpp", row.get("false_positive_probability"))
        value = finite_unit_interval(raw)
        if raw is None:
            return None, "", "fpp_null"
        if value is None:
            return None, "", "fpp_out_of_range"
        return value, str(row.get("fpp_method", "") or ""), "ok"

    if row.get("sector_results"):
        sectors = [item for item in row["sector_results"] if isinstance(item, Mapping)]
        if any("fpp_available" in item for item in sectors):
            adopted = adopt_target_fpp(sectors)
            if adopted["fpp_available"]:
                return float(adopted["fpp"]), adopted["fpp_method"], "ok"
            return None, "", str(adopted["fpp_availability_reason"])
        return None, "", _TELEMETRY_ABSENT

    return None, "", _TELEMETRY_ABSENT


__all__ = [
    "CALIBRATION_LABELS",
    "FPP_REASONS",
    "FPP_TELEMETRY_VERSION",
    "NON_CALIBRATION_LABELS",
    "adopt_target_fpp",
    "attach_row_fpp",
    "finite_unit_interval",
    "read_row_fpp",
    "sector_fpp_telemetry",
]
