"""
MoonHostScorer birim testleri.

Kapsam
------
- Gezegen kutle tahmini (parcali empirik baginti)
- Giant host, temperate host, Hill stability, cleanliness skorlari
- Hill sphere ve stable prograde zone hesabi
- Ana evaluate() akisi ve tum summary_label dallari
"""

from __future__ import annotations

import pytest

from astrotransit.quality.moon_potential import (
    MoonHostAssessment,
    MoonHostScorer,
)

# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def scorer() -> MoonHostScorer:
    return MoonHostScorer()


# ─────────────────────────────────────────────────────────────
# _estimate_planet_mass_mearth
# ─────────────────────────────────────────────────────────────

def test_mass_none_for_missing_radius(scorer: MoonHostScorer) -> None:
    assert scorer._estimate_planet_mass_mearth(None) is None


def test_mass_none_for_nonpositive_radius(scorer) -> None:
    assert scorer._estimate_planet_mass_mearth(0.0) is None
    assert scorer._estimate_planet_mass_mearth(-1.0) is None


def test_mass_terrestrial_regime(scorer) -> None:
    """r < 1.5: m = r^3.7."""
    m = scorer._estimate_planet_mass_mearth(1.0)
    assert m is not None
    assert m == pytest.approx(1.0, abs=1e-6)


def test_mass_neptunian_regime(scorer) -> None:
    """1.5 <= r < 4.0: m = 2.7 * r^1.3."""
    m = scorer._estimate_planet_mass_mearth(2.0)
    assert m is not None
    expected = 2.7 * (2.0 ** 1.3)
    assert m == pytest.approx(expected, rel=1e-6)


def test_mass_intermediate_regime(scorer) -> None:
    """4.0 <= r < 10.0: m = 17.0 * (r/3.88)."""
    m = scorer._estimate_planet_mass_mearth(5.0)
    assert m is not None
    expected = 17.0 * (5.0 / 3.88)
    assert m == pytest.approx(expected, rel=1e-6)


def test_mass_giant_regime(scorer) -> None:
    """r >= 10.0: m = 95.0 * (r/11.2)."""
    m = scorer._estimate_planet_mass_mearth(12.0)
    assert m is not None
    expected = 95.0 * (12.0 / 11.2)
    assert m == pytest.approx(expected, rel=1e-6)


def test_mass_clipped_to_upper_bound(scorer) -> None:
    """Cok buyuk radius ust sinir 1000'e kirpilmali."""
    m = scorer._estimate_planet_mass_mearth(1000.0)
    assert m is not None
    assert m <= 1000.0


def test_mass_clipped_to_lower_bound(scorer) -> None:
    """Cok kucuk radius alt sinir 0.1'e kirpilmali."""
    m = scorer._estimate_planet_mass_mearth(0.01)
    assert m is not None
    assert m >= 0.1


# ─────────────────────────────────────────────────────────────
# _compute_giant_host_score
# ─────────────────────────────────────────────────────────────

def test_giant_score_none(scorer) -> None:
    assert scorer._compute_giant_host_score(None) == 0.0


def test_giant_score_nonpositive(scorer) -> None:
    assert scorer._compute_giant_host_score(0.0) == 0.0
    assert scorer._compute_giant_host_score(-1.0) == 0.0


def test_giant_score_too_small(scorer) -> None:
    assert scorer._compute_giant_host_score(1.0) == 0.0
    assert scorer._compute_giant_host_score(2.4) == 0.0


def test_giant_score_sub_neptune(scorer) -> None:
    assert scorer._compute_giant_host_score(3.0) == 35.0


def test_giant_score_neptune(scorer) -> None:
    assert scorer._compute_giant_host_score(5.0) == 70.0


def test_giant_score_jupiter(scorer) -> None:
    assert scorer._compute_giant_host_score(11.0) == 100.0


def test_giant_score_beyond_jupiter(scorer) -> None:
    assert scorer._compute_giant_host_score(15.0) == 85.0


# ─────────────────────────────────────────────────────────────
# _compute_temperate_host_score
# ─────────────────────────────────────────────────────────────

def test_temperate_host_both_inputs(scorer) -> None:
    s = scorer._compute_temperate_host_score(260.0, 1.0)
    assert 0.0 < s <= 100.0


def test_temperate_host_teff_only(scorer) -> None:
    s = scorer._compute_temperate_host_score(260.0, None)
    assert 0.0 < s <= 100.0


def test_temperate_host_insolation_only(scorer) -> None:
    s = scorer._compute_temperate_host_score(None, 1.0)
    assert 0.0 < s <= 100.0


def test_temperate_host_none(scorer) -> None:
    assert scorer._compute_temperate_host_score(None, None) == 0.0


