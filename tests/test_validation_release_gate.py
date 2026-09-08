"""Regression tests for evidence-gated validation contracts."""
from types import SimpleNamespace

import numpy as np
import pytest

from astrotransit.validation.claims import ClaimEvidenceError, ClaimStatus, infer_claim_status, validate_claim
from astrotransit.validation.fpp_benchmark import FPPBenchmarkCase, evaluate_fpp_benchmark
from astrotransit.validation.injection_recovery import InjectionScenario, make_injection_grid, run_injection_recovery


def test_claim_firewall_does_not_promote_a_detection() -> None:
    result = SimpleNamespace(cascade_confirmed=True, followup_confirmed=False)
    assert infer_claim_status(result) == ClaimStatus.PHOTOMETRIC_PLANET_CANDIDATE
    with pytest.raises(ClaimEvidenceError):
        validate_claim(result, ClaimStatus.CONFIRMED_PLANET)


def test_injection_grid_has_expected_experimental_dimensions() -> None:
    grid = make_injection_grid(periods_days=(1, 10), depths=(1e-4, 1e-3), durations_days=(.1,))
    assert len(grid) == 4
    assert all(item.period_days > 0 for item in grid)


def test_injection_report_preserves_seed_and_unknowns() -> None:
    time = np.linspace(0, 10, 1000)
    flux = np.ones_like(time)
    scenario = InjectionScenario(2.0, 1e-3, .1, 0.0)
    report = run_injection_recovery(time, flux, [scenario], lambda _t, _f: {"period": 2.0}, seed=7)
    assert report.completeness == 1.0
    assert report.seed == 7
    assert report.provenance["random_seed"] == 7


def test_fpp_report_contains_holdout_calibration_metrics() -> None:
    report = evaluate_fpp_benchmark([
        FPPBenchmarkCase("fp", True, .9),
        FPPBenchmarkCase("planet", False, .1),
    ])
    assert report.brier_score == pytest.approx(.01)
    assert report.expected_calibration_error is not None
    assert report.roc_auc == pytest.approx(1.0)
    assert report.pr_auc is not None
