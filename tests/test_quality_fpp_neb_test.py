"""astrotransit/quality/fpp/neb_test.py için testler."""
from __future__ import annotations

from astrotransit.quality.fpp.neb_test import (
    NEBIndicator,
    NEBScenarioEvaluator,
    NEBScenarioReport,
)
from astrotransit.quality.vetting import VettingVerdict

# ═══════════════════════════════════════════════════════
# NEBIndicator
# ═══════════════════════════════════════════════════════

def test_indicator_to_dict_full():
    ind = NEBIndicator(
        name="n", available=True, verdict=VettingVerdict.FAIL,
        value=2.5, warn_threshold=3.0, fail_threshold=5.0,
        score_contribution=0.3, description="x",
    )
    d = ind.to_dict()
    assert d["name"] == "n"
    assert d["value"] == 2.5
    assert d["warn_threshold"] == 3.0
    assert d["verdict"] == "fail"


def test_indicator_to_dict_none():
    ind = NEBIndicator("n", False, VettingVerdict.SKIP)
    d = ind.to_dict()
    assert d["value"] is None
    assert d["warn_threshold"] is None
    assert d["fail_threshold"] is None


# ═══════════════════════════════════════════════════════
# NEBScenarioReport
# ═══════════════════════════════════════════════════════

def test_report_to_dict_and_summary():
    ind = NEBIndicator("n", True, VettingVerdict.PASS, value=1.0)
    r = NEBScenarioReport(
        target_id="TIC 1", sector=1, p_neb=0.1,
        neb_risk_flag="LOW_NEB_RISK",
        recommended_action="nearby_eb_not_supported",
        indicators=[ind], n_available=1,
    )
    d = r.to_dict()
    assert d["p_neb"] == 0.1
    assert len(d["indicators"]) == 1
    s = r.summary()
    assert "TIC 1" in s
    assert "p_neb=0.100" in s


def test_report_summary_none_p():
    r = NEBScenarioReport(target_id="T", sector=1, p_neb=None)
    assert "p_neb=NA" in r.summary()


# ═══════════════════════════════════════════════════════
# __init__
# ═══════════════════════════════════════════════════════

def test_init_defaults():
    ev = NEBScenarioEvaluator()
    assert ev.neighbor_count_warn > 0
    assert ev.neighbor_count_fail > ev.neighbor_count_warn


def test_init_custom():
    ev = NEBScenarioEvaluator(
        neighbor_count_warn=3, neighbor_count_fail=6,
        close_bright_nearest_warn_arcsec=5.0,
        close_bright_nearest_fail_arcsec=3.0,
        close_bright_delta_mag_warn=4.0,
        close_bright_delta_mag_fail=2.0,
        nearest_warn_arcsec=10.0,
        nearest_fail_arcsec=5.0,
    )
    assert ev.neighbor_count_fail == 6
    assert ev.nearest_fail_arcsec == 5.0


# ═══════════════════════════════════════════════════════
# _to_float_or_none / _to_int_or_none
# ═══════════════════════════════════════════════════════

def test_to_float_none():
    assert NEBScenarioEvaluator._to_float_or_none(None) is None


def test_to_float_bad():
    assert NEBScenarioEvaluator._to_float_or_none("x") is None


def test_to_float_nan():
    assert NEBScenarioEvaluator._to_float_or_none(float("nan")) is None


def test_to_float_ok():
    assert NEBScenarioEvaluator._to_float_or_none(3) == 3.0


def test_to_int_none():
    assert NEBScenarioEvaluator._to_int_or_none(None) is None


def test_to_int_bad():
    assert NEBScenarioEvaluator._to_int_or_none("x") is None


def test_to_int_ok():
    assert NEBScenarioEvaluator._to_int_or_none(5) == 5


# ═══════════════════════════════════════════════════════
# _indicator_close_bright_neighbor
# ═══════════════════════════════════════════════════════