def test_temperate_host_ignores_nonpositive(scorer) -> None:
    assert scorer._compute_temperate_host_score(0.0, 0.0) == 0.0
    assert scorer._compute_temperate_host_score(-10.0, -1.0) == 0.0


# ─────────────────────────────────────────────────────────────
# _compute_hill_stability_score
# ─────────────────────────────────────────────────────────────

def test_hill_stability_none(scorer) -> None:
    assert scorer._compute_hill_stability_score(None) == 0.0


def test_hill_stability_nonpositive(scorer) -> None:
    assert scorer._compute_hill_stability_score(0.0) == 0.0
    assert scorer._compute_hill_stability_score(-5.0) == 0.0


def test_hill_stability_tiny(scorer) -> None:
    assert scorer._compute_hill_stability_score(5.0) == 5.0


def test_hill_stability_small(scorer) -> None:
    assert scorer._compute_hill_stability_score(15.0) == 20.0


def test_hill_stability_medium(scorer) -> None:
    assert scorer._compute_hill_stability_score(30.0) == 45.0


def test_hill_stability_large(scorer) -> None:
    assert scorer._compute_hill_stability_score(60.0) == 75.0


def test_hill_stability_huge(scorer) -> None:
    assert scorer._compute_hill_stability_score(150.0) == 100.0


# ─────────────────────────────────────────────────────────────
# _compute_cleanliness_bonus
# ─────────────────────────────────────────────────────────────

def test_cleanliness_none(scorer) -> None:
    assert scorer._compute_cleanliness_bonus(None) == 0.0


def test_cleanliness_nonpositive(scorer) -> None:
    assert scorer._compute_cleanliness_bonus(0.0) == 0.0
    assert scorer._compute_cleanliness_bonus(-0.1) == 0.0


def test_cleanliness_high_crowding(scorer) -> None:
    assert scorer._compute_cleanliness_bonus(0.5) == 0.0


def test_cleanliness_moderate(scorer) -> None:
    assert scorer._compute_cleanliness_bonus(0.85) == 35.0


def test_cleanliness_low(scorer) -> None:
    assert scorer._compute_cleanliness_bonus(0.93) == 70.0


def test_cleanliness_clean(scorer) -> None:
    assert scorer._compute_cleanliness_bonus(0.99) == 100.0


# ─────────────────────────────────────────────────────────────
# evaluate() — ana akis
# ─────────────────────────────────────────────────────────────

def test_evaluate_no_inputs(scorer) -> None:
    result = scorer.evaluate()
    assert isinstance(result, MoonHostAssessment)
    assert result.estimated_planet_mass_mearth is None
    assert result.hill_radius_au is None
    assert result.stable_prograde_zone_au is None
    assert result.summary_label == "STANDARD_PLANET"
    assert result.moon_host_flag is False


def test_evaluate_small_planet_only(scorer) -> None:
    result = scorer.evaluate(planet_radius_rearth=1.0)
    assert result.estimated_planet_mass_mearth is not None
    assert result.hill_radius_au is None
    assert result.giant_host_score == 0.0
    assert result.summary_label == "STANDARD_PLANET"


def test_evaluate_giant_world_label(scorer) -> None:
    """Sadece buyuk radius → GIANT_WORLD."""
    result = scorer.evaluate(planet_radius_rearth=11.0)
    assert result.giant_host_score == 100.0
    assert result.moon_host_flag is False
    assert result.summary_label == "GIANT_WORLD"


def test_evaluate_full_inputs_hill_radius(scorer) -> None:
    """Tum girdilerle Hill sphere hesabi yapilmali."""
    result = scorer.evaluate(
        planet_radius_rearth=11.0,
        stellar_mass_msun=1.0,
        semi_major_axis_au=5.2,
        equilibrium_temperature_k=125.0,
        insolation_flux=0.04,
    )
    assert result.estimated_planet_mass_mearth is not None
    assert result.hill_radius_au is not None
    assert result.hill_radius_au > 0
    assert result.stable_prograde_zone_au is not None
    # stable zone = 0.49 * hill radius
    assert result.stable_prograde_zone_au == pytest.approx(
        0.49 * result.hill_radius_au, rel=1e-6
    )


def test_evaluate_stable_zone_in_planet_radii(scorer) -> None:
    """stable_zone_rp = stable_zone_au / rp_au."""
    result = scorer.evaluate(
        planet_radius_rearth=11.0,
        stellar_mass_msun=1.0,
        semi_major_axis_au=5.2,
    )
    assert result.stable_prograde_zone_planet_radii is not None
    assert result.stable_prograde_zone_planet_radii > 0


def test_evaluate_hill_skipped_without_stellar_mass(scorer) -> None:
    """Stellar mass yoksa Hill hesabi atlanmali."""
    result = scorer.evaluate(
        planet_radius_rearth=11.0,
        semi_major_axis_au=5.2,
    )
    assert result.hill_radius_au is None
    assert result.stable_prograde_zone_au is None


