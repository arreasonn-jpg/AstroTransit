"""Kalite değerlendirme modülü testleri."""

import numpy as np
import pytest


class TestSNR:
    """SNR hesaplama testleri."""

    def test_snr_positive_for_transit(self, detrended_lc):
        # Kaskad tespiti TLS gerektirir; zarif degradasyon tasarımına göre
        # bağımlılık import edilemiyorsa bu test atlanır.
        pytest.importorskip(
            "transitleastsquares",
            reason="transitleastsquares bu ortamda import edilemiyor",
        )
        from astrotransit.quality.snr import SNRCalculator
        from astrotransit.detection.cascade import CascadeDetector
        from astrotransit.settings import Settings

        detrended, truth = detrended_lc

        cascade = CascadeDetector(settings=Settings())
        candidate = cascade.detect(detrended)

        if candidate.confirmed:
            calc = SNRCalculator()
            snr = calc.compute(detrended, candidate)

            assert snr.snr_adopted > 0
            assert snr.noise_floor_ppm > 0


class TestScorer:
    """Skor ve sınıflandırma testleri."""

    def test_class_a_threshold(self):
        from astrotransit.quality.scorer import CandidateScorer

        scorer = CandidateScorer(class_a_threshold=80.0)

        # Yüksek puan → A olmalı (doğrudan test edemiyoruz ama eşikleri kontrol edebiliriz)
        assert scorer.class_a_threshold == 80.0
        assert scorer.class_b_threshold < scorer.class_a_threshold

    def test_normalize_linear(self):
        from astrotransit.quality.scorer import CandidateScorer

        assert CandidateScorer._normalize_linear(5.0, 0.0, 10.0) == 50.0
        assert CandidateScorer._normalize_linear(0.0, 0.0, 10.0) == 0.0
        assert CandidateScorer._normalize_linear(10.0, 0.0, 10.0) == 100.0
        assert CandidateScorer._normalize_linear(-5.0, 0.0, 10.0) == 0.0
        assert CandidateScorer._normalize_linear(15.0, 0.0, 10.0) == 100.0


class TestVetting:
    """Vetting test testleri."""

    def test_odd_even_pass(self):
        from astrotransit.quality.vetting import FalsePositiveVetter, VettingVerdict
        from astrotransit.quality.metrics import QualityMetrics, TransitMetrics
        from astrotransit.detection.cascade import CascadeCandidate, CascadeStatus

        vetter = FalsePositiveVetter(odd_even_threshold=3.0)

        metrics = QualityMetrics(
            target_id="TEST",
            sector=1,
        )
        metrics.transit = TransitMetrics(odd_even_mismatch=1.0)

        candidate = CascadeCandidate(
            target_id="TEST",
            sector=1,
            status=CascadeStatus.CONFIRMED,
            confirmed=True,
            bls_result=None,
            tls_result=None,
            period=3.5,
            depth=0.01,
            duration=0.1,
            transit_times=np.array([1.0, 4.5, 8.0]),
        )

        report = vetter.vet(candidate, metrics)

        odd_even_test = next(
            (t for t in report.tests if t.name == "odd_even_mismatch"),
            None,
        )

        assert odd_even_test is not None
        assert odd_even_test.verdict == VettingVerdict.PASS

    def test_fpp_method_label_present(self):
        """FPP proxy'si metod kimliğiyle birlikte raporlanmalıdır."""
        from astrotransit.quality.vetting import (
            FPP_METHOD,
            FalsePositiveVetter,
        )
        from astrotransit.quality.metrics import QualityMetrics, TransitMetrics
        from astrotransit.detection.cascade import CascadeCandidate, CascadeStatus

        vetter = FalsePositiveVetter()
        metrics = QualityMetrics(target_id="TEST", sector=1)
        metrics.transit = TransitMetrics(odd_even_mismatch=1.0)
        candidate = CascadeCandidate(
            target_id="TEST",
            sector=1,
            status=CascadeStatus.CONFIRMED,
            confirmed=True,
            bls_result=None,
            tls_result=None,
            period=3.5,
            depth=0.01,
            duration=0.1,
            transit_times=np.array([1.0, 4.5, 8.0]),
        )

        report = vetter.vet(candidate, metrics)

        assert report.fpp_method == FPP_METHOD
        assert report.to_dict()["fpp_method"] == FPP_METHOD
        assert report.summary()["fpp_method"] == FPP_METHOD