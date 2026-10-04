"""astrotransit/quality/fpp/eb_test.py için testler."""
from __future__ import annotations

from types import SimpleNamespace

from astrotransit.quality.fpp.eb_test import (
    EBIndicator,
    EBScenarioEvaluator,
    EBScenarioReport,
)
from astrotransit.quality.vetting import VettingVerdict

# ═══════════════════════════════════════════════════════
# EBIndicator
# ═══════════════════════════════════════════════════════

def test_indicator_to_dict_full():
    ind = EBIndicator(
        name="even_odd", available=True, verdict=VettingVerdict.FAIL,
        value=0.42, warn_threshold=0.1, fail_threshold=0.3,
        score_contribution=0.35, description="bad",
    )
    d = ind.to_dict()
    assert d["name"] == "even_odd"
    assert d["available"] is True
    assert d["verdict"] == "fail"
    assert d["value"] == 0.42
    assert d["score_contribution"] == 0.35


def test_indicator_to_dict_none_value():
    ind = EBIndicator(
        name="x", available=False, verdict=VettingVerdict.SKIP,
    )
    d = ind.to_dict()
    assert d["value"] is None
    assert d["warn_threshold"] is None
    assert d["fail_threshold"] is None


# ═══════════════════════════════════════════════════════
# EBScenarioReport
# ═══════════════════════════════════════════════════════

def test_report_to_dict_and_summary():
    ind = EBIndicator(
        name="x", available=True, verdict=VettingVerdict.PASS, value=0.05,
    )
    r = EBScenarioReport(
        target_id="TIC 1", sector=1,
        p_eb=0.15, eb_risk_flag="LOW_EB_RISK",
        recommended_action="planet_hypothesis_supported",
        indicators=[ind], n_available=1,
    )
    d = r.to_dict()
    assert d["p_eb"] == 0.15
    assert d["n_available"] == 1
    assert len(d["indicators"]) == 1
    assert "TIC 1" in r.summary()
    assert "p_eb=0.150" in r.summary()


def test_report_summary_with_none_p_eb():
    r = EBScenarioReport(target_id="T", sector=1, p_eb=None)
    assert "p_eb=NA" in r.summary()


# ═══════════════════════════════════════════════════════
# __init__
# ═══════════════════════════════════════════════════════

def test_evaluator_init_defaults():
    ev = EBScenarioEvaluator()
    assert ev.even_odd_warn > 0
    assert ev.even_odd_fail > ev.even_odd_warn


def test_evaluator_init_custom():
    ev = EBScenarioEvaluator(
        even_odd_warn=0.05, even_odd_fail=0.2,
        vshape_warn=0.5, vshape_fail=0.8,
        secondary_ratio_warn=0.1, secondary_ratio_fail=0.2,
    )
    assert ev.even_odd_warn == 0.05
    assert ev.vshape_fail == 0.8


# ═══════════════════════════════════════════════════════
# _indicator_even_odd
# ═══════════════════════════════════════════════════════

def test_even_odd_insufficient_transits():
    ev = EBScenarioEvaluator()
    ind = ev._indicator_even_odd(
        primary_depth=0.01, odd_depth=0.011, even_depth=0.010,
        n_transits=1,
    )
    assert ind.available is False
    assert ind.verdict == VettingVerdict.SKIP


def test_even_odd_missing_depths():
    ev = EBScenarioEvaluator()
    ind = ev._indicator_even_odd(
        primary_depth=None, odd_depth=None, even_depth=None, n_transits=5,
    )
    assert ind.available is False


def test_even_odd_fail():
    ev = EBScenarioEvaluator(even_odd_warn=0.05, even_odd_fail=0.2)
    ind = ev._indicator_even_odd(
        primary_depth=0.01, odd_depth=0.02, even_depth=0.01, n_transits=5,
    )
    # frac_diff = |0.02-0.01| / 0.01 = 1.0 → FAIL
    assert ind.verdict == VettingVerdict.FAIL
    assert ind.available is True
    assert ind.score_contribution == 0.35


