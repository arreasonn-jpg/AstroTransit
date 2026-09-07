"""Dünya-benzerlik profili testleri."""

from types import SimpleNamespace

from astrotransit.data.catalog_client import StellarProperties
from astrotransit.modeling.parameters import DerivedParameters
from astrotransit.outputs.schemas import build_record
from astrotransit.science.earth_similarity import score_earth_similarity


def test_strict_profile_requires_mass_and_host_temperature():
    result = score_earth_similarity(
        "strict_earth_twin",
        planet_radius_rearth=1.0,
        insolation_s_earth=1.0,
        semi_major_axis_au=1.0,
    )

    assert result.score == 100.0
    assert result.classification == "INCOMPLETE_EARTH_TWIN"
    assert result.missing_required_dimensions == (
        "equilibrium_temperature",
        "mass",
        "host_teff",
    )
    assert result.components["mass"].value is None
    assert result.components["mass"].available is False


def test_strict_profile_can_produce_earth_twin_candidate():
    result = score_earth_similarity(
        "strict_earth_twin",
        planet_radius_rearth=1.0,
        insolation_s_earth=1.0,
        equilibrium_temperature_k=255.0,
        planet_mass_mearth=1.0,
        semi_major_axis_au=1.0,
        stellar_teff_k=5778.0,
    )

    assert result.classification == "EARTH_TWIN_CANDIDATE"
    assert result.score_p50 == 100.0
    assert result.measurement_completeness > 0.8


def test_sampled_scores_expose_uncertainty():
    result = score_earth_similarity(
        "photometric_earth_analog",
        samples={
            "radius": [0.9, 1.0, 1.1],
            "insolation": [0.9, 1.0, 1.1],
        },
    )

    assert result.uncertainty_available is True
    assert result.score_p05 <= result.score_p50 <= result.score_p95


def _earth_like_candidate():
    return SimpleNamespace(
        target_id="TIC 123456789",
        sector=14,
        period=365.25,
        period_err=0.1,
        t0=1.0,
        rp_rs=0.0092,
        depth=0.000085,
        duration=0.5,
        confirmed=True,
        status="CONFIRMED",
        transit_times=[],
    )


def _solar_stellar():
    return StellarProperties(
        tic_id=123456789,
        teff=5778.0,
        radius=1.0,
        mass=1.0,
    )


def test_build_record_persists_similarity_fields():
    record = build_record(
        candidate=_earth_like_candidate(),
        stellar_props=_solar_stellar(),
        earth_similarity_profile="photometric_earth_analog",
    )

    assert record.earth_similarity_profile == "photometric_earth_analog"
    assert record.earth_similarity_score is not None
    assert record.earth_analog_class == "PHOTOMETRIC_EARTH_ANALOG"
    assert record.planet_mass_mearth is None
    assert record.mass_status == "unavailable"
    assert record.detection_confidence == "UNKNOWN"
    nested = record.to_nested_dict()
    assert "earth_similarity" in nested
    assert nested["earth_similarity"]["missing_required_dimensions"] == []


def test_followup_confirmation_is_separate_from_cascade_confirmation():
    derived = DerivedParameters(
        planet_radius_rearth=1.0,
        semi_major_axis_au=1.0,
        equilibrium_temperature_k=255.0,
        insolation_flux=1.0,
    )
    fit = SimpleNamespace(
        success=True,
        fit_method="map",
        period=365.25,
        period_err=0.1,
        t0=1.0,
        rp_rs=0.0092,
        planet_mass_mearth=1.0,
        derived=derived,
    )
    quality = SimpleNamespace(
        fpp_report=SimpleNamespace(fpp=0.02, confidence="HIGH"),
    )

    record = build_record(
        candidate=_earth_like_candidate(),
        fit_result=fit,
        quality_result=quality,
        stellar_props=_solar_stellar(),
        earth_similarity_profile="strict_earth_twin",
        followup_result={"confirmed": True},
    )

    assert record.cascade_confirmed is True
    assert record.earth_analog_class == "CONFIRMED_EARTH_TWIN"
    assert record.earth_twin_status == "confirmed_earth_twin"
    assert record.detection_confidence == "HIGH"
    assert record.false_positive_probability == 0.02
