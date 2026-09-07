"""
Pytest ortak fixture'ları.

Tüm test modülleri tarafından kullanılan
ortak veri, mock ve yardımcı fonksiyonlar.
"""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pytest

# Proje kökünü yola ekle
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


# ──────────────────────────────────────
# Sentetik veri üreticileri
# ──────────────────────────────────────
def generate_synthetic_lightcurve(
    n_points: int = 5000,
    cadence_days: float = 2.0 / 1440.0,
    baseline: float = 1.0,
    noise_ppm: float = 200.0,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Sentetik sabit light curve üretir (transit yok).

    Returns
    -------
    tuple[time, flux, flux_err]
    """

    rng = np.random.default_rng(seed)

    time = np.arange(n_points) * cadence_days
    noise = rng.normal(0, noise_ppm * 1e-6, n_points)
    flux = baseline + noise
    flux_err = np.full(n_points, noise_ppm * 1e-6)

    return time, flux, flux_err


def generate_transit_lightcurve(
    n_points: int = 5000,
    cadence_days: float = 2.0 / 1440.0,
    period: float = 3.5,
    t0: float = 1.0,
    depth: float = 0.01,
    duration_days: float = 0.1,
    noise_ppm: float = 200.0,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """
    Sentetik transit light curve üretir.

    Basit kutu transit modeli kullanır.

    Returns
    -------
    tuple[time, flux, flux_err, truth_params]
    """

    rng = np.random.default_rng(seed)

    time = np.arange(n_points) * cadence_days
    noise = rng.normal(0, noise_ppm * 1e-6, n_points)
    flux = np.ones(n_points) + noise

    # Kutu transit enjeksiyonu
    half_dur = duration_days / 2.0

    for n_transit in range(-5, int(time[-1] / period) + 5):
        t_center = t0 + n_transit * period
        in_transit = np.abs(time - t_center) < half_dur
        flux[in_transit] -= depth

    flux_err = np.full(n_points, noise_ppm * 1e-6)

    truth = {
        "period": period,
        "t0": t0,
        "depth": depth,
        "duration_days": duration_days,
        "rp_rs": np.sqrt(depth),
        "n_points": n_points,
        "noise_ppm": noise_ppm,
    }

    return time, flux, flux_err, truth


# ──────────────────────────────────────
# Fixture'lar
# ──────────────────────────────────────
@pytest.fixture
def synthetic_flat():
    """Transitsiz sentetik light curve."""
    return generate_synthetic_lightcurve()


@pytest.fixture
def synthetic_transit():
    """Transitli sentetik light curve."""
    return generate_transit_lightcurve()


@pytest.fixture
def synthetic_transit_shallow():
    """Sığ transitli light curve (500 ppm derinlik)."""
    return generate_transit_lightcurve(depth=0.0005, noise_ppm=150.0)


@pytest.fixture
def synthetic_transit_deep():
    """Derin transitli light curve (2% derinlik)."""
    return generate_transit_lightcurve(depth=0.02, noise_ppm=100.0)


@pytest.fixture
def tess_lc_data():
    """TESSLightCurveData mock nesnesi."""

    from astrotransit.data.tess_client import TESSLightCurveData

    time, flux, flux_err, truth = generate_transit_lightcurve()

    return TESSLightCurveData(
        target_id="TIC 999999999",
        sector=14,
        time=time,
        flux=flux,
        flux_err=flux_err,
        quality=np.zeros(len(time), dtype=np.int32),
        cadence=120.0,
        n_points_raw=len(time),
        n_points_clean=len(time),
        meta={"SECTOR": 14, "TEFF": 5500, "RADIUS": 1.0},
    ), truth


@pytest.fixture
def detrended_lc():
    """DetrendedLightCurve mock nesnesi."""

    from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve

    time, flux, flux_err, truth = generate_transit_lightcurve()

    return DetrendedLightCurve(
        target_id="TIC 999999999",
        sector=14,
        time=time,
        flux=flux,
        flux_err=flux_err,
        trend=np.ones(len(time)),
        raw_flux=flux.copy(),
        method="biweight",
        window_length=0.5,
        break_tolerance=0.5,
    ), truth


@pytest.fixture
def tmp_output_dir(tmp_path):
    """Geçici çıktı dizini."""
    output = tmp_path / "outputs"
    output.mkdir()
    (output / "parquet").mkdir()
    (output / "json").mkdir()
    (output / "csv").mkdir()
    (output / "figures").mkdir()
    return output


@pytest.fixture
def sample_settings():
    """Test için ayarlar nesnesi."""

    from astrotransit.settings import Settings
    return Settings()