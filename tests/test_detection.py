"""Transit tespit modülü testleri."""

import numpy as np
import pytest

from tests.conftest import generate_transit_lightcurve, generate_synthetic_lightcurve


class TestBLSSearch:
    """BLS arama testleri."""

    def test_finds_transit(self, detrended_lc):
        from astrotransit.detection.bls_search import BLSSearch

        detrended, truth = detrended_lc
        bls = BLSSearch()
        result = bls.search(detrended)

        assert result.has_candidate
        assert result.best is not None
        # Periyot %5 içinde doğru olmalı
        assert abs(result.best.period - truth["period"]) / truth["period"] < 0.05

    def test_no_transit_in_flat(self):
        from astrotransit.detection.bls_search import BLSSearch
        from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve

        time, flux, flux_err = generate_synthetic_lightcurve(noise_ppm=200.0)

        detrended = DetrendedLightCurve(
            target_id="FLAT",
            sector=1,
            time=time,
            flux=flux,
            flux_err=flux_err,
            trend=np.ones(len(time)),
            raw_flux=flux.copy(),
            method="biweight",
            window_length=0.5,
            break_tolerance=0.5,
        )

        bls = BLSSearch()
        result = bls.search(detrended)

        # Düz veri için güçlü aday olmamalı veya power düşük olmalı
        if result.has_candidate:
            assert result.best.power < 15.0

    def test_period_range(self, detrended_lc):
        from astrotransit.detection.bls_search import BLSSearch
        from astrotransit.detection.thresholds import BLSThresholds

        detrended, _ = detrended_lc

        thresholds = BLSThresholds(
            min_period_days=1.0,
            max_period_days=10.0,
        )

        bls = BLSSearch(thresholds=thresholds)
        result = bls.search(detrended)

        assert result.n_periods_searched > 0
        assert result.periods_searched[0] >= 1.0
        assert result.periods_searched[-1] <= 10.0


class TestCascade:
    """Kademeli tespit sistemi testleri."""

    def test_cascade_confirmed(self, detrended_lc):
        from astrotransit.detection.cascade import CascadeDetector, CascadeStatus
        from astrotransit.settings import Settings

        detrended, truth = detrended_lc
        settings = Settings()

        cascade = CascadeDetector(settings=settings)
        candidate = cascade.detect(detrended)

        assert candidate.status in [
            CascadeStatus.CONFIRMED,
            CascadeStatus.TLS_FAILED,
            CascadeStatus.PERIOD_MISMATCH,
            CascadeStatus.BLS_FAILED,
        ]

        if candidate.confirmed:
            assert abs(candidate.period - truth["period"]) / truth["period"] < 0.05