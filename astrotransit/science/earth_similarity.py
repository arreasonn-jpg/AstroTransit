"""Dünya-benzerlik skorları ve aday sınıflandırması.

Bu modül yaşanabilirliği veya yaşamı kanıtlamaz. Transit fotometrisi ve
katalog/follow-up ölçümlerinden elde edilen fiziksel parametreleri, açıkça
tanımlanmış profillere göre karşılaştırır. Eksik bir ölçüm Dünya değeriyle
doldurulmaz; eksik ölçümler skor güvenilirliği ve sınıflandırmaya yansır.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

import numpy as np


EARTH_SIMILARITY_DEFINITION_VERSION = "1.0"


@dataclass(frozen=True)
class SimilarityDimension:
    """Tek bir fiziksel özelliğin referans ve tolerans tanımı."""

    key: str
    reference: float
    scale: float
    weight: float
    unit: str
    transform: str = "log"

    def score(self, value: Any) -> np.ndarray:
        """Değeri 0-1 aralığında benzerlik skoruna çevirir.

        Pozitif oranlar (yarıçap, kütle, ışınım, yoğunluk) log uzayında,
        sıcaklık gibi büyüklükler lineer uzayda karşılaştırılır.
        """

        values = np.asarray(value, dtype=float)
        result = np.full(values.shape, np.nan, dtype=float)
        valid = np.isfinite(values) & (values > 0)
        if self.transform == "log":
            valid &= self.reference > 0
            distance = np.zeros_like(values, dtype=float)
            distance[valid] = np.log(values[valid] / self.reference)
        elif self.transform == "linear":
            distance = values - self.reference
        else:  # pragma: no cover - profile definitions are validated below
            raise ValueError(f"Bilinmeyen similarity transform: {self.transform}")

        if self.scale <= 0:
            raise ValueError(f"{self.key} için scale pozitif olmalıdır.")
        result[valid] = np.exp(-0.5 * (distance[valid] / self.scale) ** 2)
        return result


@dataclass(frozen=True)
class EarthSimilarityProfile:
    """Dünya-benzerlik profili.

    ``required_dimensions`` tamamlanmadan yüksek bir skor alınsa bile sonuç
    strict Earth-twin sınıfına yükseltilmez.
    """

    name: str
    dimensions: tuple[SimilarityDimension, ...]
    required_dimensions: tuple[str, ...]
    minimum_score: float = 90.0
    description: str = ""

    def __post_init__(self) -> None:
        names = {item.key for item in self.dimensions}
        if len(names) != len(self.dimensions):
            raise ValueError(f"{self.name}: aynı similarity dimension birden fazla tanımlı")
        if not self.required_dimensions:
            raise ValueError(f"{self.name}: en az bir zorunlu dimension gereklidir")
        if not set(self.required_dimensions).issubset(names):
            raise ValueError(f"{self.name}: required_dimensions profilde bulunmuyor")
        if any(item.weight <= 0 for item in self.dimensions):
            raise ValueError(f"{self.name}: dimension weight değerleri pozitif olmalıdır")
        if not 0 < self.minimum_score <= 100:
            raise ValueError(f"{self.name}: minimum_score 0-100 arasında olmalıdır")

    @property
    def total_weight(self) -> float:
        return float(sum(item.weight for item in self.dimensions))


# Toleranslar bilimsel bir "kesin Dünya tanımı" değil, sıralama için
# başlangıç profilleridir. Proje kullanıcıları kendi hedef örneklemleri için
# profili kopyalayıp ağırlıkları değiştirebilir.
EARTH_SIMILARITY_PROFILES: dict[str, EarthSimilarityProfile] = {
    # v1.0: değerler, ağırlıklar ve sınıflandırma eşikleri bu profillerle
    # birlikte kaydedilir; yeni bilimsel tanımlar sürüm artırmalıdır.
    "strict_earth_twin": EarthSimilarityProfile(
        name="strict_earth_twin",
        dimensions=(
            SimilarityDimension("radius", 1.0, 0.18, 0.24, "R_earth"),
            SimilarityDimension("insolation", 1.0, 0.30, 0.24, "S_earth"),
            SimilarityDimension("equilibrium_temperature", 255.0, 38.0, 0.10, "K", "linear"),
            SimilarityDimension("mass", 1.0, 0.35, 0.19, "M_earth"),
            SimilarityDimension("density", 5.51, 0.35, 0.05, "g/cm3"),
            SimilarityDimension("semi_major_axis", 1.0, 0.45, 0.05, "AU"),
            SimilarityDimension("host_teff", 5778.0, 700.0, 0.13, "K", "linear"),
        ),
        required_dimensions=(
            "radius",
            "insolation",
            "equilibrium_temperature",
            "semi_major_axis",
            "mass",
            "host_teff",
        ),
        minimum_score=90.0,
        description="Denge sıcaklığı, yörünge, kütle ve G/K benzeri yıldız ortamı da bilinen strict profil.",
    ),
    "photometric_earth_analog": EarthSimilarityProfile(
        name="photometric_earth_analog",
        dimensions=(
            SimilarityDimension("radius", 1.0, 0.22, 0.38, "R_earth"),
            SimilarityDimension("insolation", 1.0, 0.35, 0.33, "S_earth"),
            SimilarityDimension("equilibrium_temperature", 255.0, 45.0, 0.15, "K", "linear"),
            SimilarityDimension("semi_major_axis", 1.0, 0.60, 0.05, "AU"),
            SimilarityDimension("host_teff", 5778.0, 900.0, 0.09, "K", "linear"),
        ),
        required_dimensions=(
            "radius",
            "insolation",
            "equilibrium_temperature",
            "semi_major_axis",
            "host_teff",
        ),
        minimum_score=90.0,
        description=(
            "Gezegen kütlesi olmadan; yarıçap, ışınım, denge sıcaklığı, yörünge "
            "ve yıldız sıcaklığı ile oluşturulan photometric profil."
        ),
    ),
    "terrestrial_hz_analog": EarthSimilarityProfile(
        name="terrestrial_hz_analog",
        dimensions=(
            SimilarityDimension("radius", 1.0, 0.35, 0.33, "R_earth"),
            SimilarityDimension("insolation", 1.0, 0.45, 0.42, "S_earth"),
            SimilarityDimension("equilibrium_temperature", 255.0, 55.0, 0.20, "K", "linear"),
            SimilarityDimension("semi_major_axis", 1.0, 0.75, 0.05, "AU"),
        ),
        required_dimensions=("radius", "insolation"),
        minimum_score=80.0,
        description="Geniş keşif profili: küçük, ılıman ve HZ-benzeri adaylar.",
    ),
}


_INPUT_DIMENSIONS = {
    "radius": "planet_radius_rearth",
    "mass": "planet_mass_mearth",
    "insolation": "insolation_s_earth",
    "equilibrium_temperature": "equilibrium_temperature_k",
    "density": "density_gcm3",
    "semi_major_axis": "semi_major_axis_au",
    "host_teff": "stellar_teff_k",
}


@dataclass(frozen=True)
class SimilarityComponent:
    """Bir dimension'ın hesaplanmış sonucu."""

    key: str
    value: Optional[float]
    reference: float
    score: Optional[float]
    weight: float
    unit: str
    available: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "reference": self.reference,
            "score": None if self.score is None else round(self.score * 100.0, 4),
            "weight": self.weight,
            "unit": self.unit,
            "available": self.available,
        }


