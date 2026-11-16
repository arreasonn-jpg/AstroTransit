"""L1 claim firewall (l1_claims) testleri."""

from __future__ import annotations

import pytest

from astrotransit.validation.l1_claims import (
    L1ClaimEvidenceError,
    L1ClaimLabel,
    infer_l1_claim,
    validate_l1_claim,
)


def test_no_assessment_returns_base_label():
    assert infer_l1_claim({"l1_assessed": False}) == L1ClaimLabel.L1_REGION_ASSESSED


def test_kol2_controlled_requires_review_and_budget():
    result = {
        "l1_assessed": True,
        "l1_stationkeeping_review_score": 85.0,
        "station_keeping_budget_ok": True,
    }
    assert infer_l1_claim(result) == L1ClaimLabel.L1_CONTROLLED_STRUCTURE_CANDIDATE


def test_kol2_review_without_budget_is_only_review():
    result = {
        "l1_assessed": True,
        "l1_stationkeeping_review_score": 85.0,
        "station_keeping_budget_ok": False,
    }
    assert infer_l1_claim(result) == L1ClaimLabel.L1_STATIONKEEPING_REVIEW


def test_kol2_low_review_not_controlled():
    result = {
        "l1_assessed": True,
        "l1_stationkeeping_review_score": 40.0,
        "station_keeping_budget_ok": True,
    }
    assert infer_l1_claim(result) == L1ClaimLabel.L1_REGION_ASSESSED


def test_kol1_habitable_region_candidate():
    result = {
        "l1_assessed": True,
        "host_in_habitable_zone": True,
        "l1_insolation_in_habitable_range": True,
        "earth_similarity_score": 95.0,
        "l1_min_similarity": 90.0,
    }
    assert infer_l1_claim(result) == L1ClaimLabel.L1_HABITABLE_REGION_CANDIDATE


def test_kol1_host_not_hz_blocks_habitable_label():
    result = {
        "l1_assessed": True,
        "host_in_habitable_zone": False,
        "l1_insolation_in_habitable_range": True,
        "earth_similarity_score": 95.0,
    }
    assert infer_l1_claim(result) == L1ClaimLabel.L1_REGION_ASSESSED


def test_kol1_low_similarity_blocks_habitable_label():
    result = {
        "l1_assessed": True,
        "host_in_habitable_zone": True,
        "l1_insolation_in_habitable_range": True,
        "earth_similarity_score": 60.0,
        "l1_min_similarity": 90.0,
    }
    assert infer_l1_claim(result) == L1ClaimLabel.L1_REGION_ASSESSED


def test_validate_accepts_supported_label():
    result = {
        "l1_assessed": True,
        "l1_stationkeeping_review_score": 85.0,
        "station_keeping_budget_ok": True,
    }
    assert validate_l1_claim(result, "L1_CONTROLLED_STRUCTURE_CANDIDATE") == L1ClaimLabel.L1_CONTROLLED_STRUCTURE_CANDIDATE
    assert validate_l1_claim(result, "L1_REGION_ASSESSED") == L1ClaimLabel.L1_REGION_ASSESSED


def test_validate_rejects_unsupported_stronger_label():
    result = {"l1_assessed": True, "l1_stationkeeping_review_score": 40.0}
    with pytest.raises(L1ClaimEvidenceError):
        validate_l1_claim(result, "L1_CONTROLLED_STRUCTURE_CANDIDATE")


def test_validate_rejects_habitable_label_without_hz():
    result = {
        "l1_assessed": True,
        "host_in_habitable_zone": None,
        "l1_insolation_in_habitable_range": True,
        "earth_similarity_score": 95.0,
    }
    with pytest.raises(L1ClaimEvidenceError):
        validate_l1_claim(result, "L1_HABITABLE_REGION_CANDIDATE")


def test_never_infers_control_from_presence_alone():
    # "L1'de görüldü" ancak review skoru yoksa hiçbir Kol 2 etiketi üretilmez
    result = {"l1_assessed": True, "l1_stationkeeping_review_score": None}
    assert infer_l1_claim(result) == L1ClaimLabel.L1_REGION_ASSESSED
