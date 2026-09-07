"""RV ve ek-transit takip ölçümlerini FollowupEvidence'e çeviren adaptörler."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from astrotransit.validation.followup import FollowupEvidence


@dataclass(frozen=True)
class RVFollowupMeasurement:
    source: str
    observation_ids: tuple[str, ...]
    mass_mearth: float
    mass_err_mearth: Optional[float] = None
    false_positive_probability: Optional[float] = None
    n_epochs: int = 0
    quality_flag: str = ""


@dataclass(frozen=True)
class TransitFollowupMeasurement:
    source: str
    observation_ids: tuple[str, ...]
    period_days: float
    period_err_days: Optional[float] = None
    period_consistent: bool = False
    snr: Optional[float] = None
    false_positive_probability: Optional[float] = None


def rv_measurement_to_evidence(
    measurement: RVFollowupMeasurement,
    *,
    minimum_epochs: int = 3,
    minimum_mass_snr: float = 3.0,
) -> FollowupEvidence:
    """RV kütlesini yalnızca temel kalite koşulları sağlanırsa confirmed yapar."""

    if measurement.mass_mearth <= 0:
        raise ValueError("RV mass_mearth pozitif olmalıdır.")
    mass_snr = (
        measurement.mass_mearth / measurement.mass_err_mearth
        if measurement.mass_err_mearth and measurement.mass_err_mearth > 0
        else 0.0
    )
    confirmed = (
        len(measurement.observation_ids) >= minimum_epochs
        and measurement.n_epochs >= minimum_epochs
        and mass_snr >= minimum_mass_snr
        and measurement.quality_flag.lower() in {"", "pass", "good", "validated"}
        and (
            measurement.false_positive_probability is None
            or measurement.false_positive_probability < 0.5
        )
    )
    notes = () if confirmed else (
        "RV kanıtı temel epoch, mass-SNR veya kalite koşullarını karşılamadı.",
    )
    return FollowupEvidence(
        source=measurement.source,
        observation_type="radial_velocity",
        observation_ids=measurement.observation_ids,
        confirmed=confirmed,
        mass_mearth=measurement.mass_mearth,
        mass_err_mearth=measurement.mass_err_mearth,
        false_positive_probability=measurement.false_positive_probability,
        notes=notes,
    )


def transit_measurement_to_evidence(
    measurement: TransitFollowupMeasurement,
    *,
    minimum_snr: float = 7.0,
) -> FollowupEvidence:
    """Ek transit gözlemini repeatability ve SNR ile doğrulama kanıtına çevirir."""

    if measurement.period_days <= 0:
        raise ValueError("Follow-up period_days pozitif olmalıdır.")
    confirmed = (
        len(measurement.observation_ids) >= 2
        and measurement.period_consistent
        and measurement.snr is not None
        and measurement.snr >= minimum_snr
        and (
            measurement.false_positive_probability is None
            or measurement.false_positive_probability < 0.5
        )
    )
    notes = () if confirmed else (
        "Ek transit kanıtı en az iki gözlem, periyot tutarlılığı ve SNR koşullarını karşılamadı.",
    )
    return FollowupEvidence(
        source=measurement.source,
        observation_type="additional_transit",
        observation_ids=measurement.observation_ids,
        confirmed=confirmed,
        false_positive_probability=measurement.false_positive_probability,
        repeatable_transit=measurement.period_consistent,
        notes=notes,
    )


__all__ = [
    "RVFollowupMeasurement",
    "TransitFollowupMeasurement",
    "rv_measurement_to_evidence",
    "transit_measurement_to_evidence",
]
