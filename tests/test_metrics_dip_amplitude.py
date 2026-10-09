"""Regression tests for the FAZ 2b.3a fix of _dip_amplitude.

The bug: the old implementation required individual in-window points to
be more than 2σ below the baseline median. This never happens in real
TESS data (shallow depths, high noise), so the function always returned
(0.0, sigma) and the entire secondary-eclipse metric chain was zero.

The fix: return (depth, SE_mean) where SE_mean = sigma / sqrt(n_in/3).
This makes depth / SE a meaningful z-score, matching standard practice
(Morton 2012 VESPA; Kepler Robovetter).
"""

from __future__ import annotations

import numpy as np

from astrotransit.quality.metrics import QualityMetricsCalculator


def _make_arrays(depth_ppm: float, noise_ppm: float, n_in: int, n_out: int = 60, seed: int = 0):
    rng = np.random.default_rng(seed)
    n = n_in + n_out
    flux = 1.0 + rng.normal(0.0, noise_ppm * 1e-6, n)
    m = np.zeros(n, dtype=bool)
    m[:n_in] = True
    flux[m] -= depth_ppm * 1e-6
    o = np.zeros(n, dtype=bool)
    o[n_in:] = True
    return flux, m, o


def test_shallow_transit_produces_nonzero_z():
    """Real TESS-like: 2000 ppm depth, 3000 ppm noise, N=14.
    Old code returned (0.0, sigma). New code returns a z > 0."""
    flux, m, o = _make_arrays(depth_ppm=2000, noise_ppm=3000, n_in=14, seed=1)
    depth, se = QualityMetricsCalculator._dip_amplitude(flux, m, o)
    assert depth > 0.0
    assert se > 0.0
    z = depth / se
    # With 14 in-dip points, n_eff = 4.67, SE ~ 3000/2.16 = 1390 ppm,
    # z ~ 2000/1390 = 1.44.
    assert 0.5 < z < 5.0


def test_deep_transit_still_high_z():
    """Synthetic-like: 30000 ppm depth, 600 ppm noise.
    Old code also worked here; new code should also work (large z)."""
    flux, m, o = _make_arrays(depth_ppm=30000, noise_ppm=600, n_in=14, seed=2)
    depth, se = QualityMetricsCalculator._dip_amplitude(flux, m, o)
    assert depth > 0.0
    assert se > 0.0
    z = depth / se
    assert z > 20.0


def test_no_dip_returns_zero():
    flux = np.ones(100)
    m = np.zeros(100, dtype=bool)
    m[10:25] = True
    o = np.zeros(100, dtype=bool)
    o[30:90] = True
    depth, _se = QualityMetricsCalculator._dip_amplitude(flux, m, o)
    assert depth == 0.0


def test_n_eff_uses_red_noise_penalty():
    """Two identical-depth cases: same sigma, larger n_in -> smaller SE."""
    flux_a, m_a, o_a = _make_arrays(depth_ppm=2000, noise_ppm=3000, n_in=6,  seed=3)
    flux_b, m_b, o_b = _make_arrays(depth_ppm=2000, noise_ppm=3000, n_in=30, seed=3)
    _, se_a = QualityMetricsCalculator._dip_amplitude(flux_a, m_a, o_a)
    _, se_b = QualityMetricsCalculator._dip_amplitude(flux_b, m_b, o_b)
    assert se_b < se_a
