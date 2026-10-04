"""
QualityMetricsCalculator ve dataclass birim testleri.

Kapsam
------
- PhotometricMetrics / TransitMetrics / StellarMetrics / QualityMetrics to_dict
- compute_photometric: normal, az nokta
- compute_transit: TLS var/yok, fit_result var/yok
- compute_stellar: LS peak, variable, binary suspect, secondary
- compute_all: entegrasyon
- Yardimcilar: _compute_cdpp, _compute_entropy, _compute_transit_symmetry,
  _compute_timing_rms, _lomb_scargle_peak, _check_secondary_eclipse
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from astrotransit.detection.cascade import CascadeCandidate, CascadeStatus
from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve
from astrotransit.quality.metrics import (
    PhotometricMetrics,
    QualityMetrics,
    QualityMetricsCalculator,
    StellarMetrics,
    TransitMetrics,
)

# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

def _detrended(
    target: str = "TIC-100",
    sector: int = 1,
    n: int = 1000,
    cadence_days: float = 120.0 / 86400.0,
    noise: float = 5e-4,
) -> DetrendedLightCurve:
    rng = np.random.default_rng(0)
    t = np.arange(n) * cadence_days + 2000.0
    flux = 1.0 + rng.normal(0, noise, size=n)
    err = np.full(n, noise)
    trend = np.ones(n)
    raw = flux + 0.001
    return DetrendedLightCurve(
        target_id=target,
        sector=sector,
        time=t,
        flux=flux,
        flux_err=err,
        trend=trend,
        raw_flux=raw,
        method="biweight",
        window_length=0.5,
        break_tolerance=0.5,
        meta={"CADENCE": "120s"},
    )


def _candidate(
    target: str = "TIC-100",
    sector: int = 1,
    n_transits: int = 4,
    with_tls: bool = False,
    odd_even: float = 0.0,
) -> CascadeCandidate:
    dummy_bls = MagicMock()
    dummy_bls.best = None

    tls = None
    if with_tls:
        n = 200
        phase = np.linspace(0.0, 1.0, n)
        flux = 1.0 + np.random.default_rng(1).normal(0, 5e-4, size=n)
        # Transit sinyali faz 0.5'te
        flux[95:105] -= 0.005
        tls = MagicMock()
        tls.folded_phase = phase
        tls.folded_flux = flux
        tls.transit_depths = np.full(n_transits, 0.005)
        tls.transit_times = np.linspace(2000.0, 2020.0, n_transits)
        tls.odd_even_mismatch = odd_even

    return CascadeCandidate(
        target_id=target,
        sector=sector,
        status=CascadeStatus.CONFIRMED,
        confirmed=True,
        bls_result=dummy_bls,  # type: ignore[arg-type]
        tls_result=tls,
        period=5.0,
        period_err=0.01,
        t0=2000.0,
        duration=0.15,
        depth=0.005,
        rp_rs=0.08,
        snr=12.0,
        sde=9.5,
        transit_times=np.linspace(2000.0, 2020.0, n_transits),
        decision_log=[],
    )


@pytest.fixture
def calc() -> QualityMetricsCalculator:
    return QualityMetricsCalculator(cadence_sec=120.0)


# ─────────────────────────────────────────────────────────────
# Dataclass to_dict
# ─────────────────────────────────────────────────────────────

def test_photometric_metrics_to_dict() -> None:
    m = PhotometricMetrics(
        flux_rms=5e-4, median_flux=1.0, noise_ppm=500.0,
        cdpp_1hr=510.0, data_completeness=0.95, n_points=1000,
        n_gaps=2, skewness=0.1, kurtosis=0.3, variance=2.5e-7, entropy=3.5,
    )
    d = m.to_dict()
    assert d["noise_ppm"] == 500.0
    assert d["cdpp_1hr_ppm"] == 510.0
    assert d["n_points"] == 1000
    assert d["n_gaps"] == 2


def test_transit_metrics_to_dict() -> None:
    m = TransitMetrics(
        snr=12.0, transit_depth=0.005, transit_depth_ppm=5000.0,
        transit_duration_hours=3.6, period=5.0, n_transits=4,
        transit_symmetry=0.9, ingress_egress_ratio=1.0,
        depth_variance=1e-8, timing_rms=0.001, odd_even_mismatch=0.5,
        residual_rms=5e-4,
    )
    d = m.to_dict()
    assert d["snr"] == 12.0
    assert d["transit_depth_ppm"] == 5000.0
    assert d["timing_rms_min"] == pytest.approx(0.001 * 1440, rel=1e-3)
    assert d["residual_rms_ppm"] == pytest.approx(500.0, rel=1e-3)


def test_stellar_metrics_to_dict() -> None:
    m = StellarMetrics(
        is_variable_star=True, variability_amplitude=1500.0,
        rotation_period_days=10.5, lomb_scargle_peak=0.5,
        lomb_scargle_period=10.5, is_binary_suspect=True,
        secondary_eclipse_depth=1e-3, centroid_shift=0.1,
    )
    d = m.to_dict()
    assert d["is_variable_star"] is True
    assert d["variability_amplitude_ppm"] == 1500.0
    assert d["secondary_eclipse_depth_ppm"] == pytest.approx(1000.0, rel=1e-3)
    assert d["centroid_shift"] == 0.1


def test_quality_metrics_to_dict() -> None:
    m = QualityMetrics(
        target_id="TIC-100", sector=1,
        photometric=PhotometricMetrics(noise_ppm=500.0),
        transit=TransitMetrics(snr=12.0),
        stellar=StellarMetrics(is_variable_star=False),
    )
    d = m.to_dict()
    assert d["target_id"] == "TIC-100"
    assert d["sector"] == 1
    assert d["photometric"]["noise_ppm"] == 500.0
    assert d["transit"]["snr"] == 12.0


# ─────────────────────────────────────────────────────────────
# compute_photometric
# ─────────────────────────────────────────────────────────────

def test_compute_photometric_normal(calc: QualityMetricsCalculator) -> None:
    det = _detrended(n=1000)
    m = calc.compute_photometric(det)
    assert m.n_points == 1000
    assert m.noise_ppm > 0
    assert m.flux_rms > 0
    assert 0.0 < m.data_completeness <= 1.0
    assert m.variance > 0


def test_compute_photometric_few_points(calc: QualityMetricsCalculator) -> None:
    """<10 nokta -> default (sifir) PhotometricMetrics."""
    det = _detrended(n=5)
    m = calc.compute_photometric(det)
    assert m.n_points == 0
    assert m.noise_ppm == 0.0


def test_compute_photometric_detects_gaps(calc: QualityMetricsCalculator) -> None:
    """Buyuk bosluklar n_gaps olarak sayilmali."""
    n = 500
    rng = np.random.default_rng(0)
    dt = 120.0 / 86400.0
    t = np.concatenate([
        np.arange(250) * dt,
        np.arange(250) * dt + 250 * dt + 1.0,  # 1 gunluk buyuk bosluk
    ])
    flux = 1.0 + rng.normal(0, 5e-4, size=n)
    err = np.full(n, 5e-4)
    det = DetrendedLightCurve(
        target_id="TIC-1", sector=1, time=t, flux=flux, flux_err=err,
        trend=np.ones(n), raw_flux=flux, method="biweight",
        window_length=0.5, break_tolerance=0.5, meta={},
    )
    m = calc.compute_photometric(det)
    assert m.n_gaps >= 1


# ─────────────────────────────────────────────────────────────
# compute_transit
# ─────────────────────────────────────────────────────────────

def test_compute_transit_no_tls(calc: QualityMetricsCalculator) -> None:
    det = _detrended()
    cand = _candidate(with_tls=False)
    m = calc.compute_transit(det, cand, fit_result=None)
    assert m.snr == 12.0
    assert m.transit_depth == 0.005
    assert m.transit_depth_ppm == 5000.0
    assert m.transit_duration_hours == pytest.approx(3.6, rel=1e-6)
    assert m.period == 5.0
    assert m.n_transits == 4
    # TLS yok -> symmetry default
    assert m.transit_symmetry == 0.0
    assert m.depth_variance == 0.0
    assert m.timing_rms == 0.0


def test_compute_transit_with_tls(calc: QualityMetricsCalculator) -> None:
    det = _detrended()
    cand = _candidate(with_tls=True, n_transits=4)
    m = calc.compute_transit(det, cand)
    # TLS var -> symmetry hesaplanmis olmali (0-1)
    assert 0.0 <= m.transit_symmetry <= 1.0
    # transit_depths var -> depth_variance hesaplanmis
    assert m.depth_variance >= 0.0


def test_compute_transit_tls_few_points(calc: QualityMetricsCalculator) -> None:
    """TLS'in folded_flux'i <10 ise symmetry default."""
    det = _detrended()
    cand = _candidate(with_tls=True)
    cand.tls_result.folded_flux = np.array([1.0, 1.0])
    cand.tls_result.folded_phase = np.array([0.4, 0.5])
    m = calc.compute_transit(det, cand)
    assert m.transit_symmetry == 0.0


def test_compute_transit_with_fit_result(calc: QualityMetricsCalculator) -> None:
    det = _detrended()
    cand = _candidate()
    fit = MagicMock()
    fit.residual_rms = 5e-4
    m = calc.compute_transit(det, cand, fit_result=fit)
    assert m.residual_rms == 5e-4


def test_compute_transit_odd_even_from_tls(calc: QualityMetricsCalculator) -> None:
    det = _detrended()
    cand = _candidate(with_tls=True, odd_even=2.5)
    m = calc.compute_transit(det, cand)
    assert m.odd_even_mismatch == 2.5


# ─────────────────────────────────────────────────────────────
# compute_stellar
# ─────────────────────────────────────────────────────────────

def test_compute_stellar_basic(calc: QualityMetricsCalculator) -> None:
    det = _detrended(n=1000)
    cand = _candidate()
    m = calc.compute_stellar(det, cand)
    # variability amplitude > 0 olmali (noise var)
    assert m.variability_amplitude > 0
    assert m.centroid_shift == 0.0
    # varsayilan olarak binary suspect olmamali (odd_even=0)
    assert m.is_binary_suspect is False


def test_compute_stellar_binary_suspect(calc: QualityMetricsCalculator) -> None:
    """odd_even > 3 -> is_binary_suspect True."""
    det = _detrended()
    cand = _candidate(with_tls=True, odd_even=5.0)
    m = calc.compute_stellar(det, cand)
    assert m.is_binary_suspect is True


def test_compute_stellar_few_points(calc: QualityMetricsCalculator) -> None:
    """<20 nokta -> LS peak 0."""
    det = _detrended(n=10)
    cand = _candidate()
    m = calc.compute_stellar(det, cand)
    # LS bosa cikar
    assert m.lomb_scargle_peak == 0.0


# ─────────────────────────────────────────────────────────────
# compute_all
# ─────────────────────────────────────────────────────────────

def test_compute_all(calc: QualityMetricsCalculator) -> None:
    det = _detrended(n=1000)
    cand = _candidate(with_tls=True)
    m = calc.compute_all(det, cand)
    assert isinstance(m, QualityMetrics)
    assert m.target_id == "TIC-100"
    assert m.sector == 1
    assert m.photometric.n_points == 1000
    assert m.transit.snr == 12.0
    assert m.stellar.variability_amplitude > 0


# ─────────────────────────────────────────────────────────────
# _compute_cdpp
# ─────────────────────────────────────────────────────────────

def test_cdpp_normal(calc: QualityMetricsCalculator) -> None:
    n = 1000
    dt = 120.0 / 86400.0
    t = np.arange(n) * dt
    flux = 1.0 + np.random.default_rng(0).normal(0, 5e-4, size=n)
    cdpp = calc._compute_cdpp(flux, t, bin_hours=1.0)
    assert cdpp > 0
    # 1h binning -> gurultu dusmeli (nokta sayisi azalir)
    naive = np.nanstd(flux - 1.0) * 1e6
    assert cdpp < naive


def test_cdpp_negative_dt(calc: QualityMetricsCalculator) -> None:
    """dt <= 0 -> 0 donmeli."""
    t = np.array([100.0, 100.0, 100.0, 100.0, 100.0])
    flux = np.array([1.0] * 5)
    assert calc._compute_cdpp(flux, t) == 0.0


def test_cdpp_bin_larger_than_data(calc: QualityMetricsCalculator) -> None:
    """points_per_bin >= len(flux) -> naive std."""
    n = 5
    dt = 120.0 / 86400.0
    t = np.arange(n) * dt
    flux = 1.0 + np.array([1e-4, -1e-4, 2e-4, -2e-4, 0.0])
    cdpp = calc._compute_cdpp(flux, t, bin_hours=24.0)
    naive = np.nanstd(flux - 1.0) * 1e6
    assert cdpp == pytest.approx(naive, rel=1e-6)


# ─────────────────────────────────────────────────────────────
# _compute_entropy
# ─────────────────────────────────────────────────────────────

def test_entropy_normal() -> None:
    flux = 1.0 + np.random.default_rng(0).normal(0, 5e-4, size=1000)
    e = QualityMetricsCalculator._compute_entropy(flux)
    assert e > 0


def test_entropy_few_points() -> None:
    flux = np.array([1.0, 1.0, 1.0])
    e = QualityMetricsCalculator._compute_entropy(flux)
    assert e == 0.0


def test_entropy_all_nan() -> None:
    flux = np.array([np.nan] * 100)
    e = QualityMetricsCalculator._compute_entropy(flux)
    assert e == 0.0


def test_entropy_constant_flux() -> None:
    """Sabit flux -> entropy ~0 (floating-point toleransli)."""
    flux = np.ones(500)
    e = QualityMetricsCalculator._compute_entropy(flux)
    # Numerik artefaktlar icin tolerans
    assert e == pytest.approx(0.0, abs=1e-8)


# ─────────────────────────────────────────────────────────────
# _compute_transit_symmetry
# ─────────────────────────────────────────────────────────────

def test_symmetry_symmetric_transit() -> None:
    """Simetrik V seklinde transit -> symmetry yuksek."""
    n = 500
    phase = np.linspace(0.0, 1.0, n)
    # Transit derinlemesine simetrik
    depth = 0.005 * np.exp(-0.5 * ((phase - 0.5) / 0.02) ** 2)
    flux = 1.0 - depth
    s = QualityMetricsCalculator._compute_transit_symmetry(phase, flux)
    assert s > 0.7


def test_symmetry_asymmetric_transit() -> None:
    """Asimetrik transit -> symmetry duser."""
    n = 500
    phase = np.linspace(0.0, 1.0, n)
    depth = 0.005 * np.exp(-0.5 * ((phase - 0.5) / 0.02) ** 2)
    # Sol tarafi daha derin yap
    left_boost = np.where(phase < 0.5, 1.5, 1.0)
    flux = 1.0 - depth * left_boost
    s = QualityMetricsCalculator._compute_transit_symmetry(phase, flux)
    # Simetriden daha dusuk olmali
    assert s < 0.95


def test_symmetry_few_points() -> None:
    phase = np.array([0.4, 0.5, 0.6])
    flux = np.array([1.0, 0.995, 1.0])
    assert QualityMetricsCalculator._compute_transit_symmetry(phase, flux) == 0.5


def test_symmetry_no_transit_in_window() -> None:
    """Pencere icinde <6 nokta -> 0.5."""
    phase = np.array([0.0, 0.1, 0.2, 0.3, 0.9])
    flux = np.ones(5)
    assert QualityMetricsCalculator._compute_transit_symmetry(phase, flux) == 0.5


def test_symmetry_zero_depth() -> None:
    """Transit yok (sabit flux) -> 0.5."""
    n = 500
    phase = np.linspace(0.0, 1.0, n)
    flux = np.ones(n)
    s = QualityMetricsCalculator._compute_transit_symmetry(phase, flux)
    assert s == 0.5


# ─────────────────────────────────────────────────────────────
# _compute_timing_rms
# ─────────────────────────────────────────────────────────────

def test_timing_rms_perfect_ephemeris() -> None:
    """Tam periyodik transit zamanlari -> RMS ~0."""
    period = 5.0
    t0 = 2000.0
    times = t0 + np.arange(5) * period
    rms = QualityMetricsCalculator._compute_timing_rms(times, period)
    assert rms == pytest.approx(0.0, abs=1e-10)


def test_timing_rms_with_ttv() -> None:
    """TTV eklenmis transit zamanlari -> RMS > 0."""
    period = 5.0
    t0 = 2000.0
    times = t0 + np.arange(5) * period + np.array([0, 0.01, -0.02, 0.03, 0.0])
    rms = QualityMetricsCalculator._compute_timing_rms(times, period)
    assert rms > 0


def test_timing_rms_few_transits() -> None:
    times = np.array([2000.0, 2005.0])
    assert QualityMetricsCalculator._compute_timing_rms(times, 5.0) == 0.0


def test_timing_rms_bad_period() -> None:
    times = np.array([2000.0, 2005.0, 2010.0])
    assert QualityMetricsCalculator._compute_timing_rms(times, 0.0) == 0.0
    assert QualityMetricsCalculator._compute_timing_rms(times, -1.0) == 0.0


# ─────────────────────────────────────────────────────────────
# _lomb_scargle_peak
# ─────────────────────────────────────────────────────────────

def test_lomb_scargle_detects_periodic_signal() -> None:
    """Gercek periyodik sinyal -> LS peak yakalanmali."""
    n = 2000
    dt = 120.0 / 86400.0
    time = np.arange(n) * dt
    period = 5.0
    signal = 0.005 * np.sin(2 * np.pi * time / period)
    flux = 1.0 + signal
    p, power = QualityMetricsCalculator._lomb_scargle_peak(time, flux)
    assert power > 0
    assert p > 0


def test_lomb_scargle_few_points() -> None:
    time = np.arange(10) * 0.01
    flux = np.ones(10)
    p, power = QualityMetricsCalculator._lomb_scargle_peak(time, flux)
    assert p == 0.0
    assert power == 0.0


# ─────────────────────────────────────────────────────────────
# _check_secondary_eclipse
# ─────────────────────────────────────────────────────────────

def test_secondary_eclipse_basic() -> None:
    """Faz 0.5'te dip varsa secondary depth > 0."""
    n = 2000
    dt = 120.0 / 86400.0
    time = np.arange(n) * dt
    period = 5.0
    t0 = 0.0
    phase = ((time - t0) % period) / period
    # Faz 0.5'te dip
    secondary = 0.005 * np.exp(-0.5 * ((phase - 0.5) / 0.01) ** 2)
    flux = 1.0 - secondary
    depth = QualityMetricsCalculator._check_secondary_eclipse(
        time, flux, period, t0,
    )
    assert depth > 0


