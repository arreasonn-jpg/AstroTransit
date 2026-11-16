"""L1 keşif kolları için evidence-gated etiket taksonomisi.

Bu modül `validation/claims.py`'nin yanındaki ayrı bir eksendir; ana
`ClaimStatus` hiyerarşisinin sırasını değiştirmez. L1 etiketleri iki kolu
ayrı ayrı adresler:

- Kol 1 (L1'de yaşanabilir Dünya-benzeri): ``L1_HABITABLE_REGION_CANDIDATE``
  ancak ana gezegen HZ'deyse ve L1 ışınımı yaşanabilir aralıktaysa üretilebilir.
- Kol 2 (L1'de kontrollü yapı): ``L1_STATIONKEEPING_REVIEW`` yalnızca follow-up
  önceliğidir; ``L1_CONTROLLED_STRUCTURE_CANDIDATE`` istasyon tutma işareti +
  makul delta-v bütçesi gerektirir. Hiçbir etiket "kontrol kanıtlandı" veya
  "yaşanabilir gezegen bulundu" anlamına gelmez.

Bağımlılık içermez; pipeline, exporter ve denetim script'leri aynı sözleşmeyi
kullanabilir.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any, Mapping


class L1ClaimLabel(StrEnum):
    L1_REGION_ASSESSED = "L1_REGION_ASSESSED"
    L1_HABITABLE_REGION_CANDIDATE = "L1_HABITABLE_REGION_CANDIDATE"
    L1_STATIONKEEPING_REVIEW = "L1_STATIONKEEPING_REVIEW"
    L1_CONTROLLED_STRUCTURE_CANDIDATE = "L1_CONTROLLED_STRUCTURE_CANDIDATE"


class L1ClaimEvidenceError(ValueError):
    """İstenen L1 etiketi mevcut kanıt tarafından desteklenmiyorsa fırlatılır."""


def _get(result: Mapping[str, Any] | Any, name: str, default: Any = None) -> Any:
    return result.get(name, default) if isinstance(result, Mapping) else getattr(result, name, default)


def infer_l1_claim(result: Mapping[str, Any] | Any) -> L1ClaimLabel:
    """Mevcut kanıtın desteklediği en güçlü L1 etiketini döndürür.

    Kol 2: ``l1_stationkeeping_review_score >= 70`` ve makul delta-v bütçesi
    (``station_keeping_budget_ok=True``) varsa ``L1_CONTROLLED_STRUCTURE_CANDIDATE``;
    yalnızca review skoru yüksekse ``L1_STATIONKEEPING_REVIEW``.
    Kol 1: ``host_in_habitable_zone is True`` ve ``l1_insolation_in_habitable_range
    is True`` ve ``earth_similarity_score >= min`` (varsayılan 90) varsa
    ``L1_HABITABLE_REGION_CANDIDATE``.
    En az L1 geometrisi hesaplandıysa ``L1_REGION_ASSESSED``.
    """
    l1_assessed = bool(_get(result, "l1_assessed", False))
    if not l1_assessed:
        return L1ClaimLabel.L1_REGION_ASSESSED if l1_assessed else L1ClaimLabel.L1_REGION_ASSESSED

    review_score = _get(result, "l1_stationkeeping_review_score", None)
    budget_ok = _get(result, "station_keeping_budget_ok", None)
    if review_score is not None and float(review_score) >= 70.0:
        if budget_ok is True:
            return L1ClaimLabel.L1_CONTROLLED_STRUCTURE_CANDIDATE
        return L1ClaimLabel.L1_STATIONKEEPING_REVIEW

    host_hz = _get(result, "host_in_habitable_zone", None)
    l1_habitable = _get(result, "l1_insolation_in_habitable_range", None)
    sim = _get(result, "earth_similarity_score", None)
    min_sim = float(_get(result, "l1_min_similarity", 90.0) or 90.0)
    if host_hz is True and l1_habitable is True and sim is not None and float(sim) >= min_sim:
        return L1ClaimLabel.L1_HABITABLE_REGION_CANDIDATE

    return L1ClaimLabel.L1_REGION_ASSESSED


def validate_l1_claim(result: Mapping[str, Any] | Any, requested: str | L1ClaimLabel) -> L1ClaimLabel:
    """İstenen L1 etiketini kanıta karşı doğrular; desteklenmiyorsa hata fırlatır."""
    requested_label = L1ClaimLabel(str(requested).upper())
    supported = infer_l1_claim(result)
    order = list(L1ClaimLabel)
    if order.index(requested_label) > order.index(supported):
        raise L1ClaimEvidenceError(
            f"{requested_label.value} requires stronger evidence; "
            f"available L1 claim is {supported.value}."
        )
    return requested_label


__all__ = [
    "L1ClaimEvidenceError",
    "L1ClaimLabel",
    "infer_l1_claim",
    "validate_l1_claim",
]