def test_close_bright_missing():
    ev = NEBScenarioEvaluator()
    assert ev._indicator_close_bright_neighbor(None, 1.0).available is False
    assert ev._indicator_close_bright_neighbor(5.0, None).available is False
    assert ev._indicator_close_bright_neighbor(0.0, 1.0).available is False


def test_close_bright_fail():
    ev = NEBScenarioEvaluator(
        close_bright_nearest_fail_arcsec=3.0,
        close_bright_delta_mag_fail=2.0,
        close_bright_nearest_warn_arcsec=5.0,
        close_bright_delta_mag_warn=4.0,
    )
    ind = ev._indicator_close_bright_neighbor(2.0, 1.0)
    assert ind.verdict == VettingVerdict.FAIL
    assert ind.score_contribution == 0.30


def test_close_bright_warn():
    ev = NEBScenarioEvaluator(
        close_bright_nearest_fail_arcsec=3.0,
        close_bright_delta_mag_fail=2.0,
        close_bright_nearest_warn_arcsec=5.0,
        close_bright_delta_mag_warn=4.0,
    )
    ind = ev._indicator_close_bright_neighbor(4.0, 3.0)
    assert ind.verdict == VettingVerdict.WARN


def test_close_bright_pass_medium():
    ev = NEBScenarioEvaluator(
        close_bright_nearest_fail_arcsec=1.0,
        close_bright_delta_mag_fail=0.5,
        close_bright_nearest_warn_arcsec=2.0,
        close_bright_delta_mag_warn=1.0,
    )
    ind = ev._indicator_close_bright_neighbor(20.0, 3.0)
    # r<40 ve dm<5 → PASS + 0.06
    assert ind.verdict == VettingVerdict.PASS
    assert ind.score_contribution == 0.06


def test_close_bright_pass_clean():
    ev = NEBScenarioEvaluator(
        close_bright_nearest_fail_arcsec=1.0,
        close_bright_delta_mag_fail=0.5,
        close_bright_nearest_warn_arcsec=2.0,
        close_bright_delta_mag_warn=1.0,
    )
    ind = ev._indicator_close_bright_neighbor(50.0, 6.0)
    assert ind.verdict == VettingVerdict.PASS
    assert ind.score_contribution == 0.0


# ═══════════════════════════════════════════════════════
# _indicator_neighbor_density
# ═══════════════════════════════════════════════════════

def test_neighbor_density_missing():
    ev = NEBScenarioEvaluator()
    assert ev._indicator_neighbor_density(None).available is False
    assert ev._indicator_neighbor_density(-1).available is False


def test_neighbor_density_fail():
    ev = NEBScenarioEvaluator(neighbor_count_warn=3, neighbor_count_fail=5)
    ind = ev._indicator_neighbor_density(10)
    assert ind.verdict == VettingVerdict.FAIL
    assert ind.score_contribution == 0.25


def test_neighbor_density_warn():
    ev = NEBScenarioEvaluator(neighbor_count_warn=3, neighbor_count_fail=5)
    ind = ev._indicator_neighbor_density(4)
    assert ind.verdict == VettingVerdict.WARN


def test_neighbor_density_pass_medium():
    ev = NEBScenarioEvaluator(neighbor_count_warn=5, neighbor_count_fail=10)
    ind = ev._indicator_neighbor_density(3)
    assert ind.verdict == VettingVerdict.PASS
    assert ind.score_contribution == 0.05


def test_neighbor_density_pass_clean():
    ev = NEBScenarioEvaluator(neighbor_count_warn=5, neighbor_count_fail=10)
    ind = ev._indicator_neighbor_density(0)
    assert ind.verdict == VettingVerdict.PASS
    assert ind.score_contribution == 0.0


# ═══════════════════════════════════════════════════════
# _indicator_nearest_neighbor_proximity
# ═══════════════════════════════════════════════════════