def test_even_odd_warn():
    ev = EBScenarioEvaluator(even_odd_warn=0.05, even_odd_fail=0.5)
    ind = ev._indicator_even_odd(
        primary_depth=0.01, odd_depth=0.0108, even_depth=0.01, n_transits=5,
    )
    # frac_diff = 0.08 → WARN
    assert ind.verdict == VettingVerdict.WARN
    assert ind.score_contribution == 0.18


def test_even_odd_pass_small():
    ev = EBScenarioEvaluator(even_odd_warn=0.2, even_odd_fail=0.5)
    ind = ev._indicator_even_odd(
        primary_depth=0.01, odd_depth=0.01002, even_depth=0.01, n_transits=5,
    )
    # frac_diff = 0.002 → küçük
    assert ind.verdict == VettingVerdict.PASS


def test_even_odd_pass_medium():
    ev = EBScenarioEvaluator(even_odd_warn=0.5, even_odd_fail=0.8)
    ind = ev._indicator_even_odd(
        primary_depth=0.01, odd_depth=0.0115, even_depth=0.01, n_transits=5,
    )
    # frac_diff = 0.15 → PASS + 0.05 contribution
    assert ind.verdict == VettingVerdict.PASS
    assert ind.score_contribution == 0.05


# ═══════════════════════════════════════════════════════
# _indicator_vshape
# ═══════════════════════════════════════════════════════

def test_vshape_missing():
    ev = EBScenarioEvaluator()
    assert ev._indicator_vshape(None).available is False


def test_vshape_nan():
    ev = EBScenarioEvaluator()
    assert ev._indicator_vshape(float("nan")).available is False


def test_vshape_fail():
    ev = EBScenarioEvaluator(vshape_warn=0.6, vshape_fail=0.8)
    ind = ev._indicator_vshape(0.9)
    assert ind.verdict == VettingVerdict.FAIL
    assert ind.score_contribution == 0.30


def test_vshape_warn():
    ev = EBScenarioEvaluator(vshape_warn=0.6, vshape_fail=0.8)
    ind = ev._indicator_vshape(0.7)
    assert ind.verdict == VettingVerdict.WARN


def test_vshape_pass_medium():
    ev = EBScenarioEvaluator(vshape_warn=0.8, vshape_fail=0.95)
    ind = ev._indicator_vshape(0.6)
    assert ind.verdict == VettingVerdict.PASS
    assert ind.score_contribution == 0.05


def test_vshape_pass_clean():
    ev = EBScenarioEvaluator(vshape_warn=0.8, vshape_fail=0.95)
    ind = ev._indicator_vshape(0.3)
    assert ind.verdict == VettingVerdict.PASS
    assert ind.score_contribution == 0.0


# ═══════════════════════════════════════════════════════
# _indicator_secondary
# ═══════════════════════════════════════════════════════

def test_secondary_missing():
    ev = EBScenarioEvaluator()
    assert ev._indicator_secondary(None, 0.001).available is False
    assert ev._indicator_secondary(0.01, None).available is False
    assert ev._indicator_secondary(0.0, 0.001).available is False


def test_secondary_fail():
    ev = EBScenarioEvaluator(
        secondary_ratio_warn=0.1, secondary_ratio_fail=0.2,
    )
    ind = ev._indicator_secondary(0.01, 0.005)
    # ratio = 0.5 > 0.2 → FAIL
    assert ind.verdict == VettingVerdict.FAIL
    assert ind.value == 0.5


def test_secondary_warn():
    ev = EBScenarioEvaluator(
        secondary_ratio_warn=0.1, secondary_ratio_fail=0.5,
    )
    ind = ev._indicator_secondary(0.01, 0.002)
    # ratio = 0.2 → WARN
    assert ind.verdict == VettingVerdict.WARN


def test_secondary_pass():
    ev = EBScenarioEvaluator(
        secondary_ratio_warn=0.2, secondary_ratio_fail=0.5,
    )
    ind = ev._indicator_secondary(0.01, 0.0005)
    # ratio = 0.05 → PASS clean
    assert ind.verdict == VettingVerdict.PASS
    assert ind.score_contribution == 0.0


# ═══════════════════════════════════════════════════════
# _resolve_identity
# ═══════════════════════════════════════════════════════

def test_resolve_identity_explicit():
    t, s = EBScenarioEvaluator._resolve_identity(
        target_id="TIC 1", sector=5, transit_report=None, vetting_report=None,
    )
    assert t == "TIC 1"
    assert s == 5


