"""FPP telemetri çıkarımının sözleşme testleri.

Kritik olan tek şey yokluğun sıfıra dönüşmemesidir: ``None`` bir FPP değeri
asla ``0.0`` olarak kalibre edilmez, nedeni birlikte taşınır.
"""

from __future__ import annotations

import pytest

from astrotransit.validation.fpp_calibration import build_fpp_calibration_report
from astrotransit.validation.fpp_telemetry import (
    FPP_REASONS,
    FPP_TELEMETRY_VERSION,
    adopt_target_fpp,
    attach_row_fpp,
    finite_unit_interval,
    read_row_fpp,
    sector_fpp_telemetry,
)


class _SectorResult:
    def __init__(self, sector, record=None, candidate_confirmed=False):
        self.sector = sector
        self.record = record
        self.candidate_confirmed = candidate_confirmed


class _Record:
    def __init__(self, **values):
        self.__dict__.update(values)


def _record(fpp=0.42, **overrides):
    values = {
        "false_positive_probability": fpp,
        "fpp": fpp,
        "fpp_method": "heuristic_vetting_weighted_vote",
        "detection_confidence": "MEDIUM",
        "claim_status": "DETECTED",
        "candidate_class": "CANDIDATE",
        "flags": "EB_LIKE, SECONDARY_ECLIPSE",
        "is_false_positive": False,
        "total_score": 61.5,
        "sector": 14,
    }
    values.update(overrides)
    return _Record(**values)


def test_finite_unit_interval_rejects_nonfinite_and_out_of_range():
    assert finite_unit_interval(0.5) == 0.5
    assert finite_unit_interval(None) is None
    assert finite_unit_interval(float("nan")) is None
    assert finite_unit_interval(float("inf")) is None
    assert finite_unit_interval(1.7) is None
    assert finite_unit_interval("0.25") == 0.25


def test_record_without_fpp_stays_missing_not_zero():
    telemetry = sector_fpp_telemetry(_SectorResult(3, _record(fpp=None, false_positive_probability=None)))
    assert telemetry["fpp"] is None
    assert telemetry["fpp_available"] is False
    assert telemetry["fpp_availability_reason"] == "fpp_null"
    assert telemetry["flags"] == ["EB_LIKE", "SECONDARY_ECLIPSE"]
    assert telemetry["total_score"] == 61.5
    assert telemetry["claim_status"] == "DETECTED"


def test_out_of_range_fpp_is_dropped_with_reason():
    telemetry = sector_fpp_telemetry(_SectorResult(3, _record(fpp=1.7, false_positive_probability=1.7)))
    assert telemetry["fpp"] is None
    assert telemetry["fpp_availability_reason"] == "fpp_out_of_range"


def test_sector_without_record_has_no_candidate_reason():
    telemetry = sector_fpp_telemetry(_SectorResult(7, None))
    assert telemetry["fpp_availability_reason"] == "no_candidate_record"
    assert telemetry["fpp_available"] is False


def test_adoption_prefers_highest_score_then_lowest_sector():
    rows = [
        {"sector": 22, "fpp": 0.7, "fpp_available": True, "total_score": 55.0, "accepted": True},
        {"sector": 4, "fpp": 0.9, "fpp_available": True, "total_score": 55.0, "accepted": False},
        {"sector": 9, "fpp": 0.1, "fpp_available": True, "total_score": 90.0, "accepted": False},
    ]
    adopted = adopt_target_fpp(rows)
    assert adopted["fpp"] == 0.1
    assert adopted["fpp_source_sector"] == 9
    assert adopted["fpp_availability_reason"] == "ok"
    assert len(adopted["fpp_observations"]) == 3


def test_adoption_of_empty_telemetry_reports_absence():
    adopted = adopt_target_fpp([])
    assert adopted["fpp"] is None
    assert adopted["fpp_availability_reason"] == "telemetry_absent"
    assert adopted["fpp_available"] is False


def test_adoption_reason_distinguishes_no_candidate_from_unscored():
    only_missing = adopt_target_fpp(
        [{"sector": 1, "fpp": None, "fpp_available": False, "fpp_availability_reason": "fpp_null", "total_score": None}]
    )
    assert only_missing["fpp_availability_reason"] == "fpp_null"
    no_candidate = adopt_target_fpp(
        [
            {
                "sector": 1,
                "fpp": None,
                "fpp_available": False,
                "fpp_availability_reason": "no_candidate_record",
                "total_score": None,
            }
        ]
    )
    assert no_candidate["fpp_availability_reason"] == "no_candidate_record"


