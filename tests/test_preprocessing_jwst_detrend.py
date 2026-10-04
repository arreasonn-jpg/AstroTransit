"""astrotransit/preprocessing/jwst_detrend.py için testler."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from astrotransit.preprocessing.jwst_detrend import (
    JWSTDetrendedData,
    JWSTGPDetrending,
    JWSTObservationData,
)


def _make_obs(n=100, instrument="NIRSpec", target="WASP-39"):
    rng = np.random.default_rng(0)
    t = np.linspace(0, 1.0, n)
    flux = 1.0 + rng.normal(0, 5e-4, n)
    flux_err = np.full(n, 1e-4)
    return JWSTObservationData(
        target_id=target,
        program_id="1234",
        instrument=instrument,
        time=t,
        flux=flux,
        flux_err=flux_err,
    )


# ═══════════════════════════════════════════════════════
# JWSTObservationData
# ═══════════════════════════════════════════════════════

def test_obs_n_points():
    obs = _make_obs(n=50)
    assert obs.n_points == 50


def test_obs_duration_hours():
    obs = _make_obs(n=10)
    # 1.0 gün * 24 = 24 saat
    assert obs.duration_hours == pytest.approx(24.0, rel=0.01)


def test_obs_duration_hours_too_short():
    obs = JWSTObservationData(
        target_id="X", program_id="1", instrument="NIRSpec",
        time=np.array([1.0]), flux=np.array([1.0]),
        flux_err=np.array([0.001]),
    )
    assert obs.duration_hours == 0.0


def test_obs_defaults():
    obs = _make_obs()
    assert obs.time_format == "bjd"
    assert obs.meta == {}
    assert obs.wavelength_um is None


# ═══════════════════════════════════════════════════════
# JWSTDetrendedData
# ═══════════════════════════════════════════════════════

def _make_detrended(n=100, noise=0.0):
    rng = np.random.default_rng(0)
    return JWSTDetrendedData(
        target_id="TIC 1",
        instrument="NIRSpec",
        time=np.linspace(0, 1, n),
        flux=1.0 + rng.normal(0, noise, n),
        flux_err=np.full(n, 1e-4),
        gp_mean=np.ones(n),
        raw_flux=np.ones(n),
        gp_params={"sigma": 0.1, "rho": 1.0, "Q": 1.0},
        log_likelihood=-100.0,
    )


def test_detrended_n_points():
    d = _make_detrended(n=50)
    assert d.n_points == 50


def test_detrended_residual_rms():
    d = _make_detrended(n=1000, noise=1e-3)
    assert d.residual_rms == pytest.approx(1e-3, rel=0.3)


def test_detrended_noise_ppm():
    d = _make_detrended(n=1000, noise=1e-3)
    assert d.noise_ppm == pytest.approx(1000.0, rel=0.3)


def test_detrended_summary_keys():
    d = _make_detrended()
    s = d.summary()
    assert s["target_id"] == "TIC 1"
    assert s["instrument"] == "NIRSpec"
    assert "residual_rms" in s
    assert "noise_ppm" in s
    assert s["log_likelihood"] == -100.0


# ═══════════════════════════════════════════════════════
# JWSTGPDetrending.__init__
# ═══════════════════════════════════════════════════════

def test_gp_detrending_init_requires_celerite2(monkeypatch):
    import astrotransit.preprocessing.jwst_detrend as mod
    monkeypatch.setattr(mod, "_CELERITE2_AVAILABLE", False)
    with pytest.raises(ImportError, match="celerite2"):
        JWSTGPDetrending()


def test_gp_detrending_init_requires_scipy(monkeypatch):
    import astrotransit.preprocessing.jwst_detrend as mod
    monkeypatch.setattr(mod, "_CELERITE2_AVAILABLE", True)
    monkeypatch.setattr(mod, "_SCIPY_AVAILABLE", False)
    with pytest.raises(ImportError, match="scipy"):
        JWSTGPDetrending()


def test_gp_detrending_init_ok(monkeypatch):
    import astrotransit.preprocessing.jwst_detrend as mod
    monkeypatch.setattr(mod, "_CELERITE2_AVAILABLE", True)
    monkeypatch.setattr(mod, "_SCIPY_AVAILABLE", True)
    d = JWSTGPDetrending(sigma_outlier=4.0, n_restarts=2, mask_transit=False)
    assert d.sigma_outlier == 4.0
    assert d.n_restarts == 2
    assert d.mask_transit is False


# ═══════════════════════════════════════════════════════
# _build_gp / _negative_log_likelihood / _optimize_gp
# ═══════════════════════════════════════════════════════

def _make_detrending(monkeypatch, **kwargs):
    import astrotransit.preprocessing.jwst_detrend as mod
    monkeypatch.setattr(mod, "_CELERITE2_AVAILABLE", True)
    monkeypatch.setattr(mod, "_SCIPY_AVAILABLE", True)
    return JWSTGPDetrending(**kwargs)


def test_build_gp_calls_compute(monkeypatch):
    d = _make_detrending(monkeypatch)
    fake_gp = MagicMock()
    fake_kernel = MagicMock()

    fake_terms = MagicMock()
    fake_terms.SHOTerm.return_value = fake_kernel

    import astrotransit.preprocessing.jwst_detrend as mod
    # celerite2 kurulu olmayabilir; mod.terms yoksa ekle
    monkeypatch.setattr(mod, "terms", fake_terms, raising=False)
    monkeypatch.setattr(fake_terms, "SHOTerm", fake_terms.SHOTerm, raising=False)

    fake_cel = MagicMock()
    fake_cel.GaussianProcess.return_value = fake_gp
    monkeypatch.setattr(mod, "celerite2", fake_cel, raising=False)

    time = np.linspace(0, 1, 20)
    err = np.full(20, 1e-4)
    gp = d._build_gp(time, err, 0.0, 0.0, 0.0)
    assert gp is fake_gp
    fake_gp.compute.assert_called_once()


def test_negative_log_likelihood_returns_float(monkeypatch):
    d = _make_detrending(monkeypatch)
    fake_gp = MagicMock()
    fake_gp.log_likelihood.return_value = -42.0
    monkeypatch.setattr(d, "_build_gp", lambda *a, **k: fake_gp)

    time = np.linspace(0, 1, 20)
    flux = np.ones(20)
    err = np.full(20, 1e-4)
    nll = d._negative_log_likelihood(np.array([0.0, 0.0, 0.0]), time, flux, err)
    assert nll == 42.0


def test_negative_log_likelihood_returns_inf_on_error(monkeypatch):
    d = _make_detrending(monkeypatch)
    monkeypatch.setattr(d, "_build_gp", MagicMock(side_effect=RuntimeError("x")))

    time = np.linspace(0, 1, 20)
    flux = np.ones(20)
    err = np.full(20, 1e-4)
    nll = d._negative_log_likelihood(np.array([0.0, 0.0, 0.0]), time, flux, err)
    assert np.isinf(nll)


def test_optimize_gp_success(monkeypatch):
    d = _make_detrending(monkeypatch, n_restarts=1)
    fake_result = SimpleNamespace(x=np.array([-2.0, 0.0, 0.0]), fun=-10.0)
    import astrotransit.preprocessing.jwst_detrend as mod
    monkeypatch.setattr(mod, "minimize", lambda *a, **k: fake_result)

    time = np.linspace(0, 1, 20)
    flux = 1.0 + np.random.default_rng(0).normal(0, 5e-4, 20)
    err = np.full(20, 1e-4)
    params, ll = d._optimize_gp(time, flux, err)
    assert "log_sigma" in params
    assert "sigma" in params
    assert ll == 10.0


def test_optimize_gp_all_fail_raises(monkeypatch):
    d = _make_detrending(monkeypatch, n_restarts=1)
    import astrotransit.preprocessing.jwst_detrend as mod
    monkeypatch.setattr(mod, "minimize", MagicMock(side_effect=RuntimeError("x")))

    time = np.linspace(0, 1, 20)
    flux = np.ones(20)
    err = np.full(20, 1e-4)
    with pytest.raises(RuntimeError, match="optimizasyon"):
        d._optimize_gp(time, flux, err)


# ═══════════════════════════════════════════════════════
# detrend
# ═══════════════════════════════════════════════════════

def test_detrend_happy(monkeypatch):
    d = _make_detrending(monkeypatch)
    # GP'yi mockla
    fake_gp = MagicMock()
    # return_cov=False → tek array, length = t'nin boyutu
    fake_gp.predict.side_effect = lambda *a, **kw: np.ones_like(
        np.asarray(kw.get("t", a[-1] if a else 0), dtype=float)
    )
    monkeypatch.setattr(d, "_build_gp", lambda *a, **k: fake_gp)
    monkeypatch.setattr(
        d, "_optimize_gp",
        lambda *a, **k: (
            {"log_sigma": -2.3, "log_rho": 0.0, "log_Q": 0.0,
             "sigma": 0.1, "rho": 1.0, "Q": 1.0},
            -10.0,
        ),
    )

    obs = _make_obs(n=100)
    out = d.detrend(obs)
    assert isinstance(out, JWSTDetrendedData)
    assert out.target_id == obs.target_id
    assert out.instrument == obs.instrument


def test_detrend_with_transit_mask(monkeypatch):
    d = _make_detrending(monkeypatch, mask_transit=True)
    monkeypatch.setattr(
        d, "_optimize_gp",
        lambda *a, **k: (
            {"log_sigma": -2.3, "log_rho": 0.0, "log_Q": 0.0,
             "sigma": 0.1, "rho": 1.0, "Q": 1.0},
            -10.0,
        ),
    )
    fake_gp = MagicMock()
    fake_gp.predict.side_effect = lambda *a, **kw: np.ones_like(
        np.asarray(kw.get("t", a[-1] if a else 0), dtype=float)
    )
    monkeypatch.setattr(d, "_build_gp", lambda *a, **k: fake_gp)

    obs = _make_obs(n=100)
    mask = np.zeros(100, dtype=bool)
    mask[40:60] = True  # transit penceresi
    out = d.detrend(obs, transit_mask=mask)
    assert isinstance(out, JWSTDetrendedData)


def test_detrend_with_outliers(monkeypatch):
    d = _make_detrending(monkeypatch)
    monkeypatch.setattr(
        d, "_optimize_gp",
        lambda *a, **k: (
            {"log_sigma": -2.3, "log_rho": 0.0, "log_Q": 0.0,
             "sigma": 0.1, "rho": 1.0, "Q": 1.0},
            -10.0,
        ),
    )
    fake_gp = MagicMock()
    fake_gp.predict.side_effect = lambda *a, **kw: np.ones_like(
        np.asarray(kw.get("t", a[-1] if a else 0), dtype=float)
    )
    monkeypatch.setattr(d, "_build_gp", lambda *a, **k: fake_gp)

    obs = _make_obs(n=100)
    obs.flux[5] = 100.0  # belirgin aykırı
    out = d.detrend(obs)
    assert out.n_points <= obs.n_points