def test_evaluate_hill_skipped_without_axis(scorer) -> None:
    """Semi-major axis yoksa Hill hesabi atlanmali."""
    result = scorer.evaluate(
        planet_radius_rearth=11.0,
        stellar_mass_msun=1.0,
    )
    assert result.hill_radius_au is None


def test_evaluate_hill_skipped_for_tiny_planet(scorer) -> None:
    """Cok kucuk gezegen kutlesi 0'dan buyuk olsa da Hill hesaplanabilir."""
    result = scorer.evaluate(
        planet_radius_rearth=0.5,
        stellar_mass_msun=1.0,
        semi_major_axis_au=1.0,
    )
    # kucuk gezegen icin hill radius cok kucuk
    assert result.hill_radius_au is not None
    assert result.hill_radius_au < 0.01


def test_evaluate_potential_habitable_moon_host(scorer) -> None:
    """Buyuk gezegen + temperate + genis Hill + temiz cevre."""
    # Jüpiter benzeri, L4/L5 civari, bolgesel temiz
    result = scorer.evaluate(
        planet_radius_rearth=11.0,
        stellar_mass_msun=1.0,
        semi_major_axis_au=1.5,
        equilibrium_temperature_k=250.0,
        insolation_flux=0.6,
        crowding_ratio=0.99,
    )
    assert result.moon_host_flag is True
    assert result.temperate_host_score >= 60
    assert result.summary_label == "POTENTIAL_HABITABLE_MOON_HOST"


def test_evaluate_potential_moon_host_no_temperate(scorer) -> None:
    """Buyuk gezegen + genis Hill ama sicak → POTENTIAL_MOON_HOST.

    semi_major_axis genis (hill_stability yuksek) ve temiz cevre
    (cleanliness=100) secildi. Sicaklik/insolasyon yuksek oldugu icin
    temperate_host_score < 60 kalmali ve label POTENTIAL_MOON_HOST olmali.
    """
    result = scorer.evaluate(
        planet_radius_rearth=11.0,
        stellar_mass_msun=1.0,
        semi_major_axis_au=2.0,
        equilibrium_temperature_k=1500.0,
        insolation_flux=100.0,
        crowding_ratio=0.99,
    )
    assert result.moon_host_flag is True
    assert result.temperate_host_score < 60
    assert result.summary_label == "POTENTIAL_MOON_HOST"


def test_evaluate_giant_but_unstable_hill(scorer) -> None:
    """Buyuk gezegen ama dar Hill → GIANT_WORLD."""
    # Cok yakin yorunge, kucuk Hill
    result = scorer.evaluate(
        planet_radius_rearth=11.0,
        stellar_mass_msun=0.1,
        semi_major_axis_au=0.01,
    )
    assert result.giant_host_score == 100.0
    assert result.moon_host_flag is False
    assert result.summary_label == "GIANT_WORLD"


def test_evaluate_score_decomposition(scorer) -> None:
    """moon_host_score agirlikli ortalama olmali."""
    result = scorer.evaluate(
        planet_radius_rearth=11.0,
        stellar_mass_msun=1.0,
        semi_major_axis_au=1.5,
        equilibrium_temperature_k=250.0,
        insolation_flux=0.6,
        crowding_ratio=0.99,
    )
    expected = (
        0.40 * result.giant_host_score
        + 0.30 * result.temperate_host_score
        + 0.25 * result.hill_stability_score
        + 0.05 * scorer._compute_cleanliness_bonus(0.99)
    )
    assert result.moon_host_score == pytest.approx(expected, rel=1e-6)


def test_evaluate_assessment_to_dict(scorer) -> None:
    result = scorer.evaluate(
        planet_radius_rearth=11.0,
        stellar_mass_msun=1.0,
        semi_major_axis_au=1.5,
    )
    d = result.to_dict()
    assert isinstance(d, dict)
    assert "moon_host_score" in d
    assert "summary_label" in d
    assert isinstance(d["moon_host_score"], float)
    assert d["moon_host_score"] == round(d["moon_host_score"], 4)


def test_evaluate_zero_radius_returns_none_mass(scorer) -> None:
    result = scorer.evaluate(planet_radius_rearth=0.0)
    assert result.estimated_planet_mass_mearth is None


def test_evaluate_negative_radius(scorer) -> None:
    result = scorer.evaluate(planet_radius_rearth=-1.0)
    assert result.estimated_planet_mass_mearth is None
    assert result.giant_host_score == 0.0


def test_evaluate_crowding_only_no_planet(scorer) -> None:
    """Crowding verildi ama gezegen yok → STANDARD."""
    result = scorer.evaluate(crowding_ratio=0.99)
    assert result.summary_label == "STANDARD_PLANET"