def test_resolve_identity_from_transit_report():
    rep = SimpleNamespace(target_id="TIC 2", sector=3)
    t, s = EBScenarioEvaluator._resolve_identity(
        target_id=None, sector=None, transit_report=rep, vetting_report=None,
    )
    assert t == "TIC 2"
    assert s == 3


def test_resolve_identity_from_vetting_report():
    rep = SimpleNamespace(target_id="TIC 3", sector=4)
    t, s = EBScenarioEvaluator._resolve_identity(
        target_id=None, sector=None, transit_report=None, vetting_report=rep,
    )
    assert t == "TIC 3"
    assert s == 4


def test_resolve_identity_unknown():
    t, s = EBScenarioEvaluator._resolve_identity(
        target_id=None, sector=None, transit_report=None, vetting_report=None,
    )
    assert t == "UNKNOWN_TARGET"
    assert s == -1


# ═══════════════════════════════════════════════════════
# _to_float_or_none
# ═══════════════════════════════════════════════════════

def test_to_float_none():
    assert EBScenarioEvaluator._to_float_or_none(None) is None


def test_to_float_bad():
    assert EBScenarioEvaluator._to_float_or_none("bad") is None


def test_to_float_nan():
    assert EBScenarioEvaluator._to_float_or_none(float("nan")) is None


def test_to_float_ok():
    assert EBScenarioEvaluator._to_float_or_none(3) == 3.0


# ═══════════════════════════════════════════════════════
# _get_test_value
# ═══════════════════════════════════════════════════════

def test_get_test_value_no_tests():
    assert EBScenarioEvaluator._get_test_value(SimpleNamespace(), "x") is None


def test_get_test_value_found():
    tests = [SimpleNamespace(name="v_shape_metric", value=0.6)]
    rep = SimpleNamespace(tests=tests)
    assert EBScenarioEvaluator._get_test_value(rep, "v_shape_metric") == 0.6


def test_get_test_value_not_found():
    tests = [SimpleNamespace(name="x", value=1.0)]
    rep = SimpleNamespace(tests=tests)
    assert EBScenarioEvaluator._get_test_value(rep, "y") is None


def test_get_test_value_invalid():
    tests = [SimpleNamespace(name="x", value="bad")]
    rep = SimpleNamespace(tests=tests)
    assert EBScenarioEvaluator._get_test_value(rep, "x") is None


# ═══════════════════════════════════════════════════════
# _compute_p_eb, _compute_flag, _recommend_action
# ═══════════════════════════════════════════════════════

def test_compute_p_eb_empty():
    assert EBScenarioEvaluator._compute_p_eb([]) is None


def test_compute_p_eb_clipped():
    inds = [
        EBIndicator("a", True, VettingVerdict.FAIL, score_contribution=0.4),
        EBIndicator("b", True, VettingVerdict.FAIL, score_contribution=0.5),
    ]
    p = EBScenarioEvaluator._compute_p_eb(inds)
    assert p is not None
    assert 0.0 <= p <= 1.0


def test_compute_p_eb_skips_unavailable():
    inds = [
        EBIndicator("a", True, VettingVerdict.PASS, score_contribution=0.1),
        EBIndicator("b", False, VettingVerdict.SKIP, score_contribution=0.5),
    ]
    assert EBScenarioEvaluator._compute_p_eb(inds) == 0.1


def test_compute_flag_high_on_fail():
    inds = [EBIndicator("a", True, VettingVerdict.FAIL)]
    assert EBScenarioEvaluator._compute_flag(inds, 0.1) == "HIGH_EB_RISK"


def test_compute_flag_high_on_p_eb():
    inds = [EBIndicator("a", True, VettingVerdict.PASS)]
    assert EBScenarioEvaluator._compute_flag(inds, 0.55) == "HIGH_EB_RISK"


def test_compute_flag_moderate_on_warn():
    inds = [EBIndicator("a", True, VettingVerdict.WARN)]
    assert EBScenarioEvaluator._compute_flag(inds, 0.1) == "MODERATE_EB_RISK"


def test_compute_flag_moderate_on_p_eb():
    inds = [EBIndicator("a", True, VettingVerdict.PASS)]
    assert EBScenarioEvaluator._compute_flag(inds, 0.25) == "MODERATE_EB_RISK"


