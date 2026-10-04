"""astrotransit/quality/fpp/beb_test.py için kapsamlı testler."""
from __future__ import annotations

import pytest

from astrotransit.quality.fpp.beb_test import (
    BEBIndicator,
    BEBScenarioEvaluator,
    BEBScenarioReport,
)
from astrotransit.quality.vetting import VettingVerdict

# ═══════════════════════════════════════════════════════
# BEBIndicator / BEBScenarioReport
# ═══════════════════════════════════════════════════════

def test_indicator_to_dict_full():
    ind = BEBIndicator(
        name="x", available=True, verdict=VettingVerdict.FAIL,
        value=1.5, warn_threshold=1.0, fail_threshold=2.0,
        score_contribution=0.3, description="d",
    )
    d = ind.to_dict()
    assert d["name"] == "x"
    assert d["available"] is True
    assert d["verdict"] == "fail"
    assert d["value"] == 1.5
    assert d["score_contribution"] == 0.3


def test_indicator_to_dict_none():
    ind = BEBIndicator("x", False, VettingVerdict.SKIP)
    d = ind.to_dict()
    assert d["value"] is None
    assert d["warn_threshold"] is None
    assert d["fail_threshold"] is None


def test_report_to_dict_and_summary():
    ind = BEBIndicator("x", True, VettingVerdict.PASS, value=1.0)
    r = BEBScenarioReport(
        target_id="TIC 1", sector=1, p_beb=0.15,
        beb_risk_flag="LOW_BEB_RISK",
        recommended_action="no_action",
        indicators=[ind], n_available=1,
    )
    d = r.to_dict()
    assert d["p_beb"] == 0.15
    assert len(d["indicators"]) == 1
    s = r.summary()
    assert "TIC 1" in s
    assert "p_beb=0.150" in s


def test_report_summary_none_p():
    r = BEBScenarioReport(target_id="T", sector=1, p_beb=None)
    assert "p_beb=NA" in r.summary()


# ═══════════════════════════════════════════════════════
# __init__
# ═══════════════════════════════════════════════════════

def test_init_defaults():
    e = BEBScenarioEvaluator()
    assert e.centroid_warn_arcsec == 5.0
    assert e.centroid_fail_arcsec == 10.0
    assert e.crowding_warn == 0.90
    assert e.crowding_fail == 0.85


def test_init_custom():
    e = BEBScenarioEvaluator(
        centroid_warn_arcsec=3.0, centroid_fail_arcsec=7.0,
        crowding_warn=0.8, crowding_fail=0.7,
        shallow_depth_warn_ppm=400.0, shallow_depth_fail_ppm=200.0,
    )
    assert e.centroid_warn_arcsec == 3.0
    assert e.crowding_fail == 0.7


# ═══════════════════════════════════════════════════════
# _to_float_or_none
# ═══════════════════════════════════════════════════════

def test_to_float_none():
    assert BEBScenarioEvaluator._to_float_or_none(None) is None


def test_to_float_bad():
    assert BEBScenarioEvaluator._to_float_or_none("x") is None


def test_to_float_nan():
    assert BEBScenarioEvaluator._to_float_or_none(float("nan")) is None


def test_to_float_ok():
    assert BEBScenarioEvaluator._to_float_or_none(3) == 3.0


# ═══════════════════════════════════════════════════════
# _indicator_centroid_shift
# ═══════════════════════════════════════════════════════

def test_centroid_missing():
    e = BEBScenarioEvaluator()
    assert e._indicator_centroid_shift(None).available is False
    assert e._indicator_centroid_shift(-1.0).available is False


def test_centroid_fail():
    e = BEBScenarioEvaluator(centroid_warn_arcsec=5.0, centroid_fail_arcsec=10.0)
    ind = e._indicator_centroid_shift(15.0)
    assert ind.verdict == VettingVerdict.FAIL
    assert ind.score_contribution == 0.40


def test_centroid_warn():
    e = BEBScenarioEvaluator(centroid_warn_arcsec=5.0, centroid_fail_arcsec=10.0)
    ind = e._indicator_centroid_shift(7.0)
    assert ind.verdict == VettingVerdict.WARN
    assert ind.score_contribution == 0.20


def test_centroid_pass_medium():
    e = BEBScenarioEvaluator(centroid_warn_arcsec=5.0, centroid_fail_arcsec=10.0)
    ind = e._indicator_centroid_shift(3.0)  # > 2.5 ama < 5
    assert ind.verdict == VettingVerdict.PASS
    assert ind.score_contribution == 0.08


