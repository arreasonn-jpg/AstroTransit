"""Kol 1 (L1 Earth-twin) skorlayıcı testleri."""

from __future__ import annotations

import pytest

from astrotransit.discovery.l1_earth_twin import L1EarthTwinCandidate, L1EarthTwinScorer
from astrotransit.dynamics.lagrange import M_EARTH_KG, M_SUN_KG


@pytest.fixture()
def scorer() -> L1EarthTwinScorer:
    return L1EarthTwinScorer(min_similarity=90.0)


def _sun_earth_like_kwargs(**overrides):
    kwargs = dict(
        m_star_kg=1.0 * M_SUN_KG,
        m_planet_kg=1.0 * M_EARTH_KG,
        separation_au=1.0,
        stellar_luminosity_lsun=1.0,
        stellar_teff_k=5778.0,
        stellar_radius_rsun=1.0,
        host_in_habitable_zone=True,
        candidate_radius_rearth=1.0,
        candidate_mass_mearth=1.0,
        candidate_equilibrium_temperature_k=255.0,
    )
    kwargs.update(overrides)
    return kwargs


def test_eligible_path_sun_earth_like(scorer: L1EarthTwinScorer):
    result = scorer.evaluate("TIC 1", **_sun_earth_like_kwargs())
    assert isinstance(result, L1EarthTwinCandidate)
    assert result.l1_distance_from_star_au is not None
    assert result.l1_distance_from_star_au == pytest.approx(0.99, abs=0.01)
    assert result.l1_insolation_s_earth is not None
    assert 0.25 <= result.l1_insolation_s_earth <= 2.0
    assert result.earth_similarity_score is not None
    assert result.earth_similarity_score >= 90.0
    assert result.eligible is True
    assert any("HZ" in note or "ön koşul" in note for note in result.rationale)


def test_host_not_in_hz_not_eligible(scorer: L1EarthTwinScorer):
    result = scorer.evaluate("TIC 2", **_sun_earth_like_kwargs(host_in_habitable_zone=False))
    assert result.eligible is False
    assert result.host_in_habitable_zone is False
    assert any("HZ" in note for note in result.rationale)


def test_host_hz_unknown_not_eligible(scorer: L1EarthTwinScorer):
    result = scorer.evaluate("TIC 3", **_sun_earth_like_kwargs(host_in_habitable_zone=None))
    assert result.eligible is False
    assert result.host_in_habitable_zone is None


def test_missing_masses_none_not_zero(scorer: L1EarthTwinScorer):
    result = scorer.evaluate(
        "TIC 4",
        m_star_kg=None,
        m_planet_kg=None,
        separation_au=None,
        stellar_luminosity_lsun=1.0,
        host_in_habitable_zone=True,
        candidate_radius_rearth=1.0,
        candidate_mass_mearth=1.0,
        candidate_equilibrium_temperature_k=255.0,
        stellar_teff_k=5778.0,
    )
    assert result.l1_distance_from_star_au is None
    assert result.l1_insolation_s_earth is None
    assert result.eligible is False
    data = result.to_dict()
    assert data["l1_distance_from_star_au"] is None
    assert data["l1_insolation_s_earth"] is None


def test_low_similarity_not_eligible(scorer: L1EarthTwinScorer):
    result = scorer.evaluate(
        "TIC 5",
        **_sun_earth_like_kwargs(candidate_radius_rearth=3.0, candidate_mass_mearth=20.0),
    )
    assert result.earth_similarity_score is not None
    assert result.earth_similarity_score < 90.0
    assert result.eligible is False


def test_insolation_out_of_range_not_eligible(scorer: L1EarthTwinScorer):
    # Çok parlak yıldız: L1 ışınımı 2.0 S_earth'ın üstüne çıkar
    result = scorer.evaluate("TIC 6", **_sun_earth_like_kwargs(stellar_luminosity_lsun=4.0))
    assert result.l1_insolation_s_earth is not None
    assert result.l1_insolation_s_earth > 2.0
    assert result.eligible is False


def test_stability_note_present(scorer: L1EarthTwinScorer):
    result = scorer.evaluate("TIC 7", **_sun_earth_like_kwargs())
    assert result.l1_stability_e_folding_days is not None
    assert 10.0 < result.l1_stability_e_folding_days < 60.0
    assert any("kararsız" in note for note in result.rationale)


def test_invalid_min_similarity_raises():
    with pytest.raises(ValueError):
        L1EarthTwinScorer(min_similarity=150.0)
