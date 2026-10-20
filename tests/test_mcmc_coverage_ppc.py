"""run_mcmc_coverage_ppc sözleşme testleri.

Örnekleme içeren uçtan uca koşum ağır ve `slow` işaretlidir; normal sette
yalnız üretici determinismi + özet + kapı sözleşmesi test edilir.
"""

from __future__ import annotations

import numpy as np
import pytest

from scripts.validation.run_mcmc_coverage_ppc import (
    evaluate_gate,
    generate_case,
    summarize,
)


def test_generate_case_deterministic_given_seed():
    lc1, priors1, truth1 = generate_case(2026)
    lc2, priors2, truth2 = generate_case(2026)
    assert np.array_equal(lc1.time, lc2.time)
    assert np.array_equal(lc1.flux, lc2.flux)
    assert priors1.period == priors2.period == truth1["period"] == truth2["period"]
    # Markdown: priors gerçek değer etrafında (detection-conditioned kapsam)
    assert priors1.period_bounds[0] < truth1["period"] < priors1.period_bounds[1]
    assert 0.03 <= truth1["rp_rs"] <= 0.12
    assert 1.2 <= truth1["period"] <= 4.0


def test_summarize_counts_failures_and_coverage():
    truth = {"period": 2.0, "t0": 100.1, "rp_rs": 0.05, "impact_parameter": 0.3, "noise_frac": 200e-6}
    entries = [
        {
            "seed": 1, "state": "measured", "truth": truth,
            "hdi94_coverage": {"rp_rs": True, "t0": False, "impact_parameter": True},
            "ppc": {"residual_rms_per_sigma": 1.05},
            "r_hat_max": 1.02, "ess": {"rp_rs": 300, "t0": 280},
        },
        {
            "seed": 2, "state": "measured", "truth": truth,
            "hdi94_coverage": {"rp_rs": True, "t0": True, "impact_parameter": None},
            "ppc": {"residual_rms_per_sigma": 1.15},
            "r_hat_max": 1.04, "ess": {"rp_rs": 320},
        },
        {"seed": 3, "state": "map_failed"},
    ]
    summary = summarize(entries)
    assert summary["n_cases"] == 3
    assert summary["n_measured"] == 2
    assert summary["failure_states"] == {"map_failed": 1, "mcmc_failed": 0}
    assert summary["hdi94_coverage"]["rp_rs"] == 1.0
    assert summary["hdi94_coverage"]["t0"] == 0.5
    assert summary["hdi94_coverage_pooled"] == pytest.approx(4 / 5)
    assert summary["ppc_residual_rms_per_sigma_median"] == pytest.approx(1.10)
    assert summary["r_hat_max_median"] == pytest.approx(1.03)
    assert summary["ess_median"] == pytest.approx(300.0)


def test_gate_pass_and_fail_bands():
    summary = {
        "n_cases": 12, "n_measured": 12,
        "hdi94_coverage": {"rp_rs": 0.9, "t0": 1.0, "impact_parameter": 0.83},
        "hdi94_coverage_pooled": 0.9167,
        "ppc_residual_rms_per_sigma_median": 1.0,
        "r_hat_max_median": 1.03,
        "ess_median": 300.0,
    }
    status, reasons = evaluate_gate(
        summary,
        min_cases=12,
        coverage_floor=0.75,
        coverage_ceiling=1.0,
        ppc_rmse_floor=0.5,
        ppc_rmse_ceiling=1.5,
        r_hat_max=1.1,
        ess_min=100,
    )
    assert status == "measured"
    assert reasons == []

    collapsed = dict(summary, hdi94_coverage_pooled=0.4, n_measured=3, ess_median=40.0)
    status2, reasons2 = evaluate_gate(
        collapsed,
        min_cases=12,
        coverage_floor=0.75,
        coverage_ceiling=1.0,
        ppc_rmse_floor=0.5,
        ppc_rmse_ceiling=1.5,
        r_hat_max=1.1,
        ess_min=100,
    )
    assert status2 == "measured_fail"
    assert any("kapsama" in r for r in reasons2)
    assert any("n_measured" in r for r in reasons2)
    assert any("ess_median" in r for r in reasons2)


def test_gate_coverage_ceiling_prevents_overwide():
    overwide = {
        "n_cases": 12, "n_measured": 12,
        "hdi94_coverage_pooled": 1.0,
        "ppc_residual_rms_per_sigma_median": 1.0,
        "r_hat_max_median": 1.03,
        "ess_median": 300.0,
    }
    status, reasons = evaluate_gate(
        overwide,
        min_cases=12,
        coverage_floor=0.75,
        coverage_ceiling=0.98,
        ppc_rmse_floor=0.5,
        ppc_rmse_ceiling=1.5,
        r_hat_max=1.1,
        ess_min=100,
    )
    assert status == "measured_fail"
    assert any("aşırı geniş" in r for r in reasons)
