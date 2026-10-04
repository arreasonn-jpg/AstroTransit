"""astrotransit/validation/followup.py ek testler (koşullar)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from astrotransit.validation.followup import (
    FOLLOWUP_OBSERVATION_TYPES,
    FollowupEvidence,
    FollowupValidationResult,
    _evidence_from_mapping,
    _evidence_from_object,
    coerce_followup_result,
    validate_followup_evidence,
)

# ═══════════════════════════════════════════════════════
# FollowupEvidence __post_init__
# ═══════════════════════════════════════════════════════

def test_evidence_valid():
    e = FollowupEvidence(
        source="JWST", observation_type="jwst_transit",
        observation_ids=("obs1",), confirmed=True,
    )
    assert e.source == "JWST"
    assert e.confirmed is True


def test_evidence_empty_source_raises():
    with pytest.raises(ValueError, match="source boş"):
        FollowupEvidence(source="", observation_type="jwst_transit")


def test_evidence_unknown_type_raises():
    with pytest.raises(ValueError, match="Bilinmeyen"):
        FollowupEvidence(source="X", observation_type="not_a_type")


def test_evidence_confirmed_requires_ids():
    with pytest.raises(ValueError, match="observation_id"):
        FollowupEvidence(source="X", observation_type="jwst_transit", confirmed=True)


def test_evidence_mass_invalid():
    with pytest.raises(ValueError, match="mass_mearth"):
        FollowupEvidence(
            source="X", observation_type="jwst_transit", mass_mearth=-1.0,
        )


def test_evidence_mass_inf():
    with pytest.raises(ValueError, match="mass_mearth"):
        FollowupEvidence(
            source="X", observation_type="jwst_transit", mass_mearth=float("inf"),
        )


def test_evidence_mass_err_negative():
    with pytest.raises(ValueError, match="mass_err_mearth"):
        FollowupEvidence(
            source="X", observation_type="jwst_transit", mass_err_mearth=-1.0,
        )


def test_evidence_fpp_out_of_range():
    with pytest.raises(ValueError, match="false_positive_probability"):
        FollowupEvidence(
            source="X", observation_type="jwst_transit",
            false_positive_probability=1.5,
        )


def test_evidence_to_dict():
    e = FollowupEvidence(
        source="JWST", observation_type="jwst_transit",
        observation_ids=("obs1",), confirmed=True, mass_mearth=10.0,
    )
    d = e.to_dict()
    assert d["source"] == "JWST"
    assert d["observation_ids"] == ["obs1"]
    assert d["mass_mearth"] == 10.0


def test_followup_observation_types_constant():
    assert "jwst_transit" in FOLLOWUP_OBSERVATION_TYPES
    assert "radial_velocity" in FOLLOWUP_OBSERVATION_TYPES


# ═══════════════════════════════════════════════════════
# FollowupValidationResult __post_init__
# ═══════════════════════════════════════════════════════

def test_validation_result_confirmed_requires_evidence():
    with pytest.raises(ValueError, match="confirmed"):
        FollowupValidationResult(confirmed=True)


def test_validation_result_status_followup_confirmed_requires_flag():
    with pytest.raises(ValueError, match="followup_confirmed"):
        FollowupValidationResult(status="followup_confirmed", confirmed=False)


def test_validation_result_to_dict():
    e = FollowupEvidence(
        source="X", observation_type="jwst_transit",
        observation_ids=("obs1",), confirmed=True,
    )
    r = FollowupValidationResult(
        target_id="TIC 1", confirmed=True, status="followup_confirmed",
        evidence=(e,), observation_ids=("obs1",),
    )
    d = r.to_dict()
    assert d["confirmed"] is True
    assert len(d["evidence"]) == 1


# ═══════════════════════════════════════════════════════
# validate_followup_evidence
# ═══════════════════════════════════════════════════════

def test_validate_empty_iterable():
    r = validate_followup_evidence([], target_id="X")
    assert r.confirmed is False
    assert r.status == "not_confirmed"


def test_validate_single_confirmed():
    e = FollowupEvidence(
        source="JWST", observation_type="jwst_transit",
        observation_ids=("obs1",), confirmed=True,
    )
    r = validate_followup_evidence(e, target_id="X")
    assert r.confirmed is True
    assert r.status == "followup_confirmed"
    assert r.evidence_quality == "confirmed_observation"


def test_validate_unconfirmed_evidence():
    e = FollowupEvidence(
        source="TESS", observation_type="archive_validation",
        observation_ids=("obs1",), confirmed=False,
    )
    r = validate_followup_evidence(e, target_id="X")
    assert r.confirmed is False
    assert r.status == "followup_evidence_only"
    assert r.evidence_quality == "unconfirmed_observation"


def test_validate_high_fpp_contradicts():
    e = FollowupEvidence(
        source="JWST", observation_type="jwst_transit",
        observation_ids=("obs1",), confirmed=True,
        false_positive_probability=0.9,
    )
    r = validate_followup_evidence(e, target_id="X")
    assert r.confirmed is False
    assert any("FPP" in n for n in r.notes)


def test_validate_multiple_evidence_mass_averaged():
    e1 = FollowupEvidence(
        source="RV1", observation_type="radial_velocity",
        observation_ids=("o1",), confirmed=True, mass_mearth=10.0,
    )
    e2 = FollowupEvidence(
        source="RV2", observation_type="radial_velocity",
        observation_ids=("o2",), confirmed=True, mass_mearth=20.0,
    )
    r = validate_followup_evidence((e1, e2))
    assert r.mass_mearth == pytest.approx(15.0)
    assert set(r.sources) == {"RV1", "RV2"}


def test_validate_mass_err_min():
    e1 = FollowupEvidence(
        source="X", observation_type="jwst_transit",
        observation_ids=("o1",), mass_err_mearth=5.0,
    )
    e2 = FollowupEvidence(
        source="X", observation_type="jwst_transit",
        observation_ids=("o2",), mass_err_mearth=2.0,
    )
    r = validate_followup_evidence((e1, e2))
    assert r.mass_err_mearth == 2.0


def test_validate_raises_on_non_evidence():
    with pytest.raises(TypeError, match="FollowupEvidence"):
        validate_followup_evidence(["not evidence"])  # type: ignore


def test_validate_atmosphere_and_life():
    e = FollowupEvidence(
        source="X", observation_type="atmospheric_spectroscopy",
        observation_ids=("o1",), confirmed=True,
        atmosphere_detected=True, life_detected=False,
    )
    r = validate_followup_evidence(e)
    assert r.atmosphere_detected is True
    assert r.life_detected is False


def test_validate_fpp_takes_min():
    e1 = FollowupEvidence(
        source="A", observation_type="jwst_transit",
        observation_ids=("o1",), false_positive_probability=0.1,
    )
    e2 = FollowupEvidence(
        source="B", observation_type="jwst_transit",
        observation_ids=("o2",), false_positive_probability=0.3,
    )
    r = validate_followup_evidence((e1, e2))
    assert r.false_positive_probability == 0.1


# ═══════════════════════════════════════════════════════
# coerce_followup_result
# ═══════════════════════════════════════════════════════

def test_coerce_none():
    r = coerce_followup_result(None, target_id="X")
    assert r.confirmed is False


def test_coerce_false():
    r = coerce_followup_result(False, target_id="X")
    assert r.confirmed is False


def test_coerce_passthrough_validation_result():
    v = FollowupValidationResult(target_id="X")
    assert coerce_followup_result(v) is v


def test_coerce_followup_evidence():
    e = FollowupEvidence(
        source="X", observation_type="jwst_transit",
        observation_ids=("o1",), confirmed=True,
    )
    r = coerce_followup_result(e, target_id="X")
    assert r.confirmed is True


def test_coerce_mapping_with_evidence():
    payload = {
        "evidence": {
            "source": "X", "observation_type": "jwst_transit",
            "observation_ids": ["o1"], "confirmed": True,
        },
        "target_id": "T1",
    }
    r = coerce_followup_result(payload)
    assert r.confirmed is True
    assert r.target_id == "T1"


def test_coerce_mapping_with_evidence_tuple():
    payload = {
        "evidence": [
            {"source": "X", "observation_type": "jwst_transit",
             "observation_ids": ["o1"], "confirmed": True},
        ],
    }
    r = coerce_followup_result(payload)
    assert r.confirmed is True


def test_coerce_mapping_with_source():
    payload = {
        "source": "X", "observation_type": "jwst_transit",
        "observation_ids": ["o1"],
    }
    r = coerce_followup_result(payload)
    assert r.confirmed is False  # confirmed değil


def test_coerce_mapping_legacy_confirmed_only():
    payload = {"confirmed": True, "target_id": "X"}
    r = coerce_followup_result(payload)
    assert r.status == "unvalidated_confirmation"


def test_coerce_mapping_empty():
    r = coerce_followup_result({}, target_id="X")
    assert r.confirmed is False


def test_coerce_object_with_source():
    obj = SimpleNamespace(
        source="JWST", observation_type="jwst_transit",
        observation_ids=("o1",), confirmed=True,
    )
    r = coerce_followup_result(obj)
    assert r.confirmed is True


def test_coerce_object_with_confirmed_only():
    obj = SimpleNamespace(confirmed=True)
    r = coerce_followup_result(obj)
    assert r.status == "unvalidated_confirmation"


def test_coerce_object_no_attrs():
    obj = SimpleNamespace()
    r = coerce_followup_result(obj)
    assert r.confirmed is False


# ═══════════════════════════════════════════════════════
# _evidence_from_mapping / _evidence_from_object
# ═══════════════════════════════════════════════════════

def test_evidence_from_mapping_string_id():
    e = _evidence_from_mapping({
        "source": "X", "observation_type": "jwst_transit",
        "observation_ids": "single",
    })
    assert e.observation_ids == ("single",)


def test_evidence_from_mapping_single_id_field():
    e = _evidence_from_mapping({
        "source": "X", "observation_type": "jwst_transit",
        "observation_id": "single",
    })
    assert e.observation_ids == ("single",)


def test_evidence_from_mapping_defaults():
    # source zorunlu; observation_type ve confirmed default alır
    e = _evidence_from_mapping({"source": "X"})
    assert e.observation_type == "archive_validation"
    assert e.confirmed is False


def test_evidence_from_mapping_empty_raises():
    with pytest.raises(ValueError, match="source"):
        _evidence_from_mapping({})


def test_evidence_from_object():
    obj = SimpleNamespace(
        source="X", observation_type="jwst_transit",
        observation_ids=("o1",), confirmed=True,
        mass_mearth=5.0,
    )
    e = _evidence_from_object(obj)
    assert e.source == "X"
    assert e.mass_mearth == 5.0
