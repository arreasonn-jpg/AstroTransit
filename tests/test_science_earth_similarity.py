"""astrotransit/science/earth_similarity.py için kapsamlı testler."""
from __future__ import annotations

import numpy as np
import pytest

from astrotransit.science.earth_similarity import (
    EARTH_SIMILARITY_DEFINITION_VERSION,
    EARTH_SIMILARITY_PROFILES,
    EarthSimilarityProfile,
    EarthSimilarityResult,
    SimilarityComponent,
    SimilarityDimension,
    _aggregate_sample_scores,
    _aggregate_scalar_scores,
    _normalise_samples,
    _representative_value,
    _samples_from_errors,
    get_similarity_profile,
    score_earth_similarity,
)

# ═══════════════════════════════════════════════════════
# SimilarityDimension
# ═══════════════════════════════════════════════════════

def test_dimension_log_score_positive():
    d = SimilarityDimension("radius", 1.0, 0.18, 0.24, "R_earth")
    score = d.score(1.0)
    assert score == pytest.approx(1.0)


def test_dimension_log_score_off():
    d = SimilarityDimension("radius", 1.0, 0.18, 0.24, "R_earth")
    score = d.score(2.0)
    assert score < 1.0


def test_dimension_linear_score():
    d = SimilarityDimension("teff", 5778.0, 700.0, 0.13, "K", "linear")
    assert d.score(5778.0) == pytest.approx(1.0)


def test_dimension_invalid_transform():
    d = SimilarityDimension("x", 1.0, 0.1, 0.5, "u", "weird")
    with pytest.raises(ValueError, match="transform"):
        d.score(1.0)


def test_dimension_invalid_scale():
    d = SimilarityDimension("x", 1.0, 0.0, 0.5, "u")
    with pytest.raises(ValueError, match="scale"):
        d.score(1.0)


def test_dimension_invalid_values():
    d = SimilarityDimension("radius", 1.0, 0.18, 0.24, "R_earth")
    score = d.score(np.array([-1.0, 0.0, np.nan, np.inf, 1.0]))
    assert np.isnan(score[0])
    assert np.isnan(score[1])
    assert np.isnan(score[2])
    assert np.isnan(score[3])
    assert score[4] == pytest.approx(1.0)


# ═══════════════════════════════════════════════════════
# EarthSimilarityProfile.__post_init__
# ═══════════════════════════════════════════════════════

def _dim(key, weight=0.5):
    return SimilarityDimension(key, 1.0, 0.2, weight, "unit")


def test_profile_duplicate_dimensions():
    with pytest.raises(ValueError, match="aynı similarity"):
        EarthSimilarityProfile(
            name="x",
            dimensions=(_dim("radius"), _dim("radius")),
            required_dimensions=("radius",),
        )


def test_profile_empty_required():
    with pytest.raises(ValueError, match="zorunlu"):
        EarthSimilarityProfile(
            name="x", dimensions=(_dim("radius"),), required_dimensions=(),
        )


def test_profile_required_not_in_dimensions():
    with pytest.raises(ValueError, match="required_dimensions"):
        EarthSimilarityProfile(
            name="x",
            dimensions=(_dim("radius"),),
            required_dimensions=("mass",),
        )


def test_profile_negative_weight():
    with pytest.raises(ValueError, match="weight"):
        EarthSimilarityProfile(
            name="x",
            dimensions=(SimilarityDimension("radius", 1.0, 0.2, -0.5, "u"),),
            required_dimensions=("radius",),
        )


def test_profile_bad_minimum_score():
    with pytest.raises(ValueError, match="minimum_score"):
        EarthSimilarityProfile(
            name="x", dimensions=(_dim("radius"),),
            required_dimensions=("radius",), minimum_score=150.0,
        )


def test_profile_total_weight():
    p = EarthSimilarityProfile(
        name="x", dimensions=(_dim("a", 0.3), _dim("b", 0.7)),
        required_dimensions=("a",),
    )
    assert p.total_weight == pytest.approx(1.0)