def test_compute_flag_unknown():
    inds = [EBIndicator("a", False, VettingVerdict.SKIP)]
    assert EBScenarioEvaluator._compute_flag(inds, None) == "UNKNOWN"


def test_compute_flag_low():
    inds = [EBIndicator("a", True, VettingVerdict.PASS)]
    assert EBScenarioEvaluator._compute_flag(inds, 0.05) == "LOW_EB_RISK"


def test_recommend_action_all_flags():
    assert EBScenarioEvaluator._recommend_action("LOW_EB_RISK") == "planet_hypothesis_supported"
    assert EBScenarioEvaluator._recommend_action("MODERATE_EB_RISK") == "manual_eb_review"
    assert EBScenarioEvaluator._recommend_action("HIGH_EB_RISK") == "deprioritize_as_possible_eb"
    assert EBScenarioEvaluator._recommend_action("UNKNOWN") == "insufficient_data"


# ═══════════════════════════════════════════════════════
# evaluate — entegrasyon
# ═══════════════════════════════════════════════════════

def test_evaluate_full_low_risk():
    ev = EBScenarioEvaluator()
    r = ev.evaluate(
        target_id="TIC 1", sector=1,
        primary_depth=0.01, odd_depth=0.0101, even_depth=0.01,
        v_shape_score=0.3, secondary_depth=0.0005, n_transits=5,
    )
    assert isinstance(r, EBScenarioReport)
    assert r.target_id == "TIC 1"
    assert r.eb_risk_flag == "LOW_EB_RISK"
    assert r.n_available == 3


def test_evaluate_full_high_risk():
    ev = EBScenarioEvaluator()
    r = ev.evaluate(
        target_id="TIC 2", sector=2,
        primary_depth=0.01, odd_depth=0.02, even_depth=0.01,
        v_shape_score=0.95, secondary_depth=0.005, n_transits=5,
    )
    assert r.eb_risk_flag == "HIGH_EB_RISK"
    assert r.n_fail >= 1


def test_evaluate_no_inputs():
    ev = EBScenarioEvaluator()
    r = ev.evaluate(target_id="T", sector=1)
    assert r.eb_risk_flag == "UNKNOWN"
    assert r.p_eb is None
    assert r.n_available == 0
    assert r.recommended_action == "insufficient_data"


def test_evaluate_from_transit_report():
    ev = EBScenarioEvaluator()
    transit_report = SimpleNamespace(
        target_id="TIC X", sector=7,
        details={
            "n_transits": 5,
            "per_transit_depth_median": 0.01,
            "odd_depth_median": 0.0101,
            "even_depth_median": 0.01,
        },
        tests=[SimpleNamespace(name="v_shape_metric", value=0.3)],
    )
    r = ev.evaluate(transit_report=transit_report)
    assert r.target_id == "TIC X"
    assert r.sector == 7
    assert r.n_available >= 2


def test_evaluate_from_vetting_report():
    ev = EBScenarioEvaluator()
    transit_report = SimpleNamespace(
        target_id="TIC Y", sector=3,
        details={"n_transits": 5, "per_transit_depth_median": 0.01},
        tests=[],
    )
    vetting_report = SimpleNamespace(
        target_id="TIC Y", sector=3,
        tests=[SimpleNamespace(name="secondary_eclipse", value=0.001)],
    )
    r = ev.evaluate(
        transit_report=transit_report, vetting_report=vetting_report,
    )
    assert r.target_id == "TIC Y"


def test_evaluate_partial_metrics():
    ev = EBScenarioEvaluator()
    r = ev.evaluate(
        target_id="T", sector=1,
        primary_depth=0.01, odd_depth=0.0101, even_depth=0.01,
        n_transits=5,
    )
    assert r.n_available >= 1
    # vshape + secondary skip
    assert r.p_eb is not None


def test_evaluate_evidence_flags():
    ev = EBScenarioEvaluator()
    r = ev.evaluate(
        target_id="T", sector=1,
        primary_depth=0.01, odd_depth=0.02, even_depth=0.01,
        n_transits=5,
    )
    assert "even_odd_depth_difference" in r.evidence_flags