def test_attach_row_fpp_adds_target_fields_and_version():
    row = {
        "target_id": "TIC 12",
        "label": "false_positive",
        "evaluated": True,
        "accepted_candidate": True,
        "error": "",
        "sector_results": [_SectorResult(14, _record(fpp=0.8))],
    }
    updated = attach_row_fpp(row)
    assert updated["fpp_telemetry_version"] == FPP_TELEMETRY_VERSION
    assert updated["target_fpp"] == 0.8
    assert updated["target_fpp_availability_reason"] == "ok"
    assert updated["target_fpp_method"] == "heuristic_vetting_weighted_vote"
    # Orijinal satır mutasyon geçirmemeli.
    assert "target_fpp" not in row
    assert isinstance(updated["sector_results"][0], dict)


def test_attach_row_fpp_marks_unevaluated_rows():
    row = {
        "target_id": "TIC 13",
        "label": "planet",
        "evaluated": False,
        "accepted_candidate": None,
        "error": "TESSDataError: no data",
        "sector_results": [],
    }
    updated = attach_row_fpp(row)
    assert updated["target_fpp"] is None
    assert updated["target_fpp_availability_reason"] == "not_evaluated"
    value, _method, reason = read_row_fpp(updated)
    assert value is None and reason == "not_evaluated"


def test_read_row_fpp_quiet_controls_are_not_calibration_labels():
    row = {
        "target_id": "TIC 14",
        "label": "quiet_star",
        "target_fpp_available": True,
        "target_fpp": 0.9,
        "target_fpp_availability_reason": "ok",
    }
    value, _method, reason = read_row_fpp(row)
    assert value is None
    assert reason == "label_outside_calibration_set"


def test_read_row_fpp_accepts_legacy_flat_predictions():
    value, method, reason = read_row_fpp({"label": "planet", "fpp": 0.25, "fpp_method": "manual"})
    assert (value, method, reason) == (0.25, "manual", "ok")
    missing, _m, missing_reason = read_row_fpp({"label": "planet"})
    assert missing is None and missing_reason == "telemetry_absent"
    nullish, _m, null_reason = read_row_fpp({"label": "planet", "fpp": None})
    assert nullish is None and null_reason == "fpp_null"


def test_read_row_fpp_falls_back_to_sector_telemetry():
    row = {
        "label": "false_positive",
        "sector_results": [
            {"sector": 2, "fpp": 0.6, "fpp_available": True, "total_score": 10.0, "fpp_method": "v"},
            {"sector": 5, "fpp": 0.9, "fpp_available": True, "total_score": 80.0, "fpp_method": "v"},
        ],
    }
    value, _method, reason = read_row_fpp(row)
    assert value == 0.9 and reason == "ok"


def test_reasons_are_a_closed_set():
    for reason in (
        "ok",
        "telemetry_absent",
        "no_candidate_record",
        "fpp_null",
        "fpp_out_of_range",
        "not_evaluated",
        "label_outside_calibration_set",
    ):
        assert reason in FPP_REASONS


@pytest.mark.parametrize("value", [None, "missing", -0.5, 4.0, float("nan")])
def test_build_report_never_invents_zero_fpp(value):
    rows = [
        {"target_id": f"TIC {index}", "label": "false_positive", "evaluated": True, "target_fpp": value}
        for index in range(5)
    ]
    report = build_fpp_calibration_report(rows)
    assert report["cases"]["n_cases"] == 0
    assert report["cases"]["measured_exact_zero_count"] == 0
    assert report["data_integrity"]["zero_filled_missing_fpp_count"] == 0
    assert report["data_integrity"]["missing_fpp_rows_kept_as_not_evaluated"] == 5
    assert report["status"] == "pending_run"
    assert "no_labelled_fpp_cases" in report["blocking_reasons"]
    # Metriklerin kendisi "ölçülemedi" olarak kalır, düşük bir skora çevrilmez.
    for split in report["splits"].values():
        assert split["n_cases"] == 0
        assert split["brier_score"] is None
        assert split["roc_auc"] is None