# ═══════════════════════════════════════════════════════
# SimilarityComponent / EarthSimilarityResult
# ═══════════════════════════════════════════════════════

def test_component_to_dict():
    c = SimilarityComponent("radius", 1.0, 1.0, 0.95, 0.24, "R_earth", True)
    d = c.to_dict()
    assert d["value"] == 1.0
    assert d["score"] == 95.0
    assert d["available"] is True


def test_component_to_dict_none_score():
    c = SimilarityComponent("radius", None, 1.0, None, 0.24, "R_earth", False)
    d = c.to_dict()
    assert d["score"] is None
    assert d["available"] is False


def test_result_score_alias():
    r = EarthSimilarityResult(
        profile="strict_earth_twin",
        score_p05=80.0, score_p50=92.0, score_p95=99.0,
        measurement_completeness=1.0,
        classification="EARTH_TWIN_CANDIDATE",
        components={}, missing_dimensions=(), missing_required_dimensions=(),
    )
    assert r.score == 92.0
    assert r.is_strict_candidate is True


def test_result_to_dict():
    r = EarthSimilarityResult(
        profile="strict_earth_twin",
        score_p05=80.0, score_p50=92.0, score_p95=99.0,
        measurement_completeness=1.0,
        classification="EARTHLIKE_CANDIDATE",
        components={}, missing_dimensions=("mass",), missing_required_dimensions=(),
        notes=("test",),
    )
    d = r.to_dict()
    assert d["profile"] == "strict_earth_twin"
    assert d["score"] == 92.0
    assert d["classification"] == "EARTHLIKE_CANDIDATE"
    assert d["notes"] == ["test"]
    assert d["definition_version"] == EARTH_SIMILARITY_DEFINITION_VERSION


# ═══════════════════════════════════════════════════════
# get_similarity_profile
# ═══════════════════════════════════════════════════════

def test_get_profile_by_name():
    p = get_similarity_profile("strict_earth_twin")
    assert p.name == "strict_earth_twin"


def test_get_profile_case_insensitive():
    p = get_similarity_profile("STRICT_EARTH_TWIN")
    assert p.name == "strict_earth_twin"


def test_get_profile_passthrough():
    custom = EarthSimilarityProfile(
        name="custom", dimensions=(_dim("radius"),),
        required_dimensions=("radius",),
    )
    assert get_similarity_profile(custom) is custom


def test_get_profile_unknown():
    with pytest.raises(ValueError, match="Bilinmeyen"):
        get_similarity_profile("nope")


# ═══════════════════════════════════════════════════════
# _representative_value
# ═══════════════════════════════════════════════════════

def test_representative_none():
    assert _representative_value(None) is None


def test_representative_all_nan():
    assert _representative_value(np.array([np.nan, np.inf])) is None


def test_representative_median():
    assert _representative_value([1.0, 2.0, 3.0]) == 2.0


def test_representative_scalar():
    assert _representative_value(5.0) == 5.0


# ═══════════════════════════════════════════════════════
# _samples_from_errors
# ═══════════════════════════════════════════════════════

def test_samples_errors_too_few():
    with pytest.raises(ValueError, match="n_samples"):
        _samples_from_errors({"radius": 1.0}, {"radius": 0.1}, n_samples=1, random_seed=0)


def test_samples_errors_unknown_key():
    with pytest.raises(ValueError, match="Bilinmeyen"):
        _samples_from_errors({"radius": 1.0}, {"unknown": 0.1}, n_samples=100, random_seed=0)


def test_samples_errors_non_numeric():
    with pytest.raises(ValueError, match="sayısal"):
        _samples_from_errors({"radius": 1.0}, {"radius": "bad"}, n_samples=100, random_seed=0)


def test_samples_errors_negative():
    with pytest.raises(ValueError, match="sonlu"):
        _samples_from_errors({"radius": 1.0}, {"radius": -1.0}, n_samples=100, random_seed=0)


def test_samples_errors_zero_sigma():
    """sigma=0 → sabit örnek."""
    s = _samples_from_errors(
        {"radius": 1.0}, {"radius": 0.0}, n_samples=10, random_seed=0,
    )
    assert np.all(s["radius"] == 1.0)


def test_samples_errors_center_invalid():
    """center değeri yok veya negatif → atlanır."""
    s = _samples_from_errors(
        {"radius": None}, {"radius": 0.1}, n_samples=10, random_seed=0,
    )
    assert "radius" not in s

    s2 = _samples_from_errors(
        {"radius": -1.0}, {"radius": 0.1}, n_samples=10, random_seed=0,
    )
    assert "radius" not in s2


def test_samples_errors_public_key_alias():
    """public isim (planet_radius_rearth) → dimension key'e çevrilir."""
    s = _samples_from_errors(
        {"radius": 1.0}, {"planet_radius_rearth": 0.1},
        n_samples=100, random_seed=0,
    )
    assert "radius" in s


def test_samples_errors_lognormal_for_positive():
    s = _samples_from_errors(
        {"radius": 1.0}, {"radius": 0.1}, n_samples=1000, random_seed=42,
    )
    assert np.all(s["radius"] > 0)


def test_samples_errors_normal_for_teff():
    s = _samples_from_errors(
        {"host_teff": 5778.0}, {"host_teff": 100.0},
        n_samples=1000, random_seed=42,
    )
    assert "host_teff" in s


# ═══════════════════════════════════════════════════════
# _normalise_samples
# ═══════════════════════════════════════════════════════

def test_normalise_empty():
    assert _normalise_samples(None, {"radius": 1.0}) == {}
    assert _normalise_samples({}, {"radius": 1.0}) == {}


def test_normalise_unknown_key():
    assert _normalise_samples({"unknown": [1.0]}, {"radius": 1.0}) == {}


def test_normalise_empty_array():
    assert _normalise_samples({"radius": []}, {"radius": 1.0}) == {}


def test_normalise_public_alias():
    r = _normalise_samples(
        {"planet_radius_rearth": [1.0, 1.1]}, {"radius": 1.0},
    )
    assert "radius" in r
    assert len(r["radius"]) == 2


# ═══════════════════════════════════════════════════════
# _aggregate_scalar_scores
# ═══════════════════════════════════════════════════════

def test_aggregate_scalar_no_available():
    p = EARTH_SIMILARITY_PROFILES["strict_earth_twin"]
    comps = {k: SimilarityComponent(k, None, 1.0, None, 1.0, "u", False)
             for k in ("radius", "mass")}
    assert _aggregate_scalar_scores(p, comps) == 0.0


def test_aggregate_scalar_weighted():
    p = EarthSimilarityProfile(
        name="x",
        dimensions=(
            SimilarityDimension("radius", 1.0, 0.2, 0.5, "u"),
            SimilarityDimension("mass", 1.0, 0.2, 0.5, "u"),
        ),
        required_dimensions=("radius",),
    )
    comps = {
        "radius": SimilarityComponent("radius", 1.0, 1.0, 1.0, 0.5, "u", True),
        "mass": SimilarityComponent("mass", 1.0, 1.0, 0.0, 0.5, "u", True),
    }
    s = _aggregate_scalar_scores(p, comps)
    assert s == pytest.approx(50.0)


# ═══════════════════════════════════════════════════════
# _aggregate_sample_scores
# ═══════════════════════════════════════════════════════

def test_aggregate_sample_empty():
    p = EARTH_SIMILARITY_PROFILES["strict_earth_twin"]
    assert _aggregate_sample_scores(p, {}, {}) is None


