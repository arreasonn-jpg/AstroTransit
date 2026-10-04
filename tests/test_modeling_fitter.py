"""astrotransit/modeling/fitter.py için testler.

ModelingOrchestrator'ın MAP/MCMC karar akışını ve MCMC harmonizasyonunu
kapsar. _map_fitter ve _mcmc_fitter mocklanır; PyMC gerekmez.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from astrotransit.modeling.fitter import ModelingOrchestrator

# ────────────────────── Yardımcılar ──────────────────────

def _fake_priors():
    return SimpleNamespace(
        period=3.5, t0=100.0, rp_rs=0.1, impact_parameter=0.3,
        u1=0.3, u2=0.2, duration=0.1, period_err=0.01,
        rp_rs_bounds=(1e-4, 0.5),
    )


def _orchestrator(monkeypatch, **kwargs):
    """Gerçek __init__ çalıştır, sonra alt fitter'ları sahtele."""
    import astrotransit.modeling.fitter as mod
    import astrotransit.modeling.parameters as params_mod

    # PyMCFitter'ı tamamen devre dışı bırak (hızlı test)
    monkeypatch.setattr(mod, "_PYMC_AVAILABLE", False)
    monkeypatch.setattr(mod, "PyMCFitter", None)
    monkeypatch.setattr(mod, "MCMCFitResult", None)

    # TransitPriors.from_cascade yerine sabit fake döndür
    monkeypatch.setattr(
        params_mod.TransitPriors,
        "from_cascade",
        lambda *a, **k: _fake_priors(),
    )

    orch = ModelingOrchestrator(**kwargs)
    orch._map_fitter = MagicMock()
    return orch


def _fake_candidate(snr=5.0, target="TIC 123", sector=1):
    return SimpleNamespace(
        target_id=target,
        sector=sector,
        snr=snr,
    )