def test_nearest_missing():
    ev = NEBScenarioEvaluator()
    assert ev._indicator_nearest_neighbor_proximity(None, 1.0).available is False
    assert ev._indicator_nearest_neighbor_proximity(0.0, 1.0).available is False


def test_nearest_fail_very_close_bright():
    ev = NEBScenarioEvaluator(nearest_fail_arcsec=5.0, nearest_warn_arcsec=10.0)
    ind = ev._indicator_nearest_neighbor_proximity(3.0, 2.0)
    assert ind.verdict == VettingVerdict.FAIL
    assert ind.score_contribution == 0.25


def test_nearest_fail_close_dim():
    ev = NEBScenarioEvaluator(nearest_fail_arcsec=5.0, nearest_warn_arcsec=10.0)
    ind = ev._indicator_nearest_neighbor_proximity(3.0, 4.0)
    assert ind.verdict == VettingVerdict.WARN
    assert ind.score_contribution == 0.10


def test_nearest_fail_very_dim():
    ev = NEBScenarioEvaluator(nearest_fail_arcsec=5.0, nearest_warn_arcsec=10.0)
    ind = ev._indicator_nearest_neighbor_proximity(3.0, 7.0)
    assert ind.verdict == VettingVerdict.PASS
    assert ind.score_contribution == 0.03


def test_nearest_warn_near_bright():
    ev = NEBScenarioEvaluator(nearest_fail_arcsec=3.0, nearest_warn_arcsec=10.0)
    ind = ev._indicator_nearest_neighbor_proximity(7.0, 3.0)
    assert ind.verdict == VettingVerdict.WARN
    assert ind.score_contribution == 0.12


def test_nearest_warn_near_dim():
    ev = NEBScenarioEvaluator(nearest_fail_arcsec=3.0, nearest_warn_arcsec=10.0)
    ind = ev._indicator_nearest_neighbor_proximity(7.0, 6.0)
    assert ind.verdict == VettingVerdict.PASS
    assert ind.score_contribution == 0.04


def test_nearest_pass_moderate():
    ev = NEBScenarioEvaluator(nearest_fail_arcsec=3.0, nearest_warn_arcsec=10.0)
    ind = ev._indicator_nearest_neighbor_proximity(20.0, 3.0)
    assert ind.verdict == VettingVerdict.PASS
    assert ind.score_contribution == 0.04


def test_nearest_pass_far():
    ev = NEBScenarioEvaluator(nearest_fail_arcsec=3.0, nearest_warn_arcsec=10.0)
    ind = ev._indicator_nearest_neighbor_proximity(60.0, 3.0)
    assert ind.verdict == VettingVerdict.PASS
    assert ind.score_contribution == 0.0


def test_nearest_dm_none():
    ev = NEBScenarioEvaluator(nearest_fail_arcsec=5.0, nearest_warn_arcsec=10.0)
    ind = ev._indicator_nearest_neighbor_proximity(3.0, None)
    # dm None → PASS (çünkü dm<3.5 ve dm<5.0 koşulları False)
    assert ind.verdict == VettingVerdict.PASS


# ═══════════════════════════════════════════════════════
# _compute_p_neb / _compute_flag / _recommend_action
# ═══════════════════════════════════════════════════════

def test_compute_p_neb_empty():
    assert NEBScenarioEvaluator._compute_p_neb([]) is None


def test_compute_p_neb_clipped():
    inds = [
        NEBIndicator("a", True, VettingVerdict.FAIL, score_contribution=0.4),
        NEBIndicator("b", True, VettingVerdict.FAIL, score_contribution=0.5),
    ]
    p = NEBScenarioEvaluator._compute_p_neb(inds)
    assert 0.0 <= p <= 1.0


def test_compute_p_neb_skip_unavailable():
    inds = [
        NEBIndicator("a", True, VettingVerdict.PASS, score_contribution=0.1),
        NEBIndicator("b", False, VettingVerdict.SKIP, score_contribution=0.9),
    ]
    assert NEBScenarioEvaluator._compute_p_neb(inds) == 0.1


