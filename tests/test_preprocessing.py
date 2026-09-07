"""Ön işleme modülü testleri."""

import numpy as np
import pytest

from tests.conftest import generate_synthetic_lightcurve, generate_transit_lightcurve


class TestNormalization:
    """Normalizasyon testleri."""

    def test_median_normalization(self, tess_lc_data):
        from astrotransit.preprocessing.normalization import LightCurveNormalizer

        lc_data, _ = tess_lc_data
        normalizer = LightCurveNormalizer(method="median")
        result = normalizer.normalize(lc_data)

        assert abs(result.median_flux - 1.0) < 0.01
        assert result.n_points == lc_data.n_points_clean
        assert result.norm_factor > 0

    def test_mean_normalization(self, tess_lc_data):
        from astrotransit.preprocessing.normalization import LightCurveNormalizer

        lc_data, _ = tess_lc_data
        normalizer = LightCurveNormalizer(method="mean")
        result = normalizer.normalize(lc_data)

        assert abs(np.mean(result.flux) - 1.0) < 0.01

    def test_invalid_method(self):
        from astrotransit.preprocessing.normalization import LightCurveNormalizer

        with pytest.raises(ValueError):
            LightCurveNormalizer(method="invalid")


class TestCleaning:
    """Temizleme testleri."""

    def test_sigma_clip(self):
        from astrotransit.preprocessing.cleaning import LightCurveCleaner
        from astrotransit.preprocessing.normalization import NormalizedLightCurve

        rng = np.random.default_rng(42)
        n = 1000
        time = np.arange(n) * 0.001389
        flux = np.ones(n) + rng.normal(0, 1e-4, n)
        flux_err = np.full(n, 1e-4)

        # Aykırı noktalar ekle
        flux[100] = 1.1
        flux[500] = 0.9

        normalized = NormalizedLightCurve(
            target_id="TEST",
            sector=1,
            time=time,
            flux=flux,
            flux_err=flux_err,
            norm_factor=1.0,
            method="median",
            meta={},
        )

        cleaner = LightCurveCleaner(sigma_clip_flux=3.0)
        result = cleaner.clean(normalized)

        assert result.n_points < n
        assert result.n_points > n - 10

    def test_segment_detection(self):
        from astrotransit.preprocessing.cleaning import LightCurveCleaner
        from astrotransit.preprocessing.normalization import NormalizedLightCurve

        # Boşluklu veri oluştur
        t1 = np.arange(500) * 0.001389
        t2 = np.arange(500) * 0.001389 + 5.0  # 5 günlük boşluk
        time = np.concatenate([t1, t2])
        flux = np.ones(1000)
        flux_err = np.full(1000, 1e-4)

        normalized = NormalizedLightCurve(
            target_id="TEST",
            sector=1,
            time=time,
            flux=flux,
            flux_err=flux_err,
            norm_factor=1.0,
            method="median",
            meta={},
        )

        cleaner = LightCurveCleaner(gap_threshold_days=0.5)
        result = cleaner.clean(normalized)

        assert result.n_segments == 2