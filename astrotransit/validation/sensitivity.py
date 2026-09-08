"""Sensitivity analysis for heuristic Earth-similarity rankings."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from astrotransit.science.earth_similarity import EarthSimilarityProfile, SimilarityDimension, score_earth_similarity


@dataclass(frozen=True)
class SimilaritySensitivityReport:
    profile: str
    n_candidates: int
    n_perturbations: int
    kendall_tau_min: float | None
    kendall_tau_median: float | None
    top_k_overlap_min: float | None
    perturbation_fraction: float

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def earth_similarity_sensitivity(
    candidates: Iterable[Mapping[str, Any]],
    *,
    profile: EarthSimilarityProfile | str = "strict_earth_twin",
    perturbation_fraction: float = .10,
    top_k: int = 10,
) -> SimilaritySensitivityReport:
    """Re-score candidates after deterministic ±weight perturbations."""
    if not 0 < perturbation_fraction < 1:
        raise ValueError("perturbation_fraction 0 ile 1 arasında olmalıdır.")
    rows = list(candidates)
    baseline = [_score(row, profile) for row in rows]
    if len(rows) < 2:
        return SimilaritySensitivityReport(str(getattr(profile, "name", profile)), len(rows), 0, None, None, None, perturbation_fraction)
    selected = profile if isinstance(profile, EarthSimilarityProfile) else __import__("astrotransit.science.earth_similarity", fromlist=["get_similarity_profile"]).get_similarity_profile(profile)
    taus, overlaps = [], []
    for sign in (-1.0, 1.0):
        perturbed = _perturb(selected, sign * perturbation_fraction)
        values = [_score(row, perturbed) for row in rows]
        taus.append(_kendall_tau(baseline, values))
        k = min(top_k, len(rows))
        base_top = set(sorted(range(len(rows)), key=lambda i: baseline[i], reverse=True)[:k])
        new_top = set(sorted(range(len(rows)), key=lambda i: values[i], reverse=True)[:k])
        overlaps.append(len(base_top & new_top) / k)
    taus = [value for value in taus if value is not None]
    return SimilaritySensitivityReport(selected.name, len(rows), 2, min(taus) if taus else None,
                                       sum(taus) / len(taus) if taus else None,
                                       min(overlaps) if overlaps else None, perturbation_fraction)


def _perturb(profile: EarthSimilarityProfile, delta: float) -> EarthSimilarityProfile:
    dimensions = tuple(SimilarityDimension(item.key, item.reference, item.scale,
                                            item.weight * (1 + delta), item.unit, item.transform)
                       for item in profile.dimensions)
    return EarthSimilarityProfile(profile.name, dimensions, profile.required_dimensions,
                                  profile.minimum_score, profile.description)


def _score(row: Mapping[str, Any], profile: EarthSimilarityProfile | str) -> float:
    result = score_earth_similarity(
        profile=profile,
        planet_radius_rearth=row.get("planet_radius_rearth", row.get("radius")),
        planet_mass_mearth=row.get("planet_mass_mearth", row.get("mass")),
        insolation_s_earth=row.get("insolation_s_earth", row.get("insolation")),
        equilibrium_temperature_k=row.get("equilibrium_temperature_k", row.get("equilibrium_temperature")),
        density_gcm3=row.get("density_gcm3", row.get("density")),
        semi_major_axis_au=row.get("semi_major_axis_au", row.get("semi_major_axis")),
        stellar_teff_k=row.get("stellar_teff_k", row.get("host_teff")),
    )
    return float(result.score_p50)


def _kendall_tau(left: list[float], right: list[float]) -> float | None:
    pairs = 0
    concordant = 0
    discordant = 0
    for i in range(len(left)):
        for j in range(i + 1, len(left)):
            a = left[i] - left[j]
            b = right[i] - right[j]
            if a == 0 or b == 0:
                continue
            pairs += 1
            concordant += int(a * b > 0)
            discordant += int(a * b < 0)
    return (concordant - discordant) / pairs if pairs else None


__all__ = ["SimilaritySensitivityReport", "earth_similarity_sensitivity"]
