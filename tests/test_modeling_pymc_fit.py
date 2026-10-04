"""astrotransit/modeling/pymc_fit.py için testler.

PosteriorSummary ve MCMCFitResult veri modelleri + PyMCFitter'ın
posterior çıkarma mantığı test edilir. Gerçek PyMC örneklemesi
çalıştırılmaz (pm.sample ve pm.Model mocklanır).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from astrotransit.modeling.pymc_fit import (
    MCMCFitResult,
    PosteriorSummary,
    PyMCFitter,
)

# ═══════════════════════════════════════════════════════
# PosteriorSummary
# ═══════════════════════════════════════════════════════

def test_posterior_summary_to_dict():
    s = PosteriorSummary(
        name="rp_rs", mean=0.1, std=0.005, median=0.099,
        hdi_3=0.09, hdi_97=0.11, r_hat=1.002, ess=1500.0,
    )
    d = s.to_dict()
    assert d["name"] == "rp_rs"
    assert d["mean"] == 0.1
    assert d["std"] == 0.005
    assert d["median"] == 0.099
    assert d["hdi_3pct"] == 0.09
    assert d["hdi_97pct"] == 0.11
    assert d["r_hat"] == 1.002
    assert d["ess"] == 1500.0


def test_posterior_summary_defaults():
    s = PosteriorSummary(
        name="t0", mean=100.0, std=0.01, median=100.0,
        hdi_3=99.9, hdi_97=100.1,
    )
    assert s.r_hat == 1.0
    assert s.ess == 0.0


# ═══════════════════════════════════════════════════════
# MCMCFitResult
# ═══════════════════════════════════════════════════════

def test_mcmc_result_to_dict_basic():
    r = MCMCFitResult(target_id="TIC 123", sector=1, success=True)
    d = r.to_dict()
    assert d["target_id"] == "TIC 123"
    assert d["sector"] == 1
    assert d["success"] is True
    assert d["fit_method"] == "mcmc"
    assert "posteriors" in d


def test_mcmc_result_to_dict_with_posteriors():
    ps = PosteriorSummary(
        name="t0", mean=100.0, std=0.01, median=100.0,
        hdi_3=99.9, hdi_97=100.1,
    )
    r = MCMCFitResult(
        target_id="TIC 1", sector=1, success=True,
        posteriors={"t0": ps},
    )
    d = r.to_dict()
    assert "t0" in d["posteriors"]
    assert d["posteriors"]["t0"]["name"] == "t0"


def test_mcmc_result_summary_equals_to_dict():
    r = MCMCFitResult(target_id="TIC 1", sector=1, success=True)
    assert r.summary() == r.to_dict()


def test_mcmc_result_defaults():
    r = MCMCFitResult(target_id="TIC 1", sector=1, success=False)
    assert r.r_hat_max == 99.0
    assert r.n_divergences == 0
    assert r.convergence_ok is False
    assert r.mcmc_quality == "MCMC_FAILED_DIAGNOSTICS"


# ═══════════════════════════════════════════════════════
# PyMCFitter.__init__
# ═══════════════════════════════════════════════════════

def test_pymc_fitter_init_requires_pymc(monkeypatch):
    import astrotransit.modeling.pymc_fit as mod
    monkeypatch.setattr(mod, "_PYMC_AVAILABLE", False)
    with pytest.raises(ImportError, match="pymc"):
        PyMCFitter()


def test_pymc_fitter_init_requires_exoplanet(monkeypatch):
    import astrotransit.modeling.pymc_fit as mod
    monkeypatch.setattr(mod, "_PYMC_AVAILABLE", True)
    monkeypatch.setattr(mod, "_EXOPLANET_AVAILABLE", False)
    with pytest.raises(ImportError, match="exoplanet"):
        PyMCFitter()


def test_pymc_fitter_init_ok(monkeypatch):
    import astrotransit.modeling.pymc_fit as mod
    monkeypatch.setattr(mod, "_PYMC_AVAILABLE", True)
    monkeypatch.setattr(mod, "_EXOPLANET_AVAILABLE", True)
    f = PyMCFitter(chains=4, draws=500, tune=200, target_accept=0.8, random_seed=7)
    assert f.chains == 4
    assert f.draws == 500
    assert f.tune == 200
    assert f.target_accept == 0.8
    assert f.random_seed == 7


# ═══════════════════════════════════════════════════════
# _extract_posterior_summary
# ═══════════════════════════════════════════════════════

class _FakeVar:
    """arr.values benzeri."""
    def __init__(self, arr):
        self.values = np.asarray(arr)


class _FakeIdata:
    def __init__(self, posterior_dict):
        self.posterior = {k: _FakeVar(v) for k, v in posterior_dict.items()}
        self.sample_stats = SimpleNamespace(diverging=_FakeVar([[0, 0], [0, 0]]))


def _make_fitter(monkeypatch):
    import astrotransit.modeling.pymc_fit as mod
    monkeypatch.setattr(mod, "_PYMC_AVAILABLE", True)
    monkeypatch.setattr(mod, "_EXOPLANET_AVAILABLE", True)
    return PyMCFitter(chains=2, draws=100, tune=50)


def test_extract_missing_param(monkeypatch):
    f = _make_fitter(monkeypatch)
    idata = _FakeIdata({"a": np.array([1.0, 2.0])})
    assert f._extract_posterior_summary(idata, "missing") is None


def test_extract_empty_samples(monkeypatch):
    f = _make_fitter(monkeypatch)
    idata = _FakeIdata({"a": np.array([])})
    assert f._extract_posterior_summary(idata, "a") is None


def test_extract_basic_stats(monkeypatch):
    f = _make_fitter(monkeypatch)
    samples = np.random.default_rng(0).normal(0.1, 0.01, 1000)
    idata = _FakeIdata({"a": samples})
    s = f._extract_posterior_summary(idata, "a")
    assert s is not None
    assert s.name == "a"
    assert abs(s.mean - 0.1) < 0.01
    assert s.std > 0
    assert s.hdi_3 < s.median < s.hdi_97


def test_extract_single_sample(monkeypatch):
    f = _make_fitter(monkeypatch)
    idata = _FakeIdata({"a": np.array([5.0])})
    s = f._extract_posterior_summary(idata, "a")
    assert s is not None
    assert s.std == 0.0


def test_extract_arviz_rhat_fallback(monkeypatch):
    f = _make_fitter(monkeypatch)
    idata = _FakeIdata({"a": np.array([1.0, 2.0, 3.0])})
    # arviz importable ama hata veriyor gibi
    with patch("astrotransit.modeling.pymc_fit._ARVIZ_AVAILABLE", False):
        s = f._extract_posterior_summary(idata, "a")
    assert s is not None
    assert s.r_hat == 99.0  # fallback
    assert s.ess == 0.0


# ═══════════════════════════════════════════════════════
# _failed_result
# ═══════════════════════════════════════════════════════

def test_failed_result(monkeypatch):
    f = _make_fitter(monkeypatch)
    r = f._failed_result("TIC 123", 14, "test reason")
    assert isinstance(r, MCMCFitResult)
    assert r.target_id == "TIC 123"
    assert r.sector == 14
    assert r.success is False


# ═══════════════════════════════════════════════════════
# fit — hata yolu (PyMC context patlar)
# ═══════════════════════════════════════════════════════

def test_fit_pymc_error_returns_failed(monkeypatch):
    f = _make_fitter(monkeypatch)
    import astrotransit.modeling.pymc_fit as mod

    # pm.Model patlat
    class _BrokenModel:
        def __enter__(self):
            raise RuntimeError("model init failed")
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod, "pm", MagicMock(Model=lambda *a, **k: _BrokenModel()), raising=False)

    detrended = SimpleNamespace(
        target_id="TIC 1", sector=1,
        time=np.linspace(0, 1, 10),
        flux=np.ones(10),
        flux_err=np.full(10, 1e-4),
    )
    priors = SimpleNamespace(
        period=3.5, t0=100.0, rp_rs=0.1, impact_parameter=0.3,
        u1=0.3, u2=0.2, duration=0.1,
        rp_rs_bounds=(1e-4, 0.5),
    )
    r = f.fit(detrended, priors)
    assert r.success is False


def test_fit_full_flow_with_mocks(monkeypatch):
    """fit() gövdesini tamamen mock'larla kapsar (PyMC çalıştırmadan)."""
    f = _make_fitter(monkeypatch)
    import astrotransit.modeling.pymc_fit as mod

    # ── Fake idata ──
    class _Var:
        def __init__(self, arr):
            self.values = arr

    rng = np.random.default_rng(0)
    class _Idata:
        def __init__(self):
            self.posterior = {
                "rp_rs": _Var(rng.normal(0.1, 0.005, 500)),
                "t0": _Var(rng.normal(100.0, 0.01, 500)),
                "impact_parameter": _Var(rng.normal(0.3, 0.01, 500)),
                "log_jitter": _Var(rng.normal(-8.0, 0.2, 500)),
                "baseline": _Var(rng.normal(1.0, 0.001, 500)),
            }
            self.sample_stats = SimpleNamespace(
                diverging=_Var(np.zeros((2, 500), dtype=int))
            )

    # ── Fake pm ──
    def _make_fake_pm(idata):
        fake_pm = MagicMock()
        fake_pm.Model.return_value.__enter__.return_value = MagicMock()
        fake_pm.Model.return_value.__exit__.return_value = False
        fake_pm.sample.return_value = idata

        # Tüm pm dağılım/metin fonksiyonları scalar döndürsün
        fake_pm.Data.side_effect = lambda name, val: val
        fake_pm.Deterministic.side_effect = lambda name, expr: expr
        # pm.Normal / TruncatedNormal sadece prior kaydı için çağrılır;
        # mu array olabilir (obs likelihood), float() cast'i yapma.
        fake_pm.Normal.side_effect = lambda name, **kw: kw.get(
            "initval", kw.get("mu", 1.0)
        )
        fake_pm.TruncatedNormal.side_effect = lambda name, **kw: kw.get(
            "initval", kw.get("mu", 1.0)
        )

        class _Math:
            @staticmethod
            def exp(x):
                return np.exp(np.asarray(x, dtype=float))
            @staticmethod
            def sqrt(x):
                return np.sqrt(np.asarray(x, dtype=float))
            @staticmethod
            def sum(x, axis=None):
                return np.sum(np.asarray(x), axis=axis)
        fake_pm.math = _Math()
        return fake_pm

    monkeypatch.setattr(mod, "pm", _make_fake_pm(_Idata()), raising=False)

    # ── Fake xo ──
    fake_lc_obj = MagicMock()
    fake_lc_obj.get_light_curve.return_value = np.zeros((10, 1))
    fake_xo = MagicMock()
    fake_xo.LimbDarkLightCurve.return_value = fake_lc_obj
    monkeypatch.setattr(mod, "xo", fake_xo, raising=False)

    # ── Fake arviz ──
    fake_az = MagicMock()
    fake_az.rhat.side_effect = Exception("no rhat")
    fake_az.ess.side_effect = Exception("no ess")
    monkeypatch.setattr(mod, "az", fake_az, raising=False)
    monkeypatch.setattr(mod, "_ARVIZ_AVAILABLE", False)

    # ── Fake TransitModel ──
    fake_tm_cls = MagicMock()
    fake_tm_cls.compute_a_over_rs.return_value = 10.0
    fake_tm_cls.impact_to_inclination.return_value = 88.0
    import astrotransit.modeling.transit_model as tm_mod
    monkeypatch.setattr(tm_mod, "TransitModel", fake_tm_cls)

    # ── Fake derived ──
    fake_derived = SimpleNamespace(
        planet_radius_rearth=1.0, planet_radius_rjup=0.1,
        semi_major_axis_au=0.05, equilibrium_temperature_k=300.0,
        insolation_flux=1.0, to_dict=lambda: {},
    )
    monkeypatch.setattr(mod, "compute_derived_parameters", lambda **k: fake_derived)

    detrended = SimpleNamespace(
        target_id="TIC 1", sector=1,
        time=np.linspace(0, 1, 10),
        flux=np.ones(10), flux_err=np.full(10, 1e-4),
    )
    priors = SimpleNamespace(
        period=3.5, t0=100.0, rp_rs=0.1, impact_parameter=0.3,
        u1=0.3, u2=0.2, duration=0.1,
        rp_rs_bounds=(1e-4, 0.5),
    )

    r = f.fit(detrended, priors)
    assert isinstance(r, MCMCFitResult)
    assert r.target_id == "TIC 1"
    assert r.sector == 1
    assert len(r.posteriors) == 5
    mod.pm.sample.assert_called_once()


