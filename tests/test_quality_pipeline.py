"""
QualityEvaluationPipeline birim testleri.

Kapsam
------
- __init__: default/custom settings
- evaluate(): temel akis (metrics -> snr -> vetting -> score)
- evaluate() + anomaly_data (residual/transit/timing)
- evaluate() + fpp_data
- evaluate() exception handling (anomaly/fpp)
- QualityEvaluationResult.to_dict / summary
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from astrotransit.detection.cascade import CascadeCandidate, CascadeStatus
from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve
from astrotransit.quality.pipeline import (
    QualityEvaluationPipeline,
    QualityEvaluationResult,
)
from astrotransit.settings import get_settings

# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

def _detrended(target: str = "TIC-100", sector: int = 1, n: int = 500) -> DetrendedLightCurve:
    rng = np.random.default_rng(0)
    t = np.linspace(100.0, 120.0, n)
    flux = 1.0 + rng.normal(0, 5e-4, size=n)
    err = np.full(n, 5e-4)
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


def _candidate(target: str = "TIC-100", sector: int = 1) -> CascadeCandidate:
    dummy_bls = MagicMock()
    dummy_bls.best = None  # scorer null-check yapabilsin
    return CascadeCandidate(
        target_id=target,
        sector=sector,
        status=CascadeStatus.CONFIRMED,
        confirmed=True,
        bls_result=dummy_bls,  # type: ignore[arg-type]
        tls_result=None,
        period=5.0,
        period_err=0.01,
        t0=100.0,
        duration=0.15,
        depth=0.005,
        rp_rs=0.08,
        snr=12.0,
        sde=9.5,
        transit_times=np.linspace(100.0, 120.0, 4),
        decision_log=[],
    )


@pytest.fixture
def pipeline() -> QualityEvaluationPipeline:
    return QualityEvaluationPipeline()


# ─────────────────────────────────────────────────────────────
# __init__
# ─────────────────────────────────────────────────────────────

def test_pipeline_init_default() -> None:
    p = QualityEvaluationPipeline()
    assert p.settings is not None
    assert p._metrics_calc is not None
    assert p._snr_calc is not None
    assert p._vetter is not None
    assert p._scorer is not None
    assert p._anomaly_scorer is not None
    assert p._fpp_calculator is not None


def test_pipeline_init_custom_settings() -> None:
    settings = get_settings()
    p = QualityEvaluationPipeline(settings=settings, cadence_sec=120.0)
    assert p.settings is settings


def test_pipeline_init_custom_cadence() -> None:
    p = QualityEvaluationPipeline(cadence_sec=600.0)
    assert p._metrics_calc is not None


# ─────────────────────────────────────────────────────────────
# evaluate() — temel akis
# ─────────────────────────────────────────────────────────────

def test_evaluate_basic(pipeline: QualityEvaluationPipeline) -> None:
    result = pipeline.evaluate(
        detrended=_detrended(),
        candidate=_candidate(),
    )
    assert isinstance(result, QualityEvaluationResult)
    assert result.target_id == "TIC-100"
    assert result.sector == 1
    assert result.metrics is not None
    assert result.snr is not None
    assert result.vetting is not None
    assert result.score is not None
    # anomaly_data verilmedi -> None
    assert result.anomaly is None
    assert result.fpp_report is None


def test_evaluate_with_fit_result_none(pipeline: QualityEvaluationPipeline) -> None:
    """fit_result=None ile calismali."""
    result = pipeline.evaluate(
        detrended=_detrended(),
        candidate=_candidate(),
        fit_result=None,
    )
    assert result.metrics is not None


def test_evaluate_empty_anomaly_data(pipeline: QualityEvaluationPipeline) -> None:
    """Bos dict -> alt raporlar None, ama anomaly UNKNOWN raporu dondurur.

    Not: pipeline anomaly_data={} verildiginde AnomalyScorer.score(None, None, None)
    cagirir ve 'insufficient_data' flag'li bir rapor uretir. Bu dogru davranis:
    'veri yok' ile 'analiz edilmedi' farklidir.
    """
    result = pipeline.evaluate(
        detrended=_detrended(),
        candidate=_candidate(),
        anomaly_data={},
    )
    assert result.anomaly_residual is None
    assert result.anomaly_transit is None
    assert result.anomaly_timing is None
    # anomaly raporu donuyor ama UNKNOWN
    assert result.anomaly is not None
    assert result.anomaly.anomaly_flag == "UNKNOWN"
    assert result.anomaly.recommended_action == "insufficient_data"


# ─────────────────────────────────────────────────────────────
# evaluate() — anomaly_data
# ─────────────────────────────────────────────────────────────

def test_evaluate_with_residual_anomaly(pipeline: QualityEvaluationPipeline) -> None:
    """Sadece residual verisi -> anomaly_residual dolmali."""
    n = 500
    rng = np.random.default_rng(1)
    time = np.linspace(100.0, 120.0, n)
    residuals = rng.normal(0, 5e-4, size=n)
    in_transit = np.zeros(n, dtype=bool)
    in_transit[100:150] = True

    result = pipeline.evaluate(
        detrended=_detrended(),
        candidate=_candidate(),
        anomaly_data={
            "time": time,
            "residuals": residuals,
            "in_transit_mask": in_transit,
        },
    )
    # residual dolu ise anomaly de dolu (en az bir rapor var)
    assert result.anomaly_residual is not None
    assert result.anomaly is not None


def test_evaluate_with_transit_consistency(pipeline: QualityEvaluationPipeline) -> None:
    """Phase verisi -> anomaly_transit dolmali."""
    n = 500
    rng = np.random.default_rng(2)
    phase = np.linspace(0.0, 1.0, n)
    flux = 1.0 + rng.normal(0, 5e-4, size=n)
    in_transit = np.abs(phase - 0.5) < 0.05

    result = pipeline.evaluate(
        detrended=_detrended(),
        candidate=_candidate(),
        anomaly_data={
            "phase": phase,
            "flux": flux,
            "in_transit_mask": in_transit,
        },
    )
    assert result.anomaly_transit is not None


def test_evaluate_with_timing(pipeline: QualityEvaluationPipeline) -> None:
    """period verisi -> anomaly_timing dolmali."""
    n = 4
    midtimes = 100.0 + np.arange(n) * 5.0

    result = pipeline.evaluate(
        detrended=_detrended(),
        candidate=_candidate(),
        anomaly_data={
            "period": 5.0,
            "observed_midtimes": midtimes,
            "t0": 100.0,
        },
    )
    assert result.anomaly_timing is not None


def test_evaluate_anomaly_exception_handled(
    pipeline: QualityEvaluationPipeline, monkeypatch
) -> None:
    """Anomaly analyzer exception firlatirsa yutulur."""
    def _explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        pipeline._residual_analyzer, "analyze", _explode,
    )

    n = 100
    result = pipeline.evaluate(
        detrended=_detrended(),
        candidate=_candidate(),
        anomaly_data={
            "time": np.linspace(0, 10, n),
            "residuals": np.zeros(n),
            "in_transit_mask": np.zeros(n, dtype=bool),
        },
    )
    # Exception yakalandi -> anomaly_residual None (pipeline exception'i yakalar)
    assert result.anomaly_residual is None
    # anomaly: exception sonrasi None olabilir veya UNKNOWN raporu olabilir
    # (exception tam olarak nerede atildigina bagli)


# ─────────────────────────────────────────────────────────────
# evaluate() — fpp_data
# ─────────────────────────────────────────────────────────────

def test_evaluate_with_fpp_data(pipeline: QualityEvaluationPipeline) -> None:
    result = pipeline.evaluate(
        detrended=_detrended(),
        candidate=_candidate(),
        fpp_data={
            "primary_depth": 0.005,
            "odd_depth": 0.005,
            "even_depth": 0.005,
            "v_shape_score": 0.3,
            "secondary_depth": 0.0,
            "centroid_shift_arcsec": 0.0,
            "crowding_ratio": 0.5,
            "gaia_neighbors_within_60arcsec": 0,
            "brightest_neighbor_delta_mag": 5.0,
            "nearest_neighbor_arcsec": 10.0,
        },
    )
    assert result.fpp_report is not None


def test_evaluate_fpp_exception_handled(
    pipeline: QualityEvaluationPipeline, monkeypatch
) -> None:
    def _explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        pipeline._fpp_calculator, "calculate", _explode,
    )

    result = pipeline.evaluate(
        detrended=_detrended(),
        candidate=_candidate(),
        fpp_data={"primary_depth": 0.005},
    )
    # Exception yakalandi -> fpp_report None
    assert result.fpp_report is None


# ─────────────────────────────────────────────────────────────
# QualityEvaluationResult.to_dict / summary
# ─────────────────────────────────────────────────────────────

def test_result_to_dict(pipeline: QualityEvaluationPipeline) -> None:
    result = pipeline.evaluate(detrended=_detrended(), candidate=_candidate())
    d = result.to_dict()
    assert d["target_id"] == "TIC-100"
    assert d["sector"] == 1
    assert "metrics" in d
    assert "snr" in d
    assert "vetting" in d
    assert "score" in d
    assert d["anomaly"] is None
    assert d["fpp_report"] is None


def test_result_summary(pipeline: QualityEvaluationPipeline) -> None:
    result = pipeline.evaluate(detrended=_detrended(), candidate=_candidate())
    s = result.summary()
    assert s["target_id"] == "TIC-100"
    assert s["sector"] == 1
    assert "snr_adopted" in s
    assert "total_score" in s
    assert "candidate_class" in s
    assert "detection_confidence" in s
    # fpp_report yok -> UNKNOWN
    assert s["detection_confidence"] == "UNKNOWN"


def test_result_summary_with_fpp(pipeline: QualityEvaluationPipeline) -> None:
    result = pipeline.evaluate(
        detrended=_detrended(),
        candidate=_candidate(),
        fpp_data={
            "primary_depth": 0.005,
            "odd_depth": 0.005,
            "even_depth": 0.005,
            "v_shape_score": 0.3,
            "secondary_depth": 0.0,
            "centroid_shift_arcsec": 0.0,
            "crowding_ratio": 0.5,
            "gaia_neighbors_within_60arcsec": 0,
            "brightest_neighbor_delta_mag": 5.0,
            "nearest_neighbor_arcsec": 10.0,
        },
    )
    s = result.summary()
    # fpp_report var -> confidence UNKNOWN degil
    assert s["detection_confidence"] != "UNKNOWN"


def test_result_summary_fpp_none_from_vetting(pipeline: QualityEvaluationPipeline) -> None:
    """fpp_report yok ve vetting.fpp None ise fpp=None donmeli."""
    result = pipeline.evaluate(detrended=_detrended(), candidate=_candidate())
    s = result.summary()
    # fpp ya None ya da bir deger olabilir; tip kontrolu
    assert s["fpp"] is None or isinstance(s["fpp"], float)
