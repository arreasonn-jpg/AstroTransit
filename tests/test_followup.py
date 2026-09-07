"""Takip gözlemi doğrulama sözleşmesi testleri."""

import pytest

from astrotransit.data.catalog_client import StellarProperties
from astrotransit.outputs.schemas import build_record
from astrotransit.validation.followup import (
    FollowupEvidence,
    coerce_followup_result,
    validate_followup_evidence,
)


def test_confirmed_followup_requires_observation_id():
    with pytest.raises(ValueError):
        FollowupEvidence(
            source="RV campaign",
            observation_type="radial_velocity",
            confirmed=True,
        )


def test_followup_result_does_not_infer_confirmation_from_bare_flag():
    result = coerce_followup_result({"confirmed": True}, target_id="TIC 1")

    assert result.confirmed is False
    assert result.status == "unvalidated_confirmation"


def test_build_record_does_not_accept_bare_followup_confirmation():
    record = build_record(
        candidate={
            "target_id": "TIC 1",
            "period": 365.25,
            "rp_rs": 0.0092,
            "depth": 0.000085,
            "duration": 0.5,
            "confirmed": True,
        },
        stellar_props=StellarProperties(teff=5778.0, radius=1.0, mass=1.0),
        earth_similarity_profile="strict_earth_twin",
        followup_result={"confirmed": True},
    )

    assert record.followup_confirmed is False
    assert record.followup_status == "unvalidated_confirmation"
    assert record.earth_analog_class != "CONFIRMED_EARTH_TWIN"


def test_valid_followup_evidence_carries_mass_and_fpp():
    result = validate_followup_evidence(
        FollowupEvidence(
            source="RV campaign",
            observation_type="radial_velocity",
            observation_ids=("rv-001", "rv-002"),
            confirmed=True,
            mass_mearth=1.05,
            mass_err_mearth=0.12,
            false_positive_probability=0.01,
        ),
        target_id="TIC 1",
    )

    assert result.confirmed is True
    assert result.status == "followup_confirmed"
    assert result.mass_mearth == 1.05
    assert result.sources == ("RV campaign",)
    assert result.false_positive_probability == 0.01


def test_high_fpp_blocks_followup_confirmation():
    result = validate_followup_evidence(
        FollowupEvidence(
            source="ground-based transit",
            observation_type="additional_transit",
            observation_ids=("ground-001",),
            confirmed=True,
            false_positive_probability=0.8,
        )
    )

    assert result.confirmed is False
    assert result.status == "followup_evidence_only"


def test_followup_mass_can_complete_strict_similarity_without_defaulting():
    candidate = {
        "target_id": "TIC 123",
        "sector": 14,
        "period": 365.25,
        "period_err": 0.1,
        "t0": 1.0,
        "rp_rs": 0.0092,
        "depth": 0.000085,
        "duration": 0.5,
        "confirmed": True,
        "transit_times": [],
    }
    followup = FollowupEvidence(
        source="RV campaign",
        observation_type="radial_velocity",
        observation_ids=("rv-001",),
        confirmed=True,
        mass_mearth=1.0,
    )
    record = build_record(
        candidate=candidate,
        stellar_props=StellarProperties(teff=5778.0, radius=1.0, mass=1.0),
        earth_similarity_profile="strict_earth_twin",
        followup_result=followup,
    )

    assert record.planet_mass_mearth == 1.0
    assert record.followup_confirmed is True
    assert record.followup_status == "followup_confirmed"
    assert record.followup_sources == '["RV campaign"]'
    assert record.earth_analog_class == "CONFIRMED_EARTH_TWIN"
    assert record.to_nested_dict()["followup"]["observation_ids"] == ["rv-001"]