def _fake_map_result(success=True, **overrides):
    base = dict(
        success=success,
        period=3.5,
        period_err=0.01,
        t0=100.0,
        duration_hours=2.0,
        depth=0.001,
        depth_ppm=1000.0,
        rp_rs=0.1,
        rp_rs_err=0.005,
        impact_parameter=0.3,
        a_over_rs=10.0,
        inclination_deg=88.0,
        u1=0.3,
        u2=0.2,
        baseline=1.0,
        log_jitter=-8.0,
        log_likelihood=-100.0,
        semi_major_axis_au=0.04,
        stellar_density_gcm3=1.4,
        planet_radius_rearth=None,
        planet_radius_rjup=None,
        equilibrium_temperature_k=None,
        insolation_flux=None,
        transit_depth_ppm=1000.0,
        residuals=None,
        posteriors={},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _detrended(n=100):
    import numpy as np
    return SimpleNamespace(
        target_id="TIC 123",
        sector=1,
        time=np.linspace(100, 120, n),
        flux=np.ones(n),
        flux_err=np.full(n, 1e-4),
    )


# ═══════════════════════════════════════════════════════
# __init__
# ═══════════════════════════════════════════════════════

def test_init_default(monkeypatch):
    orch = _orchestrator(monkeypatch)
    assert orch.stellar_radius == 1.0
    assert orch.stellar_mass == 1.0
    assert orch.stellar_teff == 5778.0
    assert orch.force_mcmc is False
    assert orch.force_map is False
    assert orch._mcmc_fitter is None  # PyMC kapalı


def test_init_force_map(monkeypatch):
    orch = _orchestrator(monkeypatch, force_map=True)
    assert orch.force_map is True


def test_init_force_mcmc(monkeypatch):
    orch = _orchestrator(monkeypatch, force_mcmc=True)
    assert orch.force_mcmc is True


def test_init_with_stellar_params(monkeypatch):
    orch = _orchestrator(
        monkeypatch, stellar_radius=1.2, stellar_mass=1.1, stellar_teff=6000.0
    )
    assert orch.stellar_radius == 1.2
    assert orch.stellar_mass == 1.1
    assert orch.stellar_teff == 6000.0


# ═══════════════════════════════════════════════════════
# _should_run_mcmc
# ═══════════════════════════════════════════════════════

def test_should_run_mcmc_force_map_wins(monkeypatch):
    orch = _orchestrator(monkeypatch, force_map=True, force_mcmc=True)
    orch._mcmc_fitter = MagicMock()  # olsa bile
    assert orch._should_run_mcmc(_fake_candidate(snr=100)) is False


def test_should_run_mcmc_no_fitter(monkeypatch):
    orch = _orchestrator(monkeypatch)
    orch._mcmc_fitter = None
    assert orch._should_run_mcmc(_fake_candidate(snr=100)) is False


def test_should_run_mcmc_force_mcmc(monkeypatch):
    orch = _orchestrator(monkeypatch, force_mcmc=True)
    orch._mcmc_fitter = MagicMock()
    assert orch._should_run_mcmc(_fake_candidate(snr=1.0)) is True


def test_should_run_mcmc_auto_upgrade_disabled(monkeypatch):
    orch = _orchestrator(monkeypatch)
    orch._mcmc_fitter = MagicMock()
    orch._mcmc_auto_upgrade = False
    assert orch._should_run_mcmc(_fake_candidate(snr=100)) is False


def test_should_run_mcmc_snr_below_threshold(monkeypatch):
    orch = _orchestrator(monkeypatch)
    orch._mcmc_fitter = MagicMock()
    orch._mcmc_auto_upgrade = True
    orch._mcmc_snr_threshold = 10.0
    assert orch._should_run_mcmc(_fake_candidate(snr=5.0)) is False


def test_should_run_mcmc_snr_above_threshold(monkeypatch):
    orch = _orchestrator(monkeypatch)
    orch._mcmc_fitter = MagicMock()
    orch._mcmc_auto_upgrade = True
    orch._mcmc_snr_threshold = 10.0
    assert orch._should_run_mcmc(_fake_candidate(snr=15.0)) is True


# ═══════════════════════════════════════════════════════
# _posterior_center
# ═══════════════════════════════════════════════════════

def test_posterior_center_no_posteriors(monkeypatch):
    orch = _orchestrator(monkeypatch)
    assert orch._posterior_center(SimpleNamespace(), "x") is None


def test_posterior_center_missing_name(monkeypatch):
    orch = _orchestrator(monkeypatch)
    obj = SimpleNamespace(posteriors={"a": SimpleNamespace(median=1.0)})
    assert orch._posterior_center(obj, "b") is None


def test_posterior_center_median_attr(monkeypatch):
    orch = _orchestrator(monkeypatch)
    obj = SimpleNamespace(posteriors={"a": SimpleNamespace(median=2.5)})
    assert orch._posterior_center(obj, "a") == 2.5


def test_posterior_center_value_fallback(monkeypatch):
    orch = _orchestrator(monkeypatch)
    obj = SimpleNamespace(posteriors={"a": SimpleNamespace(value=3.7)})
    assert orch._posterior_center(obj, "a") == 3.7


def test_posterior_center_mean_fallback(monkeypatch):
    orch = _orchestrator(monkeypatch)
    obj = SimpleNamespace(posteriors={"a": SimpleNamespace(mean=4.2)})
    assert orch._posterior_center(obj, "a") == 4.2


def test_posterior_center_dict_post(monkeypatch):
    orch = _orchestrator(monkeypatch)
    obj = SimpleNamespace(posteriors={"a": {"median": 5.5}})
    assert orch._posterior_center(obj, "a") == 5.5


def test_posterior_center_invalid_value(monkeypatch):
    orch = _orchestrator(monkeypatch)
    obj = SimpleNamespace(posteriors={"a": SimpleNamespace(median="bad")})
    assert orch._posterior_center(obj, "a") is None


# ═══════════════════════════════════════════════════════
# _harmonize_mcmc_result
# ═══════════════════════════════════════════════════════

def _make_mcmc_result(**overrides):
    base = dict(
        period=3.4,
        period_err=None,
        t0=None,
        duration_hours=None,
        depth=None,
        depth_ppm=None,
        rp_rs=None,
        rp_rs_err=None,
        impact_parameter=None,
        a_over_rs=None,
        inclination_deg=None,
        u1=None,
        u2=None,
        baseline=None,
        log_jitter=None,
        log_likelihood=None,
        semi_major_axis_au=None,
        stellar_density_gcm3=None,
        planet_radius_rearth=None,
        planet_radius_rjup=None,
        equilibrium_temperature_k=None,
        insolation_flux=None,
        transit_depth_ppm=None,
        residuals=None,
        posteriors={},
        derived=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_harmonize_fills_missing_from_map(monkeypatch):
    orch = _orchestrator(monkeypatch)
    map_result = _fake_map_result(period=3.5, t0=100.0, rp_rs=0.1)
    mcmc = _make_mcmc_result(period=3.4, t0=None, rp_rs=None)
    out = orch._harmonize_mcmc_result(mcmc, map_result)
    assert out.t0 == 100.0
    assert out.rp_rs == 0.1


def test_harmonize_applies_posterior_centers(monkeypatch):
    orch = _orchestrator(monkeypatch)
    map_result = _fake_map_result()
    mcmc = _make_mcmc_result(
        posteriors={
            "t0": SimpleNamespace(median=999.0),
            "rp_rs": SimpleNamespace(median=0.15),
            "baseline": SimpleNamespace(median=1.001),
            "impact_parameter": SimpleNamespace(median=0.4),
            "log_jitter": SimpleNamespace(median=-7.0),
        }
    )
    out = orch._harmonize_mcmc_result(mcmc, map_result)
    assert out.t0 == 999.0
    assert out.rp_rs == 0.15
    assert out.baseline == 1.001
    assert out.impact_parameter == 0.4
    assert out.log_jitter == -7.0


def test_harmonize_fills_from_derived(monkeypatch):
    orch = _orchestrator(monkeypatch)
    # map'te bu 5 derived alanı None bırak ki derived'e sıra gelsin
    map_result = _fake_map_result(
        semi_major_axis_au=None,
        equilibrium_temperature_k=None,
        insolation_flux=None,
    )
    derived = SimpleNamespace(
        planet_radius_rearth=1.5,
        planet_radius_rjup=0.13,
        semi_major_axis_au=0.05,
        equilibrium_temperature_k=300.0,
        insolation_flux=1.2,
    )
    mcmc = _make_mcmc_result(derived=derived)
    out = orch._harmonize_mcmc_result(mcmc, map_result)
    assert out.planet_radius_rearth == 1.5
    assert out.planet_radius_rjup == 0.13
    assert out.semi_major_axis_au == 0.05
    assert out.equilibrium_temperature_k == 300.0
    assert out.insolation_flux == 1.2


def test_harmonize_sets_contract_labels(monkeypatch):
    orch = _orchestrator(monkeypatch)
    map_result = _fake_map_result()
    mcmc = _make_mcmc_result()
    out = orch._harmonize_mcmc_result(mcmc, map_result)
    assert out.period_sampled is False
    assert out.period_err_source == "fixed_in_mcmc"


def test_harmonize_period_err_none_when_zero(monkeypatch):
    orch = _orchestrator(monkeypatch)
    map_result = _fake_map_result()
    mcmc = _make_mcmc_result(period_err=0.0)
    out = orch._harmonize_mcmc_result(mcmc, map_result)
    assert out.period_err is None


# ═══════════════════════════════════════════════════════
# fit — MAP yolları
# ═══════════════════════════════════════════════════════

def test_fit_map_success_no_mcmc(monkeypatch):
    orch = _orchestrator(monkeypatch)
    map_result = _fake_map_result(success=True)
    orch._map_fitter.fit.return_value = map_result
    orch._mcmc_fitter = None  # MCMC kapalı

    result = orch.fit(_detrended(), _fake_candidate(snr=5.0))
    assert result is map_result


def test_fit_map_failure(monkeypatch):
    orch = _orchestrator(monkeypatch)
    map_result = _fake_map_result(success=False)
    orch._map_fitter.fit.return_value = map_result
    orch._mcmc_fitter = MagicMock()

    result = orch.fit(_detrended(), _fake_candidate(snr=100.0))
    assert result is map_result
    orch._mcmc_fitter.fit.assert_not_called()


def test_fit_mcmc_upgrade_success(monkeypatch):
    orch = _orchestrator(monkeypatch)
    map_result = _fake_map_result(success=True)
    orch._map_fitter.fit.return_value = map_result

    mcmc_success = _make_mcmc_result(period=3.45, posteriors={})
    mcmc_fitter = MagicMock()
    mcmc_fitter.fit.return_value = SimpleNamespace(
        success=True, **vars(mcmc_success)
    )
    orch._mcmc_fitter = mcmc_fitter
    orch._mcmc_snr_threshold = 5.0
    orch._mcmc_auto_upgrade = True

    result = orch.fit(_detrended(), _fake_candidate(snr=10.0))
    # harmonize edilmiş sonuç dönmeli, MAP değil
    assert result is not map_result
    assert result.period == 3.45


def test_fit_mcmc_failure_falls_back_to_map(monkeypatch):
    orch = _orchestrator(monkeypatch)
    map_result = _fake_map_result(success=True)
    orch._map_fitter.fit.return_value = map_result

    mcmc_fitter = MagicMock()
    mcmc_fitter.fit.return_value = SimpleNamespace(success=False)
    orch._mcmc_fitter = mcmc_fitter
    orch._mcmc_snr_threshold = 5.0
    orch._mcmc_auto_upgrade = True

    result = orch.fit(_detrended(), _fake_candidate(snr=10.0))
    assert result is map_result


def test_fit_mcmc_exception_falls_back(monkeypatch):
    orch = _orchestrator(monkeypatch)
    map_result = _fake_map_result(success=True)
    orch._map_fitter.fit.return_value = map_result

    mcmc_fitter = MagicMock()
    mcmc_fitter.fit.side_effect = RuntimeError("pymc crash")
    orch._mcmc_fitter = mcmc_fitter
    orch._mcmc_snr_threshold = 5.0
    orch._mcmc_auto_upgrade = True

    result = orch.fit(_detrended(), _fake_candidate(snr=10.0))
    assert result is map_result


def test_fit_force_mcmc_triggers_upgrade(monkeypatch):
    orch = _orchestrator(monkeypatch, force_mcmc=True)
    map_result = _fake_map_result(success=True)
    orch._map_fitter.fit.return_value = map_result

    mcmc_fitter = MagicMock()
    mcmc_fitter.fit.return_value = SimpleNamespace(
        success=True,
        period=3.45,
        posteriors={},
        period_err=None,
        t0=None,
        duration_hours=None,
        depth=None,
        depth_ppm=None,
        rp_rs=None,
        rp_rs_err=None,
        impact_parameter=None,
        a_over_rs=None,
        inclination_deg=None,
        u1=None,
        u2=None,
        baseline=None,
        log_jitter=None,
        log_likelihood=None,
        semi_major_axis_au=None,
        stellar_density_gcm3=None,
        planet_radius_rearth=None,
        planet_radius_rjup=None,
        equilibrium_temperature_k=None,
        insolation_flux=None,
        transit_depth_ppm=None,
        residuals=None,
        derived=None,
    )
    orch._mcmc_fitter = mcmc_fitter

    # SNR düşük olsa bile force_mcmc tetikler
    result = orch.fit(_detrended(), _fake_candidate(snr=1.0))
    assert result is not map_result
    mcmc_fitter.fit.assert_called_once()