def test_compute_flag_high_on_fail():
    inds = [NEBIndicator("a", True, VettingVerdict.FAIL)]
    assert NEBScenarioEvaluator._compute_flag(inds, 0.1) == "HIGH_NEB_RISK"


def test_compute_flag_high_on_p():
    inds = [NEBIndicator("a", True, VettingVerdict.PASS)]
    assert NEBScenarioEvaluator._compute_flag(inds, 0.55) == "HIGH_NEB_RISK"


def test_compute_flag_moderate_on_warn():
    inds = [NEBIndicator("a", True, VettingVerdict.WARN)]
    assert NEBScenarioEvaluator._compute_flag(inds, 0.1) == "MODERATE_NEB_RISK"


def test_compute_flag_moderate_on_p():
    inds = [NEBIndicator("a", True, VettingVerdict.PASS)]
    assert NEBScenarioEvaluator._compute_flag(inds, 0.25) == "MODERATE_NEB_RISK"


def test_compute_flag_unknown():
    inds = [NEBIndicator("a", False, VettingVerdict.SKIP)]
    assert NEBScenarioEvaluator._compute_flag(inds, None) == "UNKNOWN"


def test_compute_flag_low():
    inds = [NEBIndicator("a", True, VettingVerdict.PASS)]
    assert NEBScenarioEvaluator._compute_flag(inds, 0.05) == "LOW_NEB_RISK"


def test_recommend_action_all():
    assert NEBScenarioEvaluator._recommend_action("LOW_NEB_RISK") == "nearby_eb_not_supported"
    assert NEBScenarioEvaluator._recommend_action("MODERATE_NEB_RISK") == "inspect_gaia_neighbors"
    assert NEBScenarioEvaluator._recommend_action("HIGH_NEB_RISK") == "deprioritize_as_possible_nearby_eb"
    assert NEBScenarioEvaluator._recommend_action("UNKNOWN") == "insufficient_data"


# ═══════════════════════════════════════════════════════
# evaluate — entegrasyon
# ═══════════════════════════════════════════════════════

def test_evaluate_full_low_risk():
    ev = NEBScenarioEvaluator()
    r = ev.evaluate(
        target_id="TIC 1", sector=1,
        gaia_neighbors_within_60arcsec=0,
        brightest_neighbor_delta_mag=8.0,
        nearest_neighbor_arcsec=60.0,
    )
    assert r.neb_risk_flag == "LOW_NEB_RISK"
    assert r.n_available == 3
    assert r.details["is_isolated"] is True


def test_evaluate_full_high_risk():
    ev = NEBScenarioEvaluator()
    r = ev.evaluate(
        target_id="TIC 2", sector=2,
        gaia_neighbors_within_60arcsec=20,
        brightest_neighbor_delta_mag=1.0,
        nearest_neighbor_arcsec=2.0,
    )
    assert r.neb_risk_flag == "HIGH_NEB_RISK"
    assert r.n_fail >= 1


def test_evaluate_no_inputs():
    ev = NEBScenarioEvaluator()
    r = ev.evaluate(target_id="T", sector=1)
    assert r.neb_risk_flag == "UNKNOWN"
    assert r.p_neb is None
    assert r.n_available == 0


def test_evaluate_partial():
    ev = NEBScenarioEvaluator()
    r = ev.evaluate(
        target_id="T", sector=1,
        gaia_neighbors_within_60arcsec=2,
    )
    assert r.n_available == 1
    assert r.p_neb is not None


def test_evaluate_evidence_flags():
    ev = NEBScenarioEvaluator()
    r = ev.evaluate(
        target_id="T", sector=1,
        gaia_neighbors_within_60arcsec=20,
        brightest_neighbor_delta_mag=1.0,
        nearest_neighbor_arcsec=2.0,
    )
    assert "close_bright_neighbor" in r.evidence_flags
    assert "neighbor_density" in r.evidence_flags
