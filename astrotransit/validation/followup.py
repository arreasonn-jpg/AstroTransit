"""Takip gözlemleri için güvenli doğrulama sözleşmesi.

TESS transit tespitinin ``confirmed Earth twin`` olarak etiketlenmesi için
tek başına yeterli olmadığını zorunlu bir veri sözleşmesine dönüştürür.
Kütle, atmosfer veya yaşam ölçümü yoksa bu değerler Dünya ile doldurulmaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Iterable, Mapping, Optional


FOLLOWUP_OBSERVATION_TYPES = {
    "additional_transit",
    "radial_velocity",
    "transit_timing",
    "high_resolution_imaging",
    "jwst_transit",
    "atmospheric_spectroscopy",
    "archive_validation",
}


@dataclass(frozen=True)
class FollowupEvidence:
    """Tek bir takip gözleminin doğrulama bilgisi."""

    source: str
    observation_type: str
    observation_ids: tuple[str, ...] = ()
    confirmed: bool = False
    mass_mearth: Optional[float] = None
    mass_err_mearth: Optional[float] = None
    false_positive_probability: Optional[float] = None
    repeatable_transit: Optional[bool] = None
    atmosphere_detected: Optional[bool] = None
    life_detected: Optional[bool] = None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        source = str(self.source).strip()
        observation_type = str(self.observation_type).strip().lower()
        if not source:
            raise ValueError("Follow-up evidence source boş olamaz.")
        if observation_type not in FOLLOWUP_OBSERVATION_TYPES:
            raise ValueError(
                f"Bilinmeyen follow-up observation_type '{self.observation_type}'. "
                f"İzin verilenler: {sorted(FOLLOWUP_OBSERVATION_TYPES)}"
            )
        if self.confirmed and not self.observation_ids:
            raise ValueError("confirmed follow-up evidence en az bir observation_id gerektirir.")
        if self.mass_mearth is not None and (
            not math.isfinite(float(self.mass_mearth)) or float(self.mass_mearth) <= 0
        ):
            raise ValueError("mass_mearth pozitif ve sonlu olmalıdır.")
        if self.mass_err_mearth is not None and (
            not math.isfinite(float(self.mass_err_mearth)) or float(self.mass_err_mearth) < 0
        ):
            raise ValueError("mass_err_mearth negatif olamaz.")
        if self.false_positive_probability is not None and not 0.0 <= float(
            self.false_positive_probability
        ) <= 1.0:
            raise ValueError("false_positive_probability 0 ile 1 arasında olmalıdır.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "observation_type": self.observation_type,
            "observation_ids": list(self.observation_ids),
            "confirmed": self.confirmed,
            "mass_mearth": self.mass_mearth,
            "mass_err_mearth": self.mass_err_mearth,
            "false_positive_probability": self.false_positive_probability,
            "repeatable_transit": self.repeatable_transit,
            "atmosphere_detected": self.atmosphere_detected,
            "life_detected": self.life_detected,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class FollowupValidationResult:
    """Bir veya daha fazla takip kanıtının birleştirilmiş sonucu."""

    target_id: str = ""
    confirmed: bool = False
    status: str = "not_confirmed"
    mass_mearth: Optional[float] = None
    mass_err_mearth: Optional[float] = None
    sources: tuple[str, ...] = ()
    observation_ids: tuple[str, ...] = ()
    evidence_quality: str = "none"
    false_positive_probability: Optional[float] = None
    atmosphere_detected: Optional[bool] = None
    life_detected: Optional[bool] = None
    notes: tuple[str, ...] = ()
    evidence: tuple[FollowupEvidence, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.confirmed and (not self.evidence or not self.observation_ids):
            raise ValueError(
                "confirmed FollowupValidationResult geçerli evidence ve observation_id gerektirir."
            )
        if self.status == "followup_confirmed" and not self.confirmed:
            raise ValueError("followup_confirmed status confirmed=True gerektirir.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "confirmed": self.confirmed,
            "status": self.status,
            "mass_mearth": self.mass_mearth,
            "mass_err_mearth": self.mass_err_mearth,
            "sources": list(self.sources),
            "observation_ids": list(self.observation_ids),
            "evidence_quality": self.evidence_quality,
            "false_positive_probability": self.false_positive_probability,
            "atmosphere_detected": self.atmosphere_detected,
            "life_detected": self.life_detected,
            "notes": list(self.notes),
            "evidence": [item.to_dict() for item in self.evidence],
        }


def validate_followup_evidence(
    evidence: FollowupEvidence | Iterable[FollowupEvidence],
    *,
    target_id: str = "",
) -> FollowupValidationResult:
    """Takip kanıtını doğrular; onay bayrağını yalnızca geçerli kanıttan üretir.

    ``confirmed`` işareti açıkça takip gözleminde verilmelidir. TESS cascade
    sonucu, similarity skoru, atmosfer beklentisi veya Dünya kütlesi varsayımı
    kendiliğinden follow-up doğrulaması sayılmaz.
    """

    if isinstance(evidence, FollowupEvidence):
        items = (evidence,)
    else:
        items = tuple(evidence)
    if not items:
        return FollowupValidationResult(target_id=target_id)
    if not all(isinstance(item, FollowupEvidence) for item in items):
        raise TypeError("follow-up evidence yalnızca FollowupEvidence nesnelerinden oluşmalıdır.")

    confirmed_items = tuple(item for item in items if item.confirmed)
    fpps = [item.false_positive_probability for item in items if item.false_positive_probability is not None]
    fpp = min(fpps) if fpps else None
    contradictory = any(
        item.false_positive_probability is not None and item.false_positive_probability >= 0.5
        for item in items
    )
    confirmed = bool(confirmed_items) and not contradictory
    notes = [note for item in items for note in item.notes]
    if contradictory:
        notes.append("En az bir follow-up kanıtı yüksek FPP bildirdi; doğrulama reddedildi.")

    masses = [item.mass_mearth for item in items if item.mass_mearth is not None]
    mass_errors = [item.mass_err_mearth for item in items if item.mass_err_mearth is not None]
    atmosphere_values = [item.atmosphere_detected for item in items if item.atmosphere_detected is not None]
    life_values = [item.life_detected for item in items if item.life_detected is not None]
    sources = tuple(dict.fromkeys(item.source for item in items))
    observation_ids = tuple(
        dict.fromkeys(observation_id for item in items for observation_id in item.observation_ids)
    )

    if confirmed:
        status = "followup_confirmed"
        evidence_quality = "confirmed_observation"
    elif items:
        status = "followup_evidence_only"
        evidence_quality = "unconfirmed_observation"
    else:  # pragma: no cover - guarded above
        status = "not_confirmed"
        evidence_quality = "none"

    return FollowupValidationResult(
        target_id=target_id,
        confirmed=confirmed,
        status=status,
        mass_mearth=(float(sum(masses) / len(masses)) if masses else None),
        mass_err_mearth=min(mass_errors) if mass_errors else None,
        sources=sources,
        observation_ids=observation_ids,
        evidence_quality=evidence_quality,
        false_positive_probability=fpp,
        atmosphere_detected=any(atmosphere_values) if atmosphere_values else None,
        life_detected=any(life_values) if life_values else None,
        notes=tuple(notes),
        evidence=items,
    )


def coerce_followup_result(value: Any, *, target_id: str = "") -> FollowupValidationResult:
    """Mapping veya pipeline nesnesini güvenli follow-up sonucuna çevirir."""

    if value is None or value is False:
        return FollowupValidationResult(target_id=target_id)
    if isinstance(value, FollowupValidationResult):
        return value
    if isinstance(value, FollowupEvidence):
        return validate_followup_evidence(value, target_id=target_id)

    if isinstance(value, Mapping):
        raw_evidence = value.get("evidence")
        if raw_evidence is not None:
            if isinstance(raw_evidence, Mapping):
                raw_evidence = (raw_evidence,)
            items = tuple(
                item if isinstance(item, FollowupEvidence) else _evidence_from_mapping(item)
                for item in raw_evidence
            )
            return validate_followup_evidence(items, target_id=str(value.get("target_id", target_id)))
        if value.get("source") or value.get("observation_type"):
            item = _evidence_from_mapping(value)
            return validate_followup_evidence(item, target_id=str(value.get("target_id", target_id)))
        # Eski payload'larda yalnızca confirmed=True vardı. Bu bayrağı artık
        # gözlem kanıtı yokken doğrulama olarak kabul etmiyoruz.
        if value.get("confirmed"):
            return FollowupValidationResult(
                target_id=str(value.get("target_id", target_id)),
                status="unvalidated_confirmation",
                notes=("confirmed=True için source ve observation_id gereklidir.",),
            )
        return FollowupValidationResult(target_id=target_id)

    source = getattr(value, "source", "")
    observation_type = getattr(value, "observation_type", "")
    if source or observation_type:
        item = _evidence_from_object(value)
        return validate_followup_evidence(item, target_id=target_id)
    if getattr(value, "confirmed", False):
        return FollowupValidationResult(
            target_id=target_id,
            status="unvalidated_confirmation",
            notes=("confirmed=True için source ve observation_id gereklidir.",),
        )
    return FollowupValidationResult(target_id=target_id)


def _evidence_from_mapping(value: Mapping[str, Any]) -> FollowupEvidence:
    observation_ids = value.get("observation_ids", value.get("observation_id", ()))
    if isinstance(observation_ids, str):
        observation_ids = (observation_ids,)
    return FollowupEvidence(
        source=str(value.get("source", "")),
        observation_type=str(value.get("observation_type", "archive_validation")),
        observation_ids=tuple(str(item) for item in observation_ids or ()),
        confirmed=bool(value.get("confirmed", False)),
        mass_mearth=value.get("mass_mearth"),
        mass_err_mearth=value.get("mass_err_mearth"),
        false_positive_probability=value.get("false_positive_probability"),
        repeatable_transit=value.get("repeatable_transit"),
        atmosphere_detected=value.get("atmosphere_detected"),
        life_detected=value.get("life_detected"),
        notes=tuple(str(item) for item in value.get("notes", ()) or ()),
    )


def _evidence_from_object(value: Any) -> FollowupEvidence:
    return _evidence_from_mapping(
        {
            "source": getattr(value, "source", ""),
            "observation_type": getattr(value, "observation_type", "archive_validation"),
            "observation_ids": getattr(value, "observation_ids", ()),
            "confirmed": getattr(value, "confirmed", False),
            "mass_mearth": getattr(value, "mass_mearth", None),
            "mass_err_mearth": getattr(value, "mass_err_mearth", None),
            "false_positive_probability": getattr(value, "false_positive_probability", None),
            "repeatable_transit": getattr(value, "repeatable_transit", None),
            "atmosphere_detected": getattr(value, "atmosphere_detected", None),
            "life_detected": getattr(value, "life_detected", None),
            "notes": getattr(value, "notes", ()),
        }
    )


__all__ = [
    "FOLLOWUP_OBSERVATION_TYPES",
    "FollowupEvidence",
    "FollowupValidationResult",
    "coerce_followup_result",
    "validate_followup_evidence",
]
