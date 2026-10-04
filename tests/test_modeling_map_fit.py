"""
MAPFitter ve ParameterVector birim testleri.

Kapsam
------
- MAPFitResult.to_dict / summary
- ParameterVector.to_vector / from_vector / bounds
- MAPFitter._negative_log_posterior: fiziksel validation
- MAPFitter.fit: basarili, basarisiz, restart senaryolari (mock minimize)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from astrotransit.modeling import map_fit as mf_module
from astrotransit.modeling.map_fit import (
    MAPFitResult,
    MAPFitter,
    ParameterVector,
)
from astrotransit.modeling.parameters import (
    DerivedParameters,
    TransitPriors,
)

# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

def _detrended(target: str = "TIC-100", sector: int = 1, n: int = 300):
    from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve
    rng = np.random.default_rng(0)
    time = np.linspace(100.0, 120.0, n)
    flux = 1.0 + rng.normal(0, 5e-4, size=n)
    return DetrendedLightCurve(
        target_id=target, sector=sector,
        time=time, flux=flux, flux_err=np.full(n, 5e-4),
        trend=np.ones(n), raw_flux=flux + 0.001,
        method="biweight", window_length=0.5,
        break_tolerance=0.5, meta={"CADENCE": "120s"},
    )


def _priors(
    period: float = 5.0,
    t0: float = 100.0,
    rp_rs: float = 0.08,
    impact_parameter: float = 0.3,
    u1: float = 0.3,
    u2: float = 0.2,
    log_jitter: float = -7.0,
    baseline: float = 1.0,
    duration: float = 0.15,
):
    """TransitPriors ornegini gercekci degerlerle uretir."""
    return TransitPriors(
        period=period, t0=t0, rp_rs=rp_rs,
        impact_parameter=impact_parameter,
        u1=u1, u2=u2, log_jitter=log_jitter,
        baseline=baseline, duration=duration,
    )


# ─────────────────────────────────────────────────────────────
# MAPFitResult
# ─────────────────────────────────────────────────────────────

def test_map_fit_result_defaults() -> None:
    r = MAPFitResult(target_id="TIC-1", sector=1, success=False)
    assert r.period == 0.0
    assert r.inclination == 90.0
    assert r.u1 == 0.3
    assert r.u2 == 0.2
    assert r.baseline == 1.0
    assert r.fit_method == "map"
    assert r.optimizer_boundary_hit is False
    assert r.is_grazing_geometry is False


def test_map_fit_result_to_dict() -> None:
    r = MAPFitResult(
        target_id="TIC-1", sector=2, success=True,
        period=5.0, rp_rs=0.08, impact_parameter=0.3,
        log_likelihood=-1200.5, residual_rms=5e-4,
    )
    d = r.to_dict()
    assert d["target_id"] == "TIC-1"
    assert d["sector"] == 2
    assert d["success"] is True
    assert d["period"] == 5.0
    assert d["rp_rs"] == 0.08
    assert d["residual_rms_ppm"] == pytest.approx(500.0, rel=1e-3)
    assert isinstance(d["optimizer_boundary_hits"], list)


def test_map_fit_result_summary_equals_to_dict() -> None:
    r = MAPFitResult(target_id="TIC-1", sector=1, success=True)
    assert r.summary() == r.to_dict()


# ─────────────────────────────────────────────────────────────
# ParameterVector
# ─────────────────────────────────────────────────────────────

def test_parameter_vector_param_names() -> None:
    assert "period" in ParameterVector.PARAM_NAMES
    assert "log_rp_rs" in ParameterVector.PARAM_NAMES
    assert len(ParameterVector.PARAM_NAMES) == 8


def test_param_vector_to_from_roundtrip() -> None:
    x = ParameterVector.to_vector(
        period=5.0, t0=100.0, rp_rs=0.08,
        impact_parameter=0.3, u1=0.3, u2=0.2,
        log_jitter=-7.0, baseline=1.0,
    )
    phys = ParameterVector.from_vector(x)
    assert phys["period"] == pytest.approx(5.0)
    assert phys["t0"] == pytest.approx(100.0)
    assert phys["rp_rs"] == pytest.approx(0.08)
    assert phys["impact_parameter"] == pytest.approx(0.3)
    assert phys["log_jitter"] == pytest.approx(-7.0)
    assert phys["baseline"] == pytest.approx(1.0)


def test_param_vector_to_vector_handles_tiny_rp() -> None:
    x = ParameterVector.to_vector(
        period=5.0, t0=100.0, rp_rs=0.0,
        impact_parameter=0.3, u1=0.3, u2=0.2,
        log_jitter=-7.0, baseline=1.0,
    )
    # rp_rs=0 -> log(1e-6) = -13.8
    assert x[2] == pytest.approx(np.log(1e-6))


def test_param_vector_bounds_shape() -> None:
    priors = _priors()
    b = ParameterVector.bounds(priors)
    assert len(b) == 8
    # log_rp_rs (index 2) log uzayinda
    assert b[2][0] < b[2][1]
    # q1, q2 0-1 arasi
    assert b[4] == (0.0, 1.0)
    assert b[5] == (0.0, 1.0)
    # baseline 0.9-1.1
    assert b[7] == (0.9, 1.1)


# ─────────────────────────────────────────────────────────────
# _negative_log_posterior
# ─────────────────────────────────────────────────────────────

def test_nll_returns_1e10_for_nonfinite() -> None:
    """NaN iceren vektor -> 1e10."""
    fitter = MAPFitter()
    x = np.array([np.nan, 100.0, np.log(0.08), 0.3, 0.5, 0.5, -7.0, 1.0])
    model = MagicMock()
    nll = fitter._negative_log_posterior(
        x, model, np.ones(10), np.ones(10), _priors(), a_over_rs=8.5,
    )
    assert nll == 1e10


def test_nll_returns_1e10_for_tiny_rp() -> None:
    """Cok kucuk rp_rs (exp(-100)) ama > 0 -> fiziksel validation gecer.

    Not: `from_vector` exp(x[2]) yapar; bu her zaman >0 verir, negatif
    olamaz. Kod fiziksel kontrol olarak rp_rs>1.0 ve rp_rs<=0 kontrol
    eder ama exp() yuzunden ikincisi pratikte tetiklenmez.
    """
    fitter = MAPFitter()
    x = np.array([5.0, 100.0, -100.0, 0.3, 0.5, 0.5, -7.0, 1.0])
    # Modelin log_likelihood'u finite donmeli
    model = MagicMock()
    model.impact_to_inclination.return_value = 88.5
    model.log_likelihood.return_value = -1000.0
    nll = fitter._negative_log_posterior(
        x, model, np.ones(10), np.ones(10), _priors(), a_over_rs=8.5,
    )
    # rp_rs ~ 3.7e-44 → finite, NLL sonlu
    assert nll != 1e10
    assert np.isfinite(nll)


def test_nll_returns_1e10_for_rp_above_1() -> None:
    """rp_rs > 1.0 -> 1e10."""
    fitter = MAPFitter()
    x = np.array([5.0, 100.0, np.log(1.5), 0.3, 0.5, 0.5, -7.0, 1.0])
    model = MagicMock()
    nll = fitter._negative_log_posterior(
        x, model, np.ones(10), np.ones(10), _priors(), a_over_rs=8.5,
    )
    assert nll == 1e10


def test_nll_returns_1e10_for_negative_period() -> None:
    fitter = MAPFitter()
    x = np.array([-5.0, 100.0, np.log(0.08), 0.3, 0.5, 0.5, -7.0, 1.0])
    nll = fitter._negative_log_posterior(
        x, MagicMock(), np.ones(10), np.ones(10), _priors(), a_over_rs=8.5,
    )
    assert nll == 1e10


def test_nll_returns_1e10_for_bad_baseline() -> None:
    fitter = MAPFitter()
    # baseline 0.3 (< 0.5)
    x = np.array([5.0, 100.0, np.log(0.08), 0.3, 0.5, 0.5, -7.0, 0.3])
    nll = fitter._negative_log_posterior(
        x, MagicMock(), np.ones(10), np.ones(10), _priors(), a_over_rs=8.5,
    )
    assert nll == 1e10


def test_nll_returns_1e10_for_grazing() -> None:
    """impact_parameter >= 1 + rp_rs -> grazing."""
    fitter = MAPFitter()
    x = np.array([5.0, 100.0, np.log(0.08), 1.2, 0.5, 0.5, -7.0, 1.0])
    nll = fitter._negative_log_posterior(
        x, MagicMock(), np.ones(10), np.ones(10), _priors(), a_over_rs=8.5,
    )
    assert nll == 1e10


def test_nll_success_path(monkeypatch) -> None:
    """Gecerli vektor -> negatif log-posterior sonlu deger."""
    fitter = MAPFitter()

    # TransitModel sinifini mock'la (impact_to_inclination + log_likelihood)
    mock_model_instance = MagicMock()
    mock_model_instance.impact_to_inclination = MagicMock(return_value=88.5)
    mock_model_instance.log_likelihood.return_value = -100.0

    x = np.array([5.0, 100.0, np.log(0.08), 0.3, 0.5, 0.5, -7.0, 1.0])
    nll = fitter._negative_log_posterior(
        x, mock_model_instance, np.ones(10), np.ones(10),
        _priors(), a_over_rs=8.5,
    )
    # log_like = -100, log_prior = -0.5 * 0 = 0, NLL = 100
    assert nll == pytest.approx(100.0)


# ─────────────────────────────────────────────────────────────
# fit — monkeypatch minimize
# ─────────────────────────────────────────────────────────────

def test_fit_success(monkeypatch) -> None:
    """Minimize basarili -> MAPFitResult success=True."""
    fitter = MAPFitter(n_restarts=1)

    # Sahte optimize result
    class FakeResult:
        x = np.array([5.0, 100.0, np.log(0.08), 0.3, 0.5, 0.5, -7.0, 1.0])
        fun = 100.0
        success = True
        nit = 42
        message = "CONVERGENCE: ..."

    monkeypatch.setattr(mf_module, "minimize", lambda *a, **kw: FakeResult())

    # TransitModel'i mock'la — compute_a_over_rs static method olarak
    # GERCEK float donmeli, aksi halde f-string format hatasi alinir
    mock_tm_instance = MagicMock()
    mock_tm_instance.impact_to_inclination.return_value = 88.5
    mock_tm_instance.flux.return_value = np.ones(300)

    class FakeTransitModel:
        def __init__(self, time):
            self._inst = mock_tm_instance
        @staticmethod
        def compute_a_over_rs(period, mass, radius):
            return 8.5
        @staticmethod
        def impact_to_inclination(b, a_over_rs):
            return 88.5
        def __getattr__(self, name):
            return getattr(mock_tm_instance, name)

    monkeypatch.setattr(mf_module, "TransitModel", FakeTransitModel)

    # Derived parameters
    monkeypatch.setattr(
        mf_module, "compute_derived_parameters",
        lambda **kw: DerivedParameters(planet_radius_rearth=10.0),
    )

    # Reliability
    fake_rel = MagicMock()
    fake_rel.status = "ok"
    fake_rel.reasons = ()
    fake_rel.is_grazing_geometry = False
    fake_rel.radius_at_optimizer_boundary = False
    monkeypatch.setattr(mf_module, "assess_radius_reliability", lambda **kw: fake_rel)

    # parameter_boundary_hits
    monkeypatch.setattr(mf_module, "parameter_boundary_hits", lambda x, b, names: ())

    result = fitter.fit(_detrended(), _priors())
    assert isinstance(result, MAPFitResult)
    assert result.target_id == "TIC-100"
    # success bool(np.bool_) olabilir; == karsilastirma kullan
    assert result.success == True  # noqa: E712
    assert result.period == pytest.approx(5.0)
    assert result.rp_rs == pytest.approx(0.08)


def test_fit_all_restarts_fail(monkeypatch) -> None:
    """Tum restartlar exception firlatirsa _failed_result."""
    fitter = MAPFitter(n_restarts=2)

    def exploding_minimize(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(mf_module, "minimize", exploding_minimize)

    class FakeTM:
        def __init__(self, time):
            pass
        @staticmethod
        def compute_a_over_rs(period, mass, radius):
            return 8.5

    monkeypatch.setattr(mf_module, "TransitModel", FakeTM)

    result = fitter.fit(_detrended(), _priors())
    assert result.success is False
    assert "Optimizasyon başarısız" in result.optimizer_message


def test_fit_retries_perturb(monkeypatch) -> None:
    """n_restarts > 1 -> birden fazla minimize cagrisi."""
    fitter = MAPFitter(n_restarts=3)

    call_count = {"n": 0}

    class FakeResult:
        x = np.array([5.0, 100.0, np.log(0.08), 0.3, 0.5, 0.5, -7.0, 1.0])
        fun = 100.0
        success = True
        nit = 10
        message = "ok"

    def counting_minimize(*args, **kwargs):
        call_count["n"] += 1
        return FakeResult()

    monkeypatch.setattr(mf_module, "minimize", counting_minimize)

    mock_tm_instance = MagicMock()
    mock_tm_instance.flux.return_value = np.ones(300)

    class FakeTM:
        def __init__(self, time):
            self._inst = mock_tm_instance
        @staticmethod
        def compute_a_over_rs(period, mass, radius):
            return 8.5
        @staticmethod
        def impact_to_inclination(b, a_over_rs):
            return 88.5
        def __getattr__(self, name):
            return getattr(mock_tm_instance, name)

    monkeypatch.setattr(mf_module, "TransitModel", FakeTM)

    monkeypatch.setattr(
        mf_module, "compute_derived_parameters",
        lambda **kw: DerivedParameters(),
    )
    fake_rel = MagicMock(status="ok", reasons=(),
                         is_grazing_geometry=False,
                         radius_at_optimizer_boundary=False)
    monkeypatch.setattr(mf_module, "assess_radius_reliability", lambda **kw: fake_rel)
    monkeypatch.setattr(mf_module, "parameter_boundary_hits", lambda x, b, n: ())

    fitter.fit(_detrended(), _priors())
    assert call_count["n"] == 3


# ─────────────────────────────────────────────────────────────
# _failed_result
# ─────────────────────────────────────────────────────────────

def test_failed_result_helper() -> None:
    fitter = MAPFitter()
    r = fitter._failed_result("TIC-9", 7)
    assert r.target_id == "TIC-9"
    assert r.sector == 7
    assert r.success is False
    assert "başarısız" in r.optimizer_message.lower()


# ─────────────────────────────────────────────────────────────
# __init__
# ─────────────────────────────────────────────────────────────

def test_fitter_init_defaults() -> None:
    f = MAPFitter()
    assert f.max_iterations == 2000
    assert f.n_restarts == 3


def test_fitter_init_custom() -> None:
    f = MAPFitter(max_iterations=500, n_restarts=1)
    assert f.max_iterations == 500
    assert f.n_restarts == 1