def test_aggregate_sample_length_mismatch():
    p = EarthSimilarityProfile(
        name="x",
        dimensions=(
            SimilarityDimension("radius", 1.0, 0.2, 0.5, "u"),
            SimilarityDimension("mass", 1.0, 0.2, 0.5, "u"),
        ),
        required_dimensions=("radius",),
    )
    samples = {
        "radius": np.array([1.0, 1.1, 1.2]),
        "mass": np.array([1.0, 1.1]),
    }
    with pytest.raises(ValueError, match="aynı uzunluk"):
        _aggregate_sample_scores(p, samples, {"radius": 1.0, "mass": 1.0})


def test_aggregate_sample_broadcast_single():
    """Tek elemanlı array tüm örneklere yayınlanır."""
    p = EarthSimilarityProfile(
        name="x",
        dimensions=(SimilarityDimension("radius", 1.0, 0.2, 1.0, "u"),),
        required_dimensions=("radius",),
    )
    samples = {"radius": np.array([1.0])}
    s = _aggregate_sample_scores(p, samples, {"radius": 1.0})
    assert s is not None


def test_aggregate_sample_all_invalid_returns_none():
    p = EarthSimilarityProfile(
        name="x",
        dimensions=(SimilarityDimension("radius", 1.0, 0.2, 1.0, "u"),),
        required_dimensions=("radius",),
    )
    samples = {"radius": np.array([-1.0, -2.0])}  # negatif → NaN skor
    s = _aggregate_sample_scores(p, samples, {"radius": -1.0})
    assert s is None


# ═══════════════════════════════════════════════════════
# score_earth_similarity
# ═══════════════════════════════════════════════════════

def test_score_insufficient():
    r = score_earth_similarity("strict_earth_twin")
    assert r.classification == "INSUFFICIENT_DATA"
    assert r.measurement_completeness == 0.0
    assert any("kullanılabilir" in n for n in r.notes)


def test_score_incomplete_missing_required():
    """Sadece radius verilirse required_dimensions eksik → INCOMPLETE."""
    r = score_earth_similarity("strict_earth_twin", planet_radius_rearth=1.0)
    assert r.classification == "INCOMPLETE_EARTH_TWIN"


def test_score_full_earth_twin():
    r = score_earth_similarity(
        "strict_earth_twin",
        planet_radius_rearth=1.0,
        planet_mass_mearth=1.0,
        insolation_s_earth=1.0,
        equilibrium_temperature_k=255.0,
        density_gcm3=5.51,
        semi_major_axis_au=1.0,
        stellar_teff_k=5778.0,
    )
    assert r.classification == "EARTH_TWIN_CANDIDATE"
    assert r.is_strict_candidate is True
    assert r.score_p50 > 90.0


def test_score_photometric_profile():
    r = score_earth_similarity(
        "photometric_earth_analog",
        planet_radius_rearth=1.0,
        insolation_s_earth=1.0,
        equilibrium_temperature_k=255.0,
        semi_major_axis_au=1.0,
        stellar_teff_k=5778.0,
    )
    assert r.classification == "PHOTOMETRIC_EARTH_ANALOG"


def test_score_terrestrial_hz_profile():
    r = score_earth_similarity(
        "terrestrial_hz_analog",
        planet_radius_rearth=1.0,
        insolation_s_earth=1.0,
        equilibrium_temperature_k=255.0,
        semi_major_axis_au=1.0,
    )
    assert r.classification == "TERRESTRIAL_HZ_ANALOG"


def test_score_earthlike_candidate():
    # Değerleri Earth-twin sınırının (90) hemen altında tut → EARTHLIKE_CANDIDATE
    r = score_earth_similarity(
        "photometric_earth_analog",
        planet_radius_rearth=1.15,
        insolation_s_earth=1.2,
        equilibrium_temperature_k=260.0,
        semi_major_axis_au=1.05,
        stellar_teff_k=5800.0,
    )
    assert r.classification == "EARTHLIKE_CANDIDATE"
    assert 70.0 <= r.score_p50 < 90.0