@dataclass(frozen=True)
class EarthSimilarityResult:
    """Dünya-benzerlik değerlendirmesinin tamamı."""

    profile: str
    score_p05: float
    score_p50: float
    score_p95: float
    measurement_completeness: float
    classification: str
    components: dict[str, SimilarityComponent]
    missing_dimensions: tuple[str, ...]
    missing_required_dimensions: tuple[str, ...]
    uncertainty_available: bool = False
    notes: tuple[str, ...] = ()
    definition_version: str = EARTH_SIMILARITY_DEFINITION_VERSION

    @property
    def score(self) -> float:
        """Geriye dönük/kolay kullanım için medyan skor."""

        return self.score_p50

    @property
    def is_strict_candidate(self) -> bool:
        return self.classification == "EARTH_TWIN_CANDIDATE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "definition_version": self.definition_version,
            "score": round(self.score_p50, 4),
            "score_p05": round(self.score_p05, 4),
            "score_p50": round(self.score_p50, 4),
            "score_p95": round(self.score_p95, 4),
            "measurement_completeness": round(self.measurement_completeness, 4),
            "classification": self.classification,
            "missing_dimensions": list(self.missing_dimensions),
            "missing_required_dimensions": list(self.missing_required_dimensions),
            "uncertainty_available": self.uncertainty_available,
            "components": {key: value.to_dict() for key, value in self.components.items()},
            "notes": list(self.notes),
        }


