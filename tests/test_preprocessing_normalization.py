"""
LightCurveNormalizer ve ilgili dataclass birim testleri.

Kapsam
------
- NormalizationMethod enum
- NormalizedLightCurve properties + summary
- NormalizedMultiSector combined_time / combined_flux / combined_flux_err
- LightCurveNormalizer.__init__ (str / enum / gecersiz)
- _compute_norm_factor: median, mean, percentile, robust_mean
- normalize / normalize_multi
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from astrotransit.preprocessing.normalization import (
    LightCurveNormalizer,
    NormalizationMethod,
    NormalizedLightCurve,
    NormalizedMultiSector,
)

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _raw_data(
    target: str = "TIC-100",
    sector: int = 1,
    n: int = 100,
    flux_scale: float = 1000.0,
    noise: float = 1.0,
    seed: int = 0,
):
    rng = np.random.default_rng(seed)
    m = MagicMock()
    m.target_id = target
    m.sector = sector
    m.time = np.linspace(100.0, 120.0, n)
    m.flux = flux_scale + rng.normal(0, noise, size=n)
    m.flux_err = np.full(n, noise)
    m.meta = {"CADENCE": "120s"}
    return m


def _norm_lc(target: str = "TIC-100", sector: int = 1, n: int = 100):
    rng = np.random.default_rng(0)
    return NormalizedLightCurve(
        target_id=target, sector=sector,
        time=np.linspace(100.0, 120.0, n),
        flux=1.0 + rng.normal(0, 1e-3, size=n),
        flux_err=np.full(n, 1e-3),
        norm_factor=1000.0,
        method="median",
        meta={"CADENCE": "120s"},
    )


# ─────────────────────────────────────────────────────────────
# NormalizationMethod
# ─────────────────────────────────────────────────────────────

def test_method_values() -> None:
    assert NormalizationMethod.MEDIAN.value == "median"
    assert NormalizationMethod.MEAN.value == "mean"
    assert NormalizationMethod.PERCENTILE.value == "percentile"
    assert NormalizationMethod.ROBUST_MEAN.value == "robust_mean"


# ─────────────────────────────────────────────────────────────
# NormalizedLightCurve
# ─────────────────────────────────────────────────────────────

def test_nlc_properties() -> None:
    lc = _norm_lc(n=500)
    assert lc.n_points == 500
    assert 0.9 < lc.median_flux < 1.1
    assert lc.flux_rms > 0


def test_nlc_summary() -> None:
    lc = _norm_lc()
    s = lc.summary()
    assert s["target_id"] == "TIC-100"
    assert s["sector"] == 1
    assert s["method"] == "median"
    assert s["n_points"] == 100
    assert "norm_factor" in s
    assert "median_flux" in s
    assert "flux_rms_ppm" in s


# ─────────────────────────────────────────────────────────────
# NormalizedMultiSector
# ─────────────────────────────────────────────────────────────

def test_multisector_n_sectors() -> None:
    m = NormalizedMultiSector(
        target_id="TIC-1",
        sectors=[_norm_lc(sector=1), _norm_lc(sector=2)],
    )
    assert m.n_sectors == 2


def test_multisector_combined_empty() -> None:
    m = NormalizedMultiSector(target_id="TIC-1", sectors=[])
    assert m.combined_time.size == 0
    assert m.combined_flux.size == 0
    assert m.combined_flux_err.size == 0


def test_multisector_combined_time_sorted() -> None:
    a = _norm_lc(sector=1, n=5)
    b = _norm_lc(sector=2, n=5)
    b.time = b.time + 100.0  # sonradan gelsin
    m = NormalizedMultiSector(target_id="TIC-1", sectors=[b, a])
    t = m.combined_time
    assert np.all(np.diff(t) >= 0)


def test_multisector_combined_flux_aligned_with_time() -> None:
    a = _norm_lc(sector=1, n=5)
    b = _norm_lc(sector=2, n=5)
    b.time = b.time + 100.0
    m = NormalizedMultiSector(target_id="TIC-1", sectors=[b, a])
    t = m.combined_time
    f = m.combined_flux
    assert len(t) == len(f) == 10
    # a'nin zamanlari kucuk, b'ninkiler buyuk
    a_times = a.time
    # ilk 5 a olmali (kucuk zamanlar once siralanir)
    assert np.allclose(t[:5], a_times)


def test_multisector_combined_flux_err() -> None:
    a = _norm_lc(sector=1, n=5)
    b = _norm_lc(sector=2, n=5)
    b.time = b.time + 100.0
    m = NormalizedMultiSector(target_id="TIC-1", sectors=[b, a])
    e = m.combined_flux_err
    assert len(e) == 10


# ─────────────────────────────────────────────────────────────
# __init__
# ─────────────────────────────────────────────────────────────

def test_normalizer_init_default() -> None:
    n = LightCurveNormalizer()
    assert n.method == NormalizationMethod.MEDIAN
    assert n.percentile == 95.0
    assert n.sigma_clip == 3.0


def test_normalizer_init_string() -> None:
    n = LightCurveNormalizer(method="mean")
    assert n.method == NormalizationMethod.MEAN


def test_normalizer_init_uppercase_string() -> None:
    n = LightCurveNormalizer(method="MEAN")
    assert n.method == NormalizationMethod.MEAN


def test_normalizer_init_invalid_string() -> None:
    with pytest.raises(ValueError, match="Geçersiz normalizasyon yöntemi"):
        LightCurveNormalizer(method="nonsense")


def test_normalizer_init_custom_percentile() -> None:
    n = LightCurveNormalizer(method="percentile", percentile=75.0)
    assert n.percentile == 75.0


# ─────────────────────────────────────────────────────────────
# _compute_norm_factor
# ─────────────────────────────────────────────────────────────

def test_norm_factor_median() -> None:
    n = LightCurveNormalizer(method="median")
    flux = np.array([1000.0, 1001.0, 999.0, 1002.0])
    factor = n._compute_norm_factor(flux)
    assert factor == 1000.5


def test_norm_factor_mean() -> None:
    n = LightCurveNormalizer(method="mean")
    flux = np.array([1000.0, 1000.0, 1000.0, 1004.0])
    factor = n._compute_norm_factor(flux)
    assert factor == 1001.0


def test_norm_factor_percentile() -> None:
    n = LightCurveNormalizer(method="percentile", percentile=50.0)
    flux = np.arange(1.0, 101.0)
    factor = n._compute_norm_factor(flux)
    assert 49.0 < factor < 52.0


def test_norm_factor_robust_mean() -> None:
    n = LightCurveNormalizer(method="robust_mean", sigma_clip=3.0)
    rng = np.random.default_rng(0)
    flux = 1000.0 + rng.normal(0, 1.0, size=200)
    factor = n._compute_norm_factor(flux)
    assert 999.0 < factor < 1001.0


def test_norm_factor_robust_mean_fallback_on_few_valid() -> None:
    """sigma_clip sonucu <10 nokta kalirsa median doner."""
    n = LightCurveNormalizer(method="robust_mean", sigma_clip=0.01)
    flux = np.array([1000.0] * 20 + [2000.0])
    factor = n._compute_norm_factor(flux)
    assert factor == 1000.0


def test_norm_factor_invalid_all_nonpositive() -> None:
    n = LightCurveNormalizer()
    with pytest.raises(ValueError, match="geçerli flux"):
        n._compute_norm_factor(np.array([-1.0, 0.0, -2.0]))


def test_norm_factor_invalid_all_nan() -> None:
    n = LightCurveNormalizer()
    with pytest.raises(ValueError, match="geçerli flux"):
        n._compute_norm_factor(np.array([np.nan, np.nan]))


def test_norm_factor_filters_nan() -> None:
    n = LightCurveNormalizer(method="median")
    flux = np.array([1000.0, np.nan, 1002.0, 998.0])
    factor = n._compute_norm_factor(flux)
    assert factor == pytest.approx(1000.0)


# ─────────────────────────────────────────────────────────────
# normalize
# ─────────────────────────────────────────────────────────────

def test_normalize_median() -> None:
    n = LightCurveNormalizer(method="median")
    lc = n.normalize(_raw_data(flux_scale=1000.0))
    assert isinstance(lc, NormalizedLightCurve)
    assert lc.target_id == "TIC-100"
    assert lc.method == "median"
    assert lc.norm_factor > 0
    # median ~1.0 olmali
    assert 0.99 < lc.median_flux < 1.01


def test_normalize_mean() -> None:
    n = LightCurveNormalizer(method="mean")
    lc = n.normalize(_raw_data(flux_scale=500.0))
    assert lc.norm_factor > 0
    assert 0.99 < lc.median_flux < 1.01


def test_normalize_copies_meta() -> None:
    n = LightCurveNormalizer()
    data = _raw_data()
    lc = n.normalize(data)
    assert lc.meta["CADENCE"] == "120s"


def test_normalize_copies_time() -> None:
    """time kopya olmali (mutasyon izole)."""
    n = LightCurveNormalizer()
    data = _raw_data()
    lc = n.normalize(data)
    assert np.array_equal(lc.time, data.time)
    assert lc.time is not data.time  # ayri array


def test_normalize_scales_flux_err() -> None:
    n = LightCurveNormalizer()
    data = _raw_data(flux_scale=1000.0, noise=10.0)
    lc = n.normalize(data)
    # flux_err = 10 / 1000 = 0.01
    assert np.allclose(lc.flux_err, 0.01, atol=1e-3)


def test_normalize_raises_when_factor_nonpositive() -> None:
    """Tum flux sifir/negatif -> hata."""
    n = LightCurveNormalizer()
    data = _raw_data()
    data.flux = np.array([0.0, -1.0, -2.0])
    with pytest.raises(ValueError, match="geçerli flux"):
        n.normalize(data)


# ─────────────────────────────────────────────────────────────
# normalize_multi
# ─────────────────────────────────────────────────────────────

def test_normalize_multi_success() -> None:
    n = LightCurveNormalizer()
    multi = MagicMock()
    multi.target_id = "TIC-100"
    multi.sectors = [_raw_data(sector=1), _raw_data(sector=2)]
    multi.n_sectors = 2
    result = n.normalize_multi(multi)
    assert isinstance(result, NormalizedMultiSector)
    assert result.n_sectors == 2


def test_normalize_multi_partial_failure() -> None:
    """Bir sektor basarisiz olsa bile digerleri tamamlanir."""
    n = LightCurveNormalizer()
    good = _raw_data(sector=1)
    bad = _raw_data(sector=2)
    bad.flux = np.array([0.0, -1.0])  # gecersiz

    multi = MagicMock()
    multi.target_id = "TIC-100"
    multi.sectors = [good, bad]
    multi.n_sectors = 2
    result = n.normalize_multi(multi)
    assert result.n_sectors == 1


def test_normalize_multi_all_fail_raises() -> None:
    n = LightCurveNormalizer()
    bad1 = _raw_data()
    bad1.flux = np.array([0.0, -1.0])
    bad2 = _raw_data()
    bad2.flux = np.array([0.0, -1.0])

    multi = MagicMock()
    multi.target_id = "TIC-100"
    multi.sectors = [bad1, bad2]
    multi.n_sectors = 2

    with pytest.raises(ValueError, match="hiçbir sektör"):
        n.normalize_multi(multi)


def test_normalize_multi_empty_sectors() -> None:
    n = LightCurveNormalizer()
    multi = MagicMock()
    multi.target_id = "TIC-100"
    multi.sectors = []
    multi.n_sectors = 0

    with pytest.raises(ValueError, match="hiçbir sektör"):
        n.normalize_multi(multi)
