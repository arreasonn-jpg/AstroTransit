"""
Habitability scorer birim testleri.

Kapsam
------
- Yildiz parlaklik tahmini (Stefan-Boltzmann)
- Insolation cozumleme (flux, L/a^2)
- HZ skoru, temperate skoru, Dunya yaricap skoru
- HZ bolge siniflandirmasi
- Ana evaluate() akisi ve tum summary_label dallari
"""

from __future__ import annotations

import pytest

from astrotransit.quality.habitability import (
    HabitabilityAssessment,
    HabitabilityScorer,
)

# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def scorer() -> HabitabilityScorer:
    return HabitabilityScorer()


# ─────────────────────────────────────────────────────────────
# _estimate_luminosity
# ─────────────────────────────────────────────────────────────

def test_estimate_luminosity_sun(scorer: HabitabilityScorer) -> None:
    lum = scorer._estimate_luminosity(1.0, 5772.0)
    assert lum is not None
    assert lum == pytest.approx(1.0, abs=1e-6)


def test_estimate_luminosity_none_when_radius_missing(scorer) -> None:
    assert scorer._estimate_luminosity(None, 5772.0) is None


def test_estimate_luminosity_none_when_teff_missing(scorer) -> None:
    assert scorer._estimate_luminosity(1.0, None) is None


def test_estimate_luminosity_none_when_negative(scorer) -> None:
    assert scorer._estimate_luminosity(-1.0, 5772.0) is None
    assert scorer._estimate_luminosity(1.0, -100.0) is None


def test_estimate_luminosity_hot_star_brighter(scorer) -> None:
    lum_hot = scorer._estimate_luminosity(1.0, 8000.0)
    lum_cool = scorer._estimate_luminosity(1.0, 4000.0)
    assert lum_hot is not None
    assert lum_cool is not None
    assert lum_hot > lum_cool


# ─────────────────────────────────────────────────────────────
# _resolve_insolation
# ─────────────────────────────────────────────────────────────

def test_resolve_insolation_prefers_explicit_flux(scorer) -> None:
    s = scorer._resolve_insolation(insolation_flux=2.5, stellar_luminosity_lsun=1.0, semi_major_axis_au=1.0)
    assert s == pytest.approx(2.5)


def test_resolve_insolation_from_luminosity_and_axis(scorer) -> None:
    s = scorer._resolve_insolation(insolation_flux=None, stellar_luminosity_lsun=1.0, semi_major_axis_au=2.0)
    assert s is not None
    assert s == pytest.approx(0.25)


def test_resolve_insolation_ignores_nonpositive_flux(scorer) -> None:
    s = scorer._resolve_insolation(insolation_flux=0.0, stellar_luminosity_lsun=1.0, semi_major_axis_au=1.0)
    assert s == pytest.approx(1.0)


def test_resolve_insolation_returns_none_when_nothing_usable(scorer) -> None:
    assert scorer._resolve_insolation(None, None, None) is None
    assert scorer._resolve_insolation(None, 1.0, None) is None
    assert scorer._resolve_insolation(None, None, 1.0) is None
    assert scorer._resolve_insolation(None, -1.0, 1.0) is None
    assert scorer._resolve_insolation(None, 1.0, -1.0) is None


# ─────────────────────────────────────────────────────────────
# _compute_hz_score
# ─────────────────────────────────────────────────────────────

def test_hz_score_peaks_at_earth(scorer) -> None:
    score = scorer._compute_hz_score(1.0)
    assert score == pytest.approx(100.0, abs=0.1)


def test_hz_score_zero_for_invalid(scorer) -> None:
    assert scorer._compute_hz_score(None) == 0.0
    assert scorer._compute_hz_score(0.0) == 0.0
    assert scorer._compute_hz_score(-1.0) == 0.0


def test_hz_score_decays_away_from_earth(scorer) -> None:
    near = scorer._compute_hz_score(1.0)
    mid = scorer._compute_hz_score(0.1)
    far = scorer._compute_hz_score(0.001)
    assert near > mid > far
    assert far >= 0.0


# ─────────────────────────────────────────────────────────────
# _compute_temperate_score
# ─────────────────────────────────────────────────────────────

def test_temperate_score_both_inputs(scorer) -> None:
    score = scorer._compute_temperate_score(272.0, 1.0)
    assert 0.0 < score <= 100.0


def test_temperate_score_teff_only(scorer) -> None:
    score = scorer._compute_temperate_score(272.0, None)
    assert 0.0 < score <= 100.0


def test_temperate_score_insolation_only(scorer) -> None:
    score = scorer._compute_temperate_score(None, 1.0)
    assert 0.0 < score <= 100.0


def test_temperate_score_zero_when_no_inputs(scorer) -> None:
    assert scorer._compute_temperate_score(None, None) == 0.0