def get_similarity_profile(profile: str | EarthSimilarityProfile) -> EarthSimilarityProfile:
    """İsimden profil döndürür; özel profil nesnesini olduğu gibi kabul eder."""

    if isinstance(profile, EarthSimilarityProfile):
        return profile
    key = str(profile).strip().lower()
    try:
        return EARTH_SIMILARITY_PROFILES[key]
    except KeyError as exc:
        available = ", ".join(sorted(EARTH_SIMILARITY_PROFILES))
        raise ValueError(f"Bilinmeyen Earth similarity profili '{profile}'. Kullanılabilir: {available}") from exc


def score_earth_similarity(
    profile: str | EarthSimilarityProfile = "strict_earth_twin",
    *,
    planet_radius_rearth: Optional[float] = None,
    planet_mass_mearth: Optional[float] = None,
    insolation_s_earth: Optional[float] = None,
    insolation_flux: Optional[float] = None,
    equilibrium_temperature_k: Optional[float] = None,
    density_gcm3: Optional[float] = None,
    semi_major_axis_au: Optional[float] = None,
    stellar_teff_k: Optional[float] = None,
    samples: Optional[Mapping[str, Sequence[float] | np.ndarray]] = None,
) -> EarthSimilarityResult:
    """Parametrelerden Earth similarity skorunu hesaplar.

    Parameters are in the units named by their suffix. Yörünge geometrisi
    ``semi_major_axis_au`` ile ayrıca hesaba katılır; ışınım bunun yerine
    geçmez. ``samples`` verilirse anahtarlar dimension isimleri (ör.
    ``"radius"`` veya ``"insolation"``) ya da public parametre isimleri
    olabilir. Sample dizileri aynı uzunlukta olmalı; tek elemanlı diziler tüm
    örneklere yayınlanır.
    """

    selected_profile = get_similarity_profile(profile)
    if insolation_s_earth is None:
        insolation_s_earth = insolation_flux

    values: dict[str, Any] = {
        "radius": planet_radius_rearth,
        "mass": planet_mass_mearth,
        "insolation": insolation_s_earth,
        "equilibrium_temperature": equilibrium_temperature_k,
        "density": density_gcm3,
        "semi_major_axis": semi_major_axis_au,
        "host_teff": stellar_teff_k,
    }
    sample_values = _normalise_samples(samples, values)
    components: dict[str, SimilarityComponent] = {}
    available_keys: set[str] = set()
    notes: list[str] = []

    for dimension in selected_profile.dimensions:
        raw = values[dimension.key]
        sample = sample_values.get(dimension.key)
        representative = _representative_value(sample if sample is not None else raw)
        score_array = dimension.score(sample if sample is not None else raw)
        representative_score = _representative_value(score_array)
        available = representative is not None and representative_score is not None
        if available:
            available_keys.add(dimension.key)
        components[dimension.key] = SimilarityComponent(
            key=dimension.key,
            value=representative,
            reference=dimension.reference,
            score=representative_score,
            weight=dimension.weight,
            unit=dimension.unit,
            available=available,
        )

    total_weight = selected_profile.total_weight
    available_weight = sum(
        item.weight for item in selected_profile.dimensions if item.key in available_keys
    )
    completeness = available_weight / total_weight if total_weight else 0.0
    missing = tuple(item.key for item in selected_profile.dimensions if item.key not in available_keys)
    missing_required = tuple(
        key for key in selected_profile.required_dimensions if key not in available_keys
    )

    sample_scores = _aggregate_sample_scores(selected_profile, sample_values, values)
    if sample_scores is None:
        score_p05 = score_p50 = score_p95 = _aggregate_scalar_scores(
            selected_profile, components
        )
        uncertainty_available = False
    else:
        score_p05, score_p50, score_p95 = np.percentile(sample_scores, [5, 50, 95]).tolist()
        uncertainty_available = True

    if not available_keys:
        classification = "INSUFFICIENT_DATA"
        notes.append("Earth similarity için kullanılabilir fiziksel ölçüm yok.")
    elif missing_required:
        classification = "INCOMPLETE_EARTH_TWIN"
        notes.append("Zorunlu dimension ölçümleri eksik; strict Earth-twin sınıfı verilemez.")
    elif score_p50 >= selected_profile.minimum_score:
        if selected_profile.name == "strict_earth_twin":
            classification = "EARTH_TWIN_CANDIDATE"
        elif selected_profile.name == "photometric_earth_analog":
            classification = "PHOTOMETRIC_EARTH_ANALOG"
        else:
            classification = "TERRESTRIAL_HZ_ANALOG"
    elif score_p50 >= 70.0:
        classification = "EARTHLIKE_CANDIDATE"
    else:
        classification = "LOW_EARTH_SIMILARITY"

    if uncertainty_available and score_p05 < selected_profile.minimum_score:
        notes.append(
            "Alt yüzde 5 skor profili eşiğinin altında; sınıflandırma belirsizlik içeriyor."
        )

    return EarthSimilarityResult(
        profile=selected_profile.name,
        score_p05=float(np.clip(score_p05, 0.0, 100.0)),
        score_p50=float(np.clip(score_p50, 0.0, 100.0)),
        score_p95=float(np.clip(score_p95, 0.0, 100.0)),
        measurement_completeness=float(np.clip(completeness, 0.0, 1.0)),
        classification=classification,
        components=components,
        missing_dimensions=missing,
        missing_required_dimensions=missing_required,
        uncertainty_available=uncertainty_available,
        notes=tuple(notes),
        definition_version=EARTH_SIMILARITY_DEFINITION_VERSION,
    )


