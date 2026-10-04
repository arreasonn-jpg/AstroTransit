"""astrotransit/quality/vetting.py için kapsamlı testler."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from astrotransit.quality.vetting import (
    FPP_METHOD,
    FalsePositiveVetter,
    VettingReport,
    VettingTest,
    VettingVerdict,
)


def _candidate(
    depth=0.001, period=3.5, duration=0.1, target="TIC 1", sector=1,
):
    return SimpleNamespace(
        target_id=target, sector=sector,
        depth=depth, period=period, duration=duration,
    )


def _metrics(
    odd_even=0.0, secondary=0.0, variable=False, amplitude=0.0,
    depth_var=0.0, n_transits=5, symmetry=0.5, completeness=0.95,
):
    return SimpleNamespace(
        transit=SimpleNamespace(
            odd_even_mismatch=odd_even,
            depth_variance=depth_var,
            n_transits=n_transits,
            transit_symmetry=symmetry,
        ),
        stellar=SimpleNamespace(
            secondary_eclipse_depth=secondary,
            is_variable_star=variable,
            variability_amplitude=amplitude,
        ),
        photometric=SimpleNamespace(data_completeness=completeness),
    )


# ═══════════════════════════════════════════════════════
# VettingVerdict + VettingTest + VettingReport
# ═══════════════════════════════════════════════════════

def test_verdict_enum():
    assert VettingVerdict.PASS.value == "pass"
    assert VettingVerdict.FAIL.value == "fail"
    assert VettingVerdict.WARN.value == "warn"
    assert VettingVerdict.SKIP.value == "skip"


def test_vetting_test_to_dict():
    t = VettingTest(
        name="x", verdict=VettingVerdict.FAIL, value=0.5, threshold=0.3,
        description="bad", fp_weight=0.25,
    )
    d = t.to_dict()
    assert d["name"] == "x"
    assert d["verdict"] == "fail"
    assert d["value"] == 0.5
    assert d["fp_weight"] == 0.25


def test_vetting_report_to_dict():
    t = VettingTest("x", VettingVerdict.PASS, 0.1, 0.3)
    r = VettingReport(
        target_id="TIC 1", sector=1, tests=[t],
        n_pass=1, false_positive_probability=0.05,
    )
    d = r.to_dict()
    assert d["target_id"] == "TIC 1"
    assert d["n_tests"] == 1
    assert d["false_positive_probability"] == 0.05
    assert d["fpp_method"] == FPP_METHOD


def test_vetting_report_to_dict_none_fpp():
    r = VettingReport(target_id="T", sector=1, false_positive_probability=None)
    d = r.to_dict()
    assert d["false_positive_probability"] is None


def test_vetting_report_summary():
    r = VettingReport(
        target_id="T", sector=1, n_pass=5, n_warn=1, n_fail=2,
        false_positive_probability=0.25, fp_flags=["x"],
    )
    s = r.summary()
    assert s["pass/warn/fail"] == "5/1/2"
    assert s["fpp"] == 0.25
    assert s["is_fp"] is False


def test_vetting_report_summary_none_fpp():
    r = VettingReport(target_id="T", sector=1)
    assert r.summary()["fpp"] is None


# ═══════════════════════════════════════════════════════
# __init__
# ═══════════════════════════════════════════════════════

def test_init_defaults():
    v = FalsePositiveVetter()
    assert v.odd_even_threshold == 3.0
    assert v.secondary_eclipse_threshold == 0.5
    assert v.max_depth_ratio == 0.5


def test_init_custom():
    v = FalsePositiveVetter(
        odd_even_threshold=5.0, secondary_eclipse_threshold=0.3,
        max_depth_ratio=0.4, variability_amplitude_threshold=1000.0,
        depth_variance_threshold=0.3,
        min_duration_period_ratio=0.01, max_duration_period_ratio=0.2,
    )
    assert v.odd_even_threshold == 5.0
    assert v.min_duration_period_ratio == 0.01


# ═══════════════════════════════════════════════════════
# _test_odd_even
# ═══════════════════════════════════════════════════════

def test_odd_even_skip_when_zero():
    v = FalsePositiveVetter()
    t = v._test_odd_even(_candidate(), _metrics(odd_even=0.0))
    assert t.verdict == VettingVerdict.SKIP


def test_odd_even_fail():
    v = FalsePositiveVetter(odd_even_threshold=3.0)
    t = v._test_odd_even(_candidate(), _metrics(odd_even=5.0))
    assert t.verdict == VettingVerdict.FAIL
    assert t.fp_weight == 0.25


def test_odd_even_warn():
    v = FalsePositiveVetter(odd_even_threshold=3.0)
    t = v._test_odd_even(_candidate(), _metrics(odd_even=2.5))
    assert t.verdict == VettingVerdict.WARN


def test_odd_even_pass():
    v = FalsePositiveVetter(odd_even_threshold=3.0)
    t = v._test_odd_even(_candidate(), _metrics(odd_even=1.0))
    assert t.verdict == VettingVerdict.PASS


# ═══════════════════════════════════════════════════════
# _test_secondary_eclipse
# ═══════════════════════════════════════════════════════

def test_secondary_fail():
    v = FalsePositiveVetter(secondary_eclipse_threshold=0.5)
    # depth=0.01, secondary=0.006 → ratio 0.6 > 0.5 → FAIL
    t = v._test_secondary_eclipse(
        _candidate(depth=0.01), _metrics(secondary=0.006),
    )
    assert t.verdict == VettingVerdict.FAIL


def test_secondary_warn():
    v = FalsePositiveVetter(secondary_eclipse_threshold=0.5)
    # depth=0.01, threshold=0.005, secondary=0.003 → > 0.0025 (half) → WARN
    t = v._test_secondary_eclipse(
        _candidate(depth=0.01), _metrics(secondary=0.003),
    )
    assert t.verdict == VettingVerdict.WARN


def test_secondary_pass():
    v = FalsePositiveVetter(secondary_eclipse_threshold=0.5)
    t = v._test_secondary_eclipse(
        _candidate(depth=0.01), _metrics(secondary=0.0001),
    )
    assert t.verdict == VettingVerdict.PASS


# ═══════════════════════════════════════════════════════
# _test_depth_limit
# ═══════════════════════════════════════════════════════

def test_depth_limit_fail():
    v = FalsePositiveVetter(max_depth_ratio=0.5)
    t = v._test_depth_limit(_candidate(depth=0.6))
    assert t.verdict == VettingVerdict.FAIL


def test_depth_limit_warn():
    v = FalsePositiveVetter(max_depth_ratio=0.5)
    # 0.45 > 0.5*0.8=0.4 → WARN
    t = v._test_depth_limit(_candidate(depth=0.45))
    assert t.verdict == VettingVerdict.WARN


def test_depth_limit_pass():
    v = FalsePositiveVetter(max_depth_ratio=0.5)
    t = v._test_depth_limit(_candidate(depth=0.01))
    assert t.verdict == VettingVerdict.PASS


# ═══════════════════════════════════════════════════════
# _test_stellar_variability
# ═══════════════════════════════════════════════════════

def test_variability_not_variable():
    v = FalsePositiveVetter()
    t = v._test_stellar_variability(_metrics(variable=False, amplitude=100.0))
    assert t.verdict == VettingVerdict.PASS


def test_variability_fail_high_amplitude():
    v = FalsePositiveVetter(variability_amplitude_threshold=5000.0)
    t = v._test_stellar_variability(
        _metrics(variable=True, amplitude=10000.0),
    )
    assert t.verdict == VettingVerdict.FAIL


def test_variability_warn_low_amplitude():
    v = FalsePositiveVetter(variability_amplitude_threshold=5000.0)
    t = v._test_stellar_variability(
        _metrics(variable=True, amplitude=1000.0),
    )
    assert t.verdict == VettingVerdict.WARN


# ═══════════════════════════════════════════════════════
# _test_depth_variance
# ═══════════════════════════════════════════════════════

def test_depth_variance_skip_low_transits():
    v = FalsePositiveVetter()
    t = v._test_depth_variance(_candidate(), _metrics(n_transits=2))
    assert t.verdict == VettingVerdict.SKIP


def test_depth_variance_skip_zero_depth():
    v = FalsePositiveVetter()
    t = v._test_depth_variance(_candidate(depth=0.0), _metrics(n_transits=5))
    assert t.verdict == VettingVerdict.SKIP


def test_depth_variance_warn():
    v = FalsePositiveVetter(depth_variance_threshold=0.5)
    # depth=0.01, var=0.0001 → std=0.01, norm=1.0 > 0.5 → WARN
    t = v._test_depth_variance(
        _candidate(depth=0.01), _metrics(depth_var=0.0001, n_transits=5),
    )
    assert t.verdict == VettingVerdict.WARN


def test_depth_variance_pass():
    v = FalsePositiveVetter(depth_variance_threshold=0.5)
    # depth=0.01, var=1e-8 → std=1e-4, norm=0.01 < 0.5 → PASS
    t = v._test_depth_variance(
        _candidate(depth=0.01), _metrics(depth_var=1e-8, n_transits=5),
    )
    assert t.verdict == VettingVerdict.PASS


# ═══════════════════════════════════════════════════════
# _test_duration_period_ratio
# ═══════════════════════════════════════════════════════

def test_duration_period_skip_zero_period():
    v = FalsePositiveVetter()
    t = v._test_duration_period_ratio(_candidate(period=0.0))
    assert t.verdict == VettingVerdict.SKIP


def test_duration_period_fail_too_small():
    v = FalsePositiveVetter(min_duration_period_ratio=0.001)
    t = v._test_duration_period_ratio(_candidate(period=100.0, duration=0.01))
    # ratio = 0.0001 < 0.001 → FAIL
    assert t.verdict == VettingVerdict.FAIL


def test_duration_period_fail_too_large():
    v = FalsePositiveVetter(max_duration_period_ratio=0.25)
    t = v._test_duration_period_ratio(_candidate(period=1.0, duration=0.5))
    # ratio = 0.5 > 0.25 → FAIL
    assert t.verdict == VettingVerdict.FAIL


def test_duration_period_pass():
    v = FalsePositiveVetter()
    t = v._test_duration_period_ratio(_candidate(period=3.5, duration=0.1))
    # ratio = 0.0286 → PASS
    assert t.verdict == VettingVerdict.PASS


# ═══════════════════════════════════════════════════════
# _test_transit_symmetry
# ═══════════════════════════════════════════════════════

def test_symmetry_skip_zero():
    v = FalsePositiveVetter()
    t = v._test_transit_symmetry(_metrics(symmetry=0.0))
    assert t.verdict == VettingVerdict.SKIP


def test_symmetry_warn():
    v = FalsePositiveVetter()
    t = v._test_transit_symmetry(_metrics(symmetry=0.1))
    assert t.verdict == VettingVerdict.WARN


def test_symmetry_pass():
    v = FalsePositiveVetter()
    t = v._test_transit_symmetry(_metrics(symmetry=0.9))
    assert t.verdict == VettingVerdict.PASS


# ═══════════════════════════════════════════════════════
# _test_data_completeness
# ═══════════════════════════════════════════════════════

def test_completeness_warn():
    v = FalsePositiveVetter()
    t = v._test_data_completeness(_metrics(completeness=0.5))
    assert t.verdict == VettingVerdict.WARN


def test_completeness_pass():
    v = FalsePositiveVetter()
    t = v._test_data_completeness(_metrics(completeness=0.95))
    assert t.verdict == VettingVerdict.PASS


# ═══════════════════════════════════════════════════════
# _compute_fpp
# ═══════════════════════════════════════════════════════

def test_compute_fpp_no_measurable():
    v = FalsePositiveVetter()
    tests = [VettingTest("x", VettingVerdict.SKIP, 0.0, 0.0)]
    assert v._compute_fpp(tests) is None


def test_compute_fpp_all_pass():
    v = FalsePositiveVetter()
    tests = [
        VettingTest("a", VettingVerdict.PASS, 0.0, 0.0, fp_weight=0.25),
        VettingTest("b", VettingVerdict.PASS, 0.0, 0.0, fp_weight=0.25),
    ]
    assert v._compute_fpp(tests) == 0.0


def test_compute_fpp_with_fails():
    v = FalsePositiveVetter()
    tests = [
        VettingTest("a", VettingVerdict.FAIL, 0.0, 0.0, fp_weight=0.25),
        VettingTest("b", VettingVerdict.PASS, 0.0, 0.0, fp_weight=0.25),
    ]
    # 0.25 / 0.5 = 0.5
    assert v._compute_fpp(tests) == 0.5


def test_compute_fpp_with_warns():
    v = FalsePositiveVetter()
    tests = [
        VettingTest("a", VettingVerdict.WARN, 0.0, 0.0, fp_weight=0.25),
        VettingTest("b", VettingVerdict.PASS, 0.0, 0.0, fp_weight=0.25),
    ]
    # 0.25*0.3 / 0.5 = 0.15
    assert v._compute_fpp(tests) == pytest.approx(0.15)


def test_compute_fpp_clipped():
    v = FalsePositiveVetter()
    tests = [
        VettingTest("a", VettingVerdict.FAIL, 0.0, 0.0, fp_weight=1.0),
    ]
    assert v._compute_fpp(tests) == 1.0


# ═══════════════════════════════════════════════════════
# vet() integration
# ═══════════════════════════════════════════════════════

def test_vet_clean_candidate():
    v = FalsePositiveVetter()
    c = _candidate(depth=0.001, period=3.5, duration=0.1)
    m = _metrics(
        odd_even=0.5, secondary=0.00001, variable=False, amplitude=50.0,
        depth_var=1e-10, n_transits=5, symmetry=0.9, completeness=0.95,
    )
    r = v.vet(c, m)
    assert isinstance(r, VettingReport)
    assert r.n_fail == 0
    assert r.is_false_positive is False


def test_vet_eb_candidate():
    v = FalsePositiveVetter()
    c = _candidate(depth=0.001, period=3.5, duration=0.1)
    m = _metrics(
        odd_even=10.0,  # FAIL
        secondary=0.005,  # FAIL (depth 0.001)
        variable=True, amplitude=20000.0,  # FAIL
        depth_var=0.0001, n_transits=5, symmetry=0.5, completeness=0.95,
    )
    r = v.vet(c, m)
    assert r.n_fail >= 2
    assert r.is_false_positive is True
    assert len(r.fp_flags) >= 2


def test_vet_fp_by_fpp_threshold():
    v = FalsePositiveVetter()
    c = _candidate(depth=0.001)
    # Tek bir FAIL + diğerleri PASS → FPP oranı > 0.5 olabilir
    m = _metrics(
        odd_even=10.0,  # FAIL (weight 0.25)
        secondary=0.0, variable=False, amplitude=0.0,
        depth_var=0.0, n_transits=5, symmetry=0.0, completeness=0.0,
    )
    r = v.vet(c, m)
    # FPP hesabına katkı: FAIL weight 0.25, total weight = 0.25 (odd_even) + 0.25 (secondary) + 0.15 (depth) + 0.1 (stellar) + 0.05 (completeness) = 0.8
    # FPP = 0.25 / 0.8 ≈ 0.3125 → is_FP False (n_fail=1, fpp < 0.5)
    assert r.n_fail >= 1


def test_vet_all_skipped():
    v = FalsePositiveVetter()
    c = _candidate(depth=0.001, period=0.0)
    m = _metrics(
        odd_even=0.0, secondary=0.0, variable=False, amplitude=0.0,
        depth_var=0.0, n_transits=2, symmetry=0.0, completeness=0.0,
    )
    r = v.vet(c, m)
    # Bazıları SKIP, bazıları WARN/PASS
    assert r.false_positive_probability is not None