def test_secondary_eclipse_no_dip() -> None:
    """Dip yoksa ~0."""
    n = 1000
    dt = 120.0 / 86400.0
    time = np.arange(n) * dt
    flux = np.ones(n)
    depth = QualityMetricsCalculator._check_secondary_eclipse(
        time, flux, 5.0, 0.0,
    )
    assert depth == 0.0


def test_secondary_eclipse_bad_period() -> None:
    time = np.arange(100) * 0.01
    flux = np.ones(100)
    assert QualityMetricsCalculator._check_secondary_eclipse(
        time, flux, 0.0, 0.0,
    ) == 0.0
    assert QualityMetricsCalculator._check_secondary_eclipse(
        time, flux, -5.0, 0.0,
    ) == 0.0


def test_secondary_eclipse_few_points() -> None:
    time = np.arange(10) * 0.01
    flux = np.ones(10)
    assert QualityMetricsCalculator._check_secondary_eclipse(
        time, flux, 5.0, 0.0,
    ) == 0.0


# ─────────────────────────────────────────────────────────────
# init
# ─────────────────────────────────────────────────────────────

def test_calculator_init_custom_cadence() -> None:
    c = QualityMetricsCalculator(cadence_sec=600.0)
    assert c.cadence_sec == 600.0


def test_calculator_init_default() -> None:
    c = QualityMetricsCalculator()
    assert c.cadence_sec == 120.0