def _normalise_samples(
    samples: Optional[Mapping[str, Sequence[float] | np.ndarray]],
    values: Mapping[str, Any],
) -> dict[str, np.ndarray]:
    if not samples:
        return {}
    result: dict[str, np.ndarray] = {}
    for key, sample in samples.items():
        dimension_key = key
        if key in _INPUT_DIMENSIONS.values():
            dimension_key = next(name for name, public in _INPUT_DIMENSIONS.items() if public == key)
        if dimension_key not in values:
            continue
        array = np.asarray(sample, dtype=float).reshape(-1)
        if array.size == 0:
            continue
        result[dimension_key] = array
    return result


def _representative_value(value: Any) -> Optional[float]:
    if value is None:
        return None
    array = np.asarray(value, dtype=float).reshape(-1)
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return None
    return float(np.median(finite))


def _aggregate_scalar_scores(
    profile: EarthSimilarityProfile,
    components: Mapping[str, SimilarityComponent],
) -> float:
    weighted = [
        (item.score * item.weight, item.weight)
        for item in components.values()
        if item.available and item.score is not None
    ]
    if not weighted:
        return 0.0
    return 100.0 * sum(value for value, _ in weighted) / sum(weight for _, weight in weighted)


def _aggregate_sample_scores(
    profile: EarthSimilarityProfile,
    samples: Mapping[str, np.ndarray],
    values: Mapping[str, Any],
) -> Optional[np.ndarray]:
    if not samples:
        return None
    lengths = [array.size for array in samples.values()]
    n_samples = max(lengths)
    arrays: dict[str, np.ndarray] = {}
    for dimension in profile.dimensions:
        if dimension.key in samples:
            array = samples[dimension.key]
            if array.size not in (1, n_samples):
                raise ValueError("Earth similarity sample dizileri aynı uzunlukta olmalıdır.")
            arrays[dimension.key] = np.full(n_samples, array.item()) if array.size == 1 else array
        elif values.get(dimension.key) is not None:
            arrays[dimension.key] = np.full(n_samples, float(values[dimension.key]))

    weighted_sum = np.zeros(n_samples, dtype=float)
    weight_sum = np.zeros(n_samples, dtype=float)
    for dimension in profile.dimensions:
        array = arrays.get(dimension.key)
        if array is None:
            continue
        scores = dimension.score(array)
        valid = np.isfinite(scores)
        weighted_sum[valid] += scores[valid] * dimension.weight
        weight_sum[valid] += dimension.weight

    valid_rows = weight_sum > 0
    if not np.any(valid_rows):
        return None
    return 100.0 * weighted_sum[valid_rows] / weight_sum[valid_rows]


__all__ = [
    "EARTH_SIMILARITY_DEFINITION_VERSION",
    "EARTH_SIMILARITY_PROFILES",
    "EarthSimilarityProfile",
    "EarthSimilarityResult",
    "SimilarityComponent",
    "SimilarityDimension",
    "get_similarity_profile",
    "score_earth_similarity",
]