def test_temperate_score_ignores_nonpositive(scorer) -> None:
    assert scorer._compute_temperate_score(0.0, 0.0) == 0.0
    assert scorer._compute_temperate_score(-50.0, -1.0) == 0.0


# ─────────────────────────────────────────────────────────────
# _compute_earth_radius_score
# ─────────────────────────────────────────────────────────────

def test_earth_radius_score_peaks_at_one(scorer) -> None:
    score = scorer._compute_earth_radius_score(1.0)
    assert score == pytest.approx(100.0, abs=0.1)


def test_earth_radius_score_drops_for_giants(scorer) -> None:
    small = scorer._compute_earth_radius_score(1.2)
    giant = scorer._compute_earth_radius_score(3.0)
    assert small > giant
    assert giant >= 0.0


def test_earth_radius_score_zero_for_invalid(scorer) -> None:
    assert scorer._compute_earth_radius_score(None) == 0.0
    assert scorer._compute_earth_radius_score(0.0) == 0.0
    assert scorer._compute_earth_radius_score(-1.0) == 0.0


# ─────────────────────────────────────────────────────────────
# _classify_hz_zone
# ─────────────────────────────────────────────────────────────

def test_classify_conservative_hz(scorer) -> None:
    zone = scorer._classify_hz_zone(
        semi_major_axis_au=1.0,
        hz_inner_au=0.95,
        hz_outer_au=1.70,
        opt_inner_au=0.75,
        opt_outer_au=2.00,
        insolation_s_earth=None,
    )
    assert zone == "conservative_hz"


def test_classify_optimistic_hz(scorer) -> None:
    zone = scorer._classify_hz_zone(
        semi_major_axis_au=1.80,
        hz_inner_au=0.95,
        hz_outer_au=1.70,
        opt_inner_au=0.75,
        opt_outer_au=2.00,
        insolation_s_earth=None,
    )
    assert zone == "optimistic_hz"


def test_classify_too_hot(scorer) -> None:
    zone = scorer._classify_hz_zone(
        semi_major_axis_au=0.5,
        hz_inner_au=0.95,
        hz_outer_au=1.70,
        opt_inner_au=0.75,
        opt_outer_au=2.00,
        insolation_s_earth=None,
    )
    assert zone == "too_hot"


def test_classify_too_cold(scorer) -> None:
    zone = scorer._classify_hz_zone(
        semi_major_axis_au=5.0,
        hz_inner_au=0.95,
        hz_outer_au=1.70,
        opt_inner_au=0.75,
        opt_outer_au=2.00,
        insolation_s_earth=None,
    )
    assert zone == "too_cold"


def test_classify_falls_back_to_insolation(scorer) -> None:
    zone = scorer._classify_hz_zone(
        semi_major_axis_au=None,
        hz_inner_au=None,
        hz_outer_au=None,
        opt_inner_au=None,
        opt_outer_au=None,
        insolation_s_earth=1.0,
    )
    assert zone == "conservative_hz"


def test_classify_insolation_too_hot(scorer) -> None:
    zone = scorer._classify_hz_zone(None, None, None, None, None, insolation_s_earth=5.0)
    assert zone == "too_hot"


def test_classify_insolation_too_cold(scorer) -> None:
    zone = scorer._classify_hz_zone(None, None, None, None, None, insolation_s_earth=0.05)
    assert zone == "too_cold"


def test_classify_unknown(scorer) -> None:
    zone = scorer._classify_hz_zone(None, None, None, None, None, None)
    assert zone == "unknown"


# ─────────────────────────────────────────────────────────────
# evaluate() — ana akis
# ─────────────────────────────────────────────────────────────

def test_evaluate_earth_analog(scorer) -> None:
    """Sun + 1 R_earth + 1 AU: EARTHLIKE_TEMPERATE olmali."""
    result = scorer.evaluate(
        planet_radius_rearth=1.0,
        equilibrium_temperature_k=255.0,
        insolation_flux=1.0,
        semi_major_axis_au=1.0,
        stellar_radius_rsun=1.0,
        stellar_teff_k=5772.0,
    )
    assert isinstance(result, HabitabilityAssessment)
    assert result.summary_label == "EARTHLIKE_TEMPERATE"
    assert result.temperate_flag is True
    assert result.earthlike_flag is True
    assert result.hz_zone == "conservative_hz"
    assert result.earth_similarity_score > 70


def test_evaluate_temperate_small_world(scorer) -> None:
    """Temperate ama Earthlike degil (r=1.6)."""
    result = scorer.evaluate(
        planet_radius_rearth=1.6,
        equilibrium_temperature_k=250.0,
        insolation_flux=1.0,
        semi_major_axis_au=1.0,
    )
    assert result.temperate_flag is True
    assert result.earthlike_flag is False
    assert result.summary_label == "TEMPERATE_SMALL_WORLD"


