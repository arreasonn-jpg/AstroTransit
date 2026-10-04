"""astrotransit/validation/injection_recovery.py için testler."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from astrotransit.validation.injection_recovery import (
    InjectionRecoveryReport,
    InjectionScenario,
    RecoveryTrial,
    _extract_period,
    inject_box_transit,
    make_injection_grid,
    run_injection_recovery,
)


def _scenario(period=3.5, depth=0.001, duration=0.1, t0=100.0, label="default"):
    return InjectionScenario(period, depth, duration, t0, label)


def _fake_lc(n=1000, span=100.0):
    t = np.linspace(100.0, 100.0 + span, n)
    return t, np.ones(n)


# ═══════════════════════════════════════════════════════
# InjectionScenario
# ═══════════════════════════════════════════════════════

def test_scenario_validate_ok():
    _scenario().validate()


def test_scenario_invalid_period():
    with pytest.raises(ValueError, match="period"):
        _scenario(period=0.0).validate()


def test_scenario_invalid_duration():
    with pytest.raises(ValueError, match="duration"):
        _scenario(duration=0.0).validate()


def test_scenario_invalid_depth_high():
    with pytest.raises(ValueError, match="depth"):
        _scenario(depth=1.0).validate()


def test_scenario_invalid_depth_low():
    with pytest.raises(ValueError, match="depth"):
        _scenario(depth=0.0).validate()


# ═══════════════════════════════════════════════════════
# RecoveryTrial
# ═══════════════════════════════════════════════════════

def test_trial_to_dict():
    t = RecoveryTrial(
        scenario=_scenario(), detected=True,
        detected_period_days=3.51, period_error_fraction=0.003,
        reason="period_match",
    )
    d = t.to_dict()
    assert d["detected"] is True
    assert d["detected_period_days"] == 3.51
    assert d["scenario"]["period_days"] == 3.5


# ═══════════════════════════════════════════════════════
# InjectionRecoveryReport
# ═══════════════════════════════════════════════════════

def test_report_completeness_map():
    r = InjectionRecoveryReport(
        trials=(), completeness=0.5,
        completeness_by_label={"a": 0.8, "b": 0.2},
    )
    assert r.completeness_map == {"a": 0.8, "b": 0.2}


def test_report_to_dict():
    r = InjectionRecoveryReport(
        trials=(RecoveryTrial(_scenario(), True),),
        completeness=1.0, n_trials=1, n_recovered=1,
    )
    d = r.to_dict()
    assert d["n_trials"] == 1
    assert d["n_recovered"] == 1
    assert len(d["trials"]) == 1


# ═══════════════════════════════════════════════════════
# inject_box_transit
# ═══════════════════════════════════════════════════════

def test_inject_basic():
    t, f = _fake_lc()
    out = inject_box_transit(t, f, _scenario())
    assert out.shape == t.shape
    assert np.any(out < 1.0)  # transit daldırma yapılmış


def test_inject_shape_mismatch():
    with pytest.raises(ValueError, match="şekle"):
        inject_box_transit(np.array([1.0, 2.0]), np.array([1.0]), _scenario())


# ═══════════════════════════════════════════════════════
# _extract_period
# ═══════════════════════════════════════════════════════

def test_extract_none():
    assert _extract_period(None) is None
    assert _extract_period(False) is None


def test_extract_scalar():
    assert _extract_period(3.5) == 3.5
    assert _extract_period(np.float64(3.5)) == 3.5


def test_extract_scalar_inf():
    assert _extract_period(float("inf")) is None


def test_extract_dict_has_candidate_false():
    assert _extract_period({"has_candidate": False, "period": 3.5}) is None


def test_extract_dict_detected_false():
    assert _extract_period({"detected": False, "period": 3.5}) is None


def test_extract_dict_period_days():
    assert _extract_period({"period_days": 3.5}) == 3.5


def test_extract_dict_period():
    assert _extract_period({"period": 3.5}) == 3.5


def test_extract_dict_best_period():
    assert _extract_period({"best_period": 3.5}) == 3.5


def test_extract_object_detected_false():
    assert _extract_period(SimpleNamespace(detected=False)) is None


def test_extract_object_period():
    assert _extract_period(SimpleNamespace(period=3.5)) == 3.5


def test_extract_object_period_days():
    assert _extract_period(SimpleNamespace(period_days=3.5)) == 3.5


# ═══════════════════════════════════════════════════════
# run_injection_recovery
# ═══════════════════════════════════════════════════════

def test_run_invalid_tolerance():
    with pytest.raises(ValueError, match="period_tolerance"):
        run_injection_recovery(
            np.array([1.0]), np.array([1.0]), [], lambda t, f: 3.5,
            period_tolerance=0.0,
        )


def test_run_empty_scenarios():
    t, f = _fake_lc()
    r = run_injection_recovery(t, f, [], lambda t, f: 3.5)
    assert r.n_trials == 0
    assert r.completeness == 0.0


def test_run_detected_exact():
    t, f = _fake_lc()
    scenarios = [_scenario(period=3.5)]
    r = run_injection_recovery(t, f, scenarios, lambda t, f: 3.5)
    assert r.completeness == 1.0
    assert r.trials[0].reason == "period_match"


def test_run_period_mismatch():
    t, f = _fake_lc()
    scenarios = [_scenario(period=3.5)]
    r = run_injection_recovery(t, f, scenarios, lambda t, f: 5.0)
    assert r.completeness == 0.0
    assert r.trials[0].reason == "period_mismatch"


def test_run_no_period():
    t, f = _fake_lc()
    scenarios = [_scenario()]
    r = run_injection_recovery(t, f, scenarios, lambda t, f: None)
    assert r.trials[0].reason == "no_period"


def test_run_detector_error():
    t, f = _fake_lc()
    scenarios = [_scenario()]

    def bad(t, f):
        raise RuntimeError("boom")

    r = run_injection_recovery(t, f, scenarios, bad)
    assert "detector_error" in r.trials[0].reason


def test_run_multiple_labels():
    t, f = _fake_lc()
    scenarios = [
        _scenario(period=3.5, label="easy"),
        _scenario(period=3.5, label="easy"),
        _scenario(period=5.0, label="hard"),
    ]
    r = run_injection_recovery(t, f, scenarios, lambda t, f: 3.5, period_tolerance=0.01)
    assert r.n_trials == 3
    assert r.completeness_by_label["easy"] == 1.0
    assert r.completeness_by_label["hard"] == 0.0


def test_run_with_seed_and_provenance():
    t, f = _fake_lc()
    r = run_injection_recovery(
        t, f, [_scenario()], lambda t, f: 3.5,
        seed=42, provenance={"k": 1},
    )
    assert r.seed == 42
    assert r.provenance == {"k": 1}


# ═══════════════════════════════════════════════════════
# make_injection_grid
# ═══════════════════════════════════════════════════════

def test_make_grid_default():
    grid = make_injection_grid()
    # 9 periods × 7 depths × 3 durations = 189
    assert len(grid) == 189


def test_make_grid_custom():
    grid = make_injection_grid(
        periods_days=[1.0, 2.0], depths=[0.001], durations_days=[0.1], t0=5.0,
    )
    assert len(grid) == 2
    assert grid[0].t0 == 5.0
    assert "P=1" in grid[0].label


# ═══════════════════════════════════════════════════════
# _extract_period obje yolları (kalan coverage)
# ═══════════════════════════════════════════════════════

def test_extract_object_with_value_attr():
    """.value niteliği taşıyan obje (ör. astropy Quantity) unwrap edilir."""
    class _QuantityLike:
        def __init__(self, v):
            self.value = v
    obj = SimpleNamespace(period=_QuantityLike(3.5))
    assert _extract_period(obj) == 3.5


def test_extract_object_best_with_period():
    """result.best.period yolu."""
    best = SimpleNamespace(period=3.5)
    obj = SimpleNamespace(best=best)
    assert _extract_period(obj) == 3.5


def test_extract_object_best_returns_none():
    """result.best var ama period yok → None."""
    best = SimpleNamespace()  # no period/period_days
    obj = SimpleNamespace(best=best)
    assert _extract_period(obj) is None


def test_extract_object_best_dict():
    """result.best dict ise _extract_period onu da çözer."""
    obj = SimpleNamespace(best={"period_days": 3.5})
    assert _extract_period(obj) == 3.5


def test_extract_object_with_detected_attr_true():
    """detected=True olduğunda period'a devam edilir (191->194 branch)."""
    obj = SimpleNamespace(detected=True, period=3.5)
    assert _extract_period(obj) == 3.5