def test_score_low_similarity():
    r = score_earth_similarity(
        "photometric_earth_analog",
        planet_radius_rearth=5.0,
        insolation_s_earth=100.0,
        equilibrium_temperature_k=1500.0,
        semi_major_axis_au=0.05,
        stellar_teff_k=5778.0,
    )
    assert r.classification == "LOW_EARTH_SIMILARITY"


def test_score_insolation_flux_alias():
    """insolation_flux parametresi insolation_s_earth'e aktarılır."""
    r = score_earth_similarity(
        "photometric_earth_analog",
        planet_radius_rearth=1.0,
        insolation_flux=1.0,
        equilibrium_temperature_k=255.0,
        semi_major_axis_au=1.0,
        stellar_teff_k=5778.0,
    )
    assert r.measurement_completeness > 0


def test_score_samples_and_errors_conflict():
    with pytest.raises(ValueError, match="samples ve errors"):
        score_earth_similarity(
            "photometric_earth_analog",
            planet_radius_rearth=1.0,
            samples={"radius": [1.0, 1.1]},
            errors={"radius": 0.1},
        )


def test_score_with_errors_uncertainty():
    r = score_earth_similarity(
        "photometric_earth_analog",
        planet_radius_rearth=1.0,
        insolation_s_earth=1.0,
        equilibrium_temperature_k=255.0,
        semi_major_axis_au=1.0,
        stellar_teff_k=5778.0,
        errors={"radius": 0.05, "insolation": 0.05},
        n_samples=200,
    )
    assert r.uncertainty_available is True
    assert r.score_p05 <= r.score_p50 <= r.score_p95


def test_score_with_samples_uncertainty():
    r = score_earth_similarity(
        "photometric_earth_analog",
        samples={
            "radius": np.linspace(0.9, 1.1, 100),
            "insolation": np.linspace(0.9, 1.1, 100),
            "equilibrium_temperature": np.linspace(245, 265, 100),
            "semi_major_axis": np.linspace(0.95, 1.05, 100),
            "host_teff": np.linspace(5600, 5900, 100),
        },
    )
    assert r.uncertainty_available is True


def test_score_uncertainty_note_low_p05():
    """Alt %5 skoru eşiğin altında ise not eklenir."""
    r = score_earth_similarity(
        "photometric_earth_analog",
        samples={
            "radius": np.concatenate([[1.0] * 50, [1.5] * 50]),
            "insolation": np.concatenate([[1.0] * 50, [2.0] * 50]),
            "equilibrium_temperature": np.concatenate([[255.0] * 50, [300.0] * 50]),
            "semi_major_axis": np.concatenate([[1.0] * 50, [1.2] * 50]),
            "host_teff": np.concatenate([[5778.0] * 50, [6000.0] * 50]),
        },
    )
    # p05 eşiğin altında olabilir, not eklenmiş olması beklenir
    assert r.uncertainty_available is True


def test_score_bad_profile():
    with pytest.raises(ValueError, match="Bilinmeyen"):
        score_earth_similarity("nonexistent_profile", planet_radius_rearth=1.0)


def test_score_definition_version():
    r = score_earth_similarity("photometric_earth_analog", planet_radius_rearth=1.0)
    assert r.definition_version == EARTH_SIMILARITY_DEFINITION_VERSION


# ═══════════════════════════════════════════════════════
# _samples_from_errors — center float dönüşümü başarısız (430-431)
# ═══════════════════════════════════════════════════════

def test_samples_errors_center_not_convertible():
    """center float'a çevrilemeyen obje → atlanır (430-431)."""
    class _BadValue:
        def __float__(self):
            raise ValueError("cannot convert")
    s = _samples_from_errors(
        {"radius": _BadValue()}, {"radius": 0.1},
        n_samples=10, random_seed=0,
    )
    assert "radius" not in s
