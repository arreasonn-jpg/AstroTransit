"""analyze_blind_holdout_failures triyaj testleri.

Gerçek rows shard'ları repo'da (blinding gereği) yok; sentetik satırlarla
taksonomi kontratını doğrular.
"""

from __future__ import annotations

import pytest

from scripts.validation.analyze_blind_holdout_failures import (
    FAILURE_MODES,
    analyze,
    classify_row,
)


def _sector(**overrides) -> dict:
    base = {
        "sector": 14,
        "success": True,
        "has_candidate": True,
        "candidate_confirmed": False,
        "vetting_fp_flags": [],
        "vetting_tests": [],
    }
    return {**base, **overrides}


def _row(**overrides) -> dict:
    base = {
        "target_id": "TIC 123",
        "label": "planet",
        "error": "",
        "requested_sectors": [14],
        "successful_sector_count": 1,
        "accepted_candidate": None,
        "per_sector": [_sector()],
    }
    return {**base, **overrides}


def test_taxonomy_constant_is_stable():
    assert FAILURE_MODES == (
        "data_error",
        "no_sector",
        "no_data",
        "no_candidate",
        "vetoed",
        "accepted",
        "fp_leak",
    )


def test_classify_error_and_sector_modes():
    row = _row(error="TimeoutError: time limit exceeded")
    assert classify_row(row) == "data_error"

    row2 = _row(error="", requested_sectors=[])
    assert classify_row(row2) == "no_sector"

    row3 = _row(error="sector_lookup_failed:HttpError: 503")
    assert classify_row(row3) == "no_sector"


def test_classify_no_data_no_candidate_vetoed_accepted():
    assert classify_row(_row(accepted_candidate=False, successful_sector_count=0)) == "no_data"
    assert classify_row(_row(accepted_candidate=False, per_sector=[_sector(has_candidate=False)])) == "no_candidate"
    assert classify_row(_row(accepted_candidate=False, per_sector=[_sector(candidate_confirmed=True)])) == "vetoed"
    assert classify_row(_row(accepted_candidate=True)) == "accepted"


def test_classify_fp_leak_and_bad_rows():
    assert classify_row(_row(label="false_positive", accepted_candidate=True)) == "fp_leak"
    # accepted_candidate None ve hata yok → artefakt/mimari sorunu = data_error
    assert classify_row(_row(accepted_candidate=None, successful_sector_count=2)) == "data_error"


def test_analyze_counts_flags_and_tests():
    vetted = _row(
        accepted_candidate=False,
        per_sector=[_sector(candidate_confirmed=True, vetting_fp_flags=["EB:flag_a"], vetting_tests=[
            {"name": "odd_even", "verdict": "fail", "value": 0.9, "threshold": 0.1},
        ])],
    )
    leak = _row(
        label="false_positive",
        accepted_candidate=True,
        per_sector=[_sector(vetting_fp_flags=["NEB:flag_b"], vetting_tests=[
            {"name": "snr", "verdict": "warn", "value": 4.0, "threshold": 7.0},
        ])],
    )
    verdict = analyze([_row(error="HttpError: download"), _row(accepted_candidate=True), vetted, leak])
    assert verdict["n_rows"] == 4
    assert verdict["modes"]["accepted"] == 1
    assert verdict["modes"]["data_error"] == 1
    assert verdict["modes"]["vetoed"] == 1
    assert verdict["modes"]["fp_leak"] == 1
    assert verdict["error_prefixes"]["HttpError"] == 1
    assert verdict["veto_flag_counts"]["EB:flag_a"] == 1
    assert verdict["fp_leak_flag_counts"]["NEB:flag_b"] == 1
    assert verdict["vetting_test_verdicts"]["planet"]["odd_even:fail"] == 1
    assert verdict["vetting_test_verdicts"]["false_positive"]["snr:warn"] == 1


def test_analyze_rejects_empty():
    with pytest.raises(ValueError, match="rows boş"):
        analyze([])