def test_evaluate_temperate_nonterrestrial(scorer) -> None:
    """Temperate ama r>1.8."""
    result = scorer.evaluate(
        planet_radius_rearth=3.0,
        equilibrium_temperature_k=280.0,
        insolation_flux=1.5,
    )
    assert result.temperate_flag is True
    assert result.summary_label == "TEMPERATE_NONTERRESTRIAL"


def test_evaluate_hot_jupiter(scorer) -> None:
    result = scorer.evaluate(
        planet_radius_rearth=11.0,
        equilibrium_temperature_k=1500.0,
        insolation_flux=100.0,
        semi_major_axis_au=0.05,
    )
    assert result.temperate_flag is False
    assert result.summary_label == "NON_TEMPERATE"
    assert result.hz_zone == "too_hot"


def test_evaluate_cold_planet(scorer) -> None:
    result = scorer.evaluate(
        planet_radius_rearth=1.0,
        equilibrium_temperature_k=50.0,
        insolation_flux=0.01,
        semi_major_axis_au=10.0,
    )
    assert result.temperate_flag is False
    assert result.hz_zone == "too_cold"


def test_evaluate_no_inputs(scorer) -> None:
    result = scorer.evaluate()
    assert result.summary_label == "NON_TEMPERATE"
    assert result.hz_zone == "unknown"
    assert result.hz_score == 0.0
    assert result.temperate_score == 0.0
    assert result.earth_radius_score == 0.0
    assert result.earth_similarity_score == 0.0


def test_evaluate_stellar_only(scorer) -> None:
    """L ve S hesaplanabilir ama gezegen bilgisi yok."""
    result = scorer.evaluate(
        stellar_radius_rsun=1.0,
        stellar_teff_k=5772.0,
        semi_major_axis_au=1.0,
    )
    assert result.stellar_luminosity_lsun == pytest.approx(1.0, abs=1e-6)
    assert result.insolation_s_earth == pytest.approx(1.0, abs=1e-6)
    assert result.hz_inner_au is not None
    assert result.hz_outer_au is not None
    assert result.hz_zone == "conservative_hz"


def test_evaluate_assessment_to_dict(scorer) -> None:
    result = scorer.evaluate(
        planet_radius_rearth=1.0,
        insolation_flux=1.0,
        semi_major_axis_au=1.0,
        stellar_radius_rsun=1.0,
        stellar_teff_k=5772.0,
    )
    d = result.to_dict()
    assert isinstance(d, dict)
    assert "summary_label" in d
    assert "hz_score" in d
    assert "earth_similarity_score" in d
    assert isinstance(d["hz_score"], float)
    # round() ile 4 hane
    assert d["hz_score"] == round(d["hz_score"], 4)


def test_evaluate_hz_from_luminosity_and_axis(scorer) -> None:
    """S dogrudan verilmeden L/a^2 ile hesaplansin."""
    result = scorer.evaluate(
        planet_radius_rearth=1.0,
        semi_major_axis_au=1.0,
        stellar_radius_rsun=1.0,
        stellar_teff_k=5772.0,
    )
    assert result.insolation_s_earth == pytest.approx(1.0, abs=1e-6)


def test_evaluate_boundary_temperate_teff(scorer) -> None:
    """Tam sinirda T_eq=180K ve 330K temperate olmali."""
    low = scorer.evaluate(equilibrium_temperature_k=180.0)
    high = scorer.evaluate(equilibrium_temperature_k=330.0)
    assert low.temperate_flag is True
    assert high.temperate_flag is True


def test_evaluate_boundary_insolation(scorer) -> None:
    """Tam sinirda S=0.25 ve 2.0 temperate olmali."""
    low = scorer.evaluate(insolation_flux=0.25)
    high = scorer.evaluate(insolation_flux=2.0)
    assert low.temperate_flag is True
    assert high.temperate_flag is True
    assert scorer.evaluate(insolation_flux=0.1).temperate_flag is False
    assert scorer.evaluate(insolation_flux=5.0).temperate_flag is False


def test_evaluate_earthlike_requires_score(scorer) -> None:
    """earthlike_flag True ama skor < 70 ise EARTHLIKE_TEMPERATE olmamali."""
    result = scorer.evaluate(
        planet_radius_rearth=1.4,
        equilibrium_temperature_k=180.0,
        insolation_flux=0.3,
    )
    assert result.earthlike_flag is True
    assert result.summary_label != "EARTHLIKE_TEMPERATE"


def test_evaluate_logger_called(scorer) -> None:
    """En azindan init cagrisinin hata vermedigini dogrula."""
    scorer2 = HabitabilityScorer()
    assert scorer2 is not None