def test_centroid_pass_low():
    e = BEBScenarioEvaluator(centroid_warn_arcsec=5.0, centroid_fail_arcsec=10.0)
    ind = e._indicator_centroid_shift(1.0)
    assert ind.verdict == VettingVerdict.PASS
    assert ind.score_contribution == 0.0


# ═══════════════════════════════════════════════════════
# _indicator_crowding_ratio
# ═══════════════════════════════════════════════════════

def test_crowding_missing():
    e = BEBScenarioEvaluator()
    assert e._indicator_crowding_ratio(None).available is False
    assert e._indicator_crowding_ratio(0.0).available is False
    assert e._indicator_crowding_ratio(-0.1).available is False


def test_crowding_fail():
    e = BEBScenarioEvaluator(crowding_warn=0.90, crowding_fail=0.85)
    ind = e._indicator_crowding_ratio(0.7)
    assert ind.verdict == VettingVerdict.FAIL
    assert ind.score_contribution == 0.25


def test_crowding_warn():
    e = BEBScenarioEvaluator(crowding_warn=0.90, crowding_fail=0.85)
    ind = e._indicator_crowding_ratio(0.87)
    assert ind.verdict == VettingVerdict.WARN
    assert ind.score_contribution == 0.12


def test_crowding_pass_medium():
    e = BEBScenarioEvaluator(crowding_warn=0.90, crowding_fail=0.85)
    ind = e._indicator_crowding_ratio(0.92)  # 0.90 < x < 0.95
    assert ind.verdict == VettingVerdict.PASS
    assert ind.score_contribution == 0.05


def test_crowding_pass_high():
    e = BEBScenarioEvaluator(crowding_warn=0.90, crowding_fail=0.85)
    ind = e._indicator_crowding_ratio(0.98)
    assert ind.verdict == VettingVerdict.PASS
    assert ind.score_contribution == 0.0


# ═══════════════════════════════════════════════════════
# _indicator_shallow_crowded
# ═══════════════════════════════════════════════════════

def test_shallow_missing():
    e = BEBScenarioEvaluator()
    assert e._indicator_shallow_crowded(None, 0.9).available is False
    assert e._indicator_shallow_crowded(0.001, None).available is False
    assert e._indicator_shallow_crowded(0.0, 0.9).available is False
    assert e._indicator_shallow_crowded(0.001, 0.0).available is False


def test_shallow_fail():
    e = BEBScenarioEvaluator(
        shallow_depth_fail_ppm=300.0, crowding_fail=0.85,
        shallow_depth_warn_ppm=500.0, crowding_warn=0.90,
    )
    # depth 0.0002 = 200 ppm < 300, crowding 0.8 < 0.85 → FAIL
    ind = e._indicator_shallow_crowded(0.0002, 0.80)
    assert ind.verdict == VettingVerdict.FAIL
    assert ind.score_contribution == 0.20


def test_shallow_warn():
    e = BEBScenarioEvaluator(
        shallow_depth_fail_ppm=300.0, crowding_fail=0.85,
        shallow_depth_warn_ppm=500.0, crowding_warn=0.90,
    )
    # depth 400 ppm < 500 warn, crowding 0.88 < 0.90 warn
    ind = e._indicator_shallow_crowded(0.0004, 0.88)
    assert ind.verdict == VettingVerdict.WARN
    assert ind.score_contribution == 0.15


def test_shallow_pass_medium():
    e = BEBScenarioEvaluator(
        shallow_depth_warn_ppm=500.0, shallow_depth_fail_ppm=300.0,
        crowding_warn=0.90, crowding_fail=0.85,
    )
    # depth 800 ppm < 1000, crowding 0.91 < 0.92
    ind = e._indicator_shallow_crowded(0.0008, 0.91)
    assert ind.verdict == VettingVerdict.PASS
    assert ind.score_contribution == 0.05


def test_shallow_pass_clean():
    e = BEBScenarioEvaluator(
        shallow_depth_warn_ppm=500.0, shallow_depth_fail_ppm=300.0,
        crowding_warn=0.90, crowding_fail=0.85,
    )
    # depth 2000 ppm, crowding 0.98
    ind = e._indicator_shallow_crowded(0.002, 0.98)
    assert ind.verdict == VettingVerdict.PASS
    assert ind.score_contribution == 0.0


# ═══════════════════════════════════════════════════════
# _compute_p_beb / _compute_flag / _recommend_action
# ═══════════════════════════════════════════════════════

def test_compute_p_beb_empty():
    assert BEBScenarioEvaluator._compute_p_beb([]) is None


def test_compute_p_beb_all_unavailable():
    inds = [BEBIndicator("a", False, VettingVerdict.SKIP, score_contribution=0.5)]
    assert BEBScenarioEvaluator._compute_p_beb(inds) is None