def test_fit_with_map_result_init(monkeypatch):
    """map_result verildiğinde init değerleri MAP'tan alınır."""
    f = _make_fitter(monkeypatch)
    import astrotransit.modeling.pymc_fit as mod

    class _Var:
        def __init__(self, arr):
            self.values = arr

    rng = np.random.default_rng(0)
    class _Idata:
        def __init__(self):
            self.posterior = {
                "rp_rs": _Var(rng.normal(0.1, 0.005, 500)),
                "t0": _Var(rng.normal(100.0, 0.01, 500)),
                "impact_parameter": _Var(rng.normal(0.3, 0.01, 500)),
                "log_jitter": _Var(rng.normal(-8.0, 0.2, 500)),
                "baseline": _Var(rng.normal(1.0, 0.001, 500)),
            }
            self.sample_stats = SimpleNamespace(
                diverging=_Var(np.zeros((2, 500), dtype=int))
            )

    def _make_fake_pm(idata):
        fake_pm = MagicMock()
        fake_pm.Model.return_value.__enter__.return_value = MagicMock()
        fake_pm.sample.return_value = idata
        fake_pm.Data.side_effect = lambda name, val: val
        fake_pm.Deterministic.side_effect = lambda name, expr: expr
        # pm.Normal / TruncatedNormal sadece prior kaydı için çağrılır;
        # mu array olabilir (obs likelihood), float() cast'i yapma.
        fake_pm.Normal.side_effect = lambda name, **kw: kw.get(
            "initval", kw.get("mu", 1.0)
        )
        fake_pm.TruncatedNormal.side_effect = lambda name, **kw: kw.get(
            "initval", kw.get("mu", 1.0)
        )

        class _Math:
            @staticmethod
            def exp(x):
                return np.exp(np.asarray(x, dtype=float))
            @staticmethod
            def sqrt(x):
                return np.sqrt(np.asarray(x, dtype=float))
            @staticmethod
            def sum(x, axis=None):
                return np.sum(np.asarray(x), axis=axis)
        fake_pm.math = _Math()
        return fake_pm

    monkeypatch.setattr(mod, "pm", _make_fake_pm(_Idata()), raising=False)

    fake_lc_obj = MagicMock()
    fake_lc_obj.get_light_curve.return_value = np.zeros((10, 1))
    fake_xo = MagicMock()
    fake_xo.LimbDarkLightCurve.return_value = fake_lc_obj
    monkeypatch.setattr(mod, "xo", fake_xo, raising=False)

    monkeypatch.setattr(mod, "_ARVIZ_AVAILABLE", False)
    monkeypatch.setattr(mod, "az", MagicMock(), raising=False)

    fake_tm_cls = MagicMock()
    fake_tm_cls.compute_a_over_rs.return_value = 10.0
    fake_tm_cls.impact_to_inclination.return_value = 88.0
    import astrotransit.modeling.transit_model as tm_mod
    monkeypatch.setattr(tm_mod, "TransitModel", fake_tm_cls)

    fake_derived = SimpleNamespace(
        planet_radius_rearth=1.0, planet_radius_rjup=0.1,
        semi_major_axis_au=0.05, equilibrium_temperature_k=300.0,
        insolation_flux=1.0, to_dict=lambda: {},
    )
    monkeypatch.setattr(mod, "compute_derived_parameters", lambda **k: fake_derived)

    map_result = SimpleNamespace(
        success=True, period=3.45, t0=99.5, rp_rs=0.095,
        impact_parameter=0.25, u1=0.31, u2=0.21,
    )
    detrended = SimpleNamespace(
        target_id="TIC 1", sector=1,
        time=np.linspace(0, 1, 10),
        flux=np.ones(10), flux_err=np.full(10, 1e-4),
    )
    priors = SimpleNamespace(
        period=3.5, t0=100.0, rp_rs=0.1, impact_parameter=0.3,
        u1=0.3, u2=0.2, duration=0.1,
        rp_rs_bounds=(1e-4, 0.5),
    )

    r = f.fit(detrended, priors, map_result=map_result)
    assert isinstance(r, MCMCFitResult)
    # Period MAP'tan geldi (init_period = 3.45)
    assert r.period == 3.45


def test_fit_missing_pymc(monkeypatch):
    import astrotransit.modeling.pymc_fit as mod
    monkeypatch.setattr(mod, "_PYMC_AVAILABLE", False)
    monkeypatch.setattr(mod, "_EXOPLANET_AVAILABLE", False)
    with pytest.raises(ImportError):
        PyMCFitter()