def test_compute_p_beb_clipped():
    inds = [
        BEBIndicator("a", True, VettingVerdict.FAIL, score_contribution=0.6),
        BEBIndicator("b", True, VettingVerdict.FAIL, score_contribution=0.7),
    ]
    p = BEBScenarioEvaluator._compute_p_beb(inds)
    assert p == 0.95  # clip


def test_compute_p_beb_sum():
    inds = [
        BEBIndicator("a", True, VettingVerdict.PASS, score_contribution=0.1),
        BEBIndicator("b", True, VettingVerdict.PASS, score_contribution=0.2),
    ]
    assert BEBScenarioEvaluator._compute_p_beb(inds) == pytest.approx(0.3)


def test_compute_flag_high_on_fail():
    inds = [BEBIndicator("a", True, VettingVerdict.FAIL)]
    assert BEBScenarioEvaluator._compute_flag(inds, 0.1) == "HIGH_BEB_RISK"


def test_compute_flag_high_on_p():
    inds = [BEBIndicator("a", True, VettingVerdict.PASS)]
    assert BEBScenarioEvaluator._compute_flag(inds, 0.6) == "HIGH_BEB_RISK"


def test_compute_flag_moderate_on_warn():
    inds = [BEBIndicator("a", True, VettingVerdict.WARN)]
    assert BEBScenarioEvaluator._compute_flag(inds, 0.1) == "MODERATE_BEB_RISK"


def test_compute_flag_moderate_on_p():
    inds = [BEBIndicator("a", True, VettingVerdict.PASS)]
    assert BEBScenarioEvaluator._compute_flag(inds, 0.25) == "MODERATE_BEB_RISK"


def test_compute_flag_unknown():
    inds = [BEBIndicator("a", False, VettingVerdict.SKIP)]
    assert BEBScenarioEvaluator._compute_flag(inds, None) == "UNKNOWN"


def test_compute_flag_low():
    inds = [BEBIndicator("a", True, VettingVerdict.PASS)]
    assert BEBScenarioEvaluator._compute_flag(inds, 0.05) == "LOW_BEB_RISK"


def test_recommend_action_all():
    # Flag isimleri koda göre; bilinmeyen → fallback
    result_low = BEBScenarioEvaluator._recommend_action("LOW_BEB_RISK")
    result_high = BEBScenarioEvaluator._recommend_action("HIGH_BEB_RISK")
    result_mod = BEBScenarioEvaluator._recommend_action("MODERATE_BEB_RISK")
    result_unknown = BEBScenarioEvaluator._recommend_action("UNKNOWN")
    assert isinstance(result_low, str)
    assert isinstance(result_high, str)
    assert isinstance(result_mod, str)
    assert isinstance(result_unknown, str)


# ═══════════════════════════════════════════════════════
# evaluate — integration
# ═══════════════════════════════════════════════════════

def test_evaluate_full_clean():
    e = BEBScenarioEvaluator()
    r = e.evaluate(
        target_id="TIC 1", sector=1,
        centroid_shift_arcsec=1.0, crowding_ratio=0.99,
        primary_depth=0.001,
    )
    assert r.beb_risk_flag == "LOW_BEB_RISK"
    assert r.n_available == 3
    assert r.n_fail == 0


def test_evaluate_full_high_risk():
    e = BEBScenarioEvaluator()
    r = e.evaluate(
        target_id="TIC 2", sector=2,
        centroid_shift_arcsec=15.0,  # FAIL
        crowding_ratio=0.7,  # FAIL
        primary_depth=0.0002,  # shallow
    )
    assert r.beb_risk_flag == "HIGH_BEB_RISK"
    assert r.n_fail >= 2


def test_evaluate_no_inputs():
    e = BEBScenarioEvaluator()
    r = e.evaluate(target_id="T", sector=1)
    assert r.beb_risk_flag == "UNKNOWN"
    assert r.p_beb is None
    assert r.n_available == 0


def test_evaluate_details_include_ppm():
    e = BEBScenarioEvaluator()
    r = e.evaluate(
        target_id="T", sector=1,
        primary_depth=0.001,
    )
    assert r.details["primary_depth_ppm"] == 1000.0


def test_evaluate_details_none_depth():
    e = BEBScenarioEvaluator()
    r = e.evaluate(target_id="T", sector=1)
    assert r.details["primary_depth_ppm"] is None


def test_evaluate_evidence_flags():
    e = BEBScenarioEvaluator()
    r = e.evaluate(
        target_id="T", sector=1,
        centroid_shift_arcsec=15.0, crowding_ratio=0.7,
        primary_depth=0.0002,
    )
    assert "centroid_shift" in r.evidence_flags
    assert "crowding_ratio" in r.evidence_flags
