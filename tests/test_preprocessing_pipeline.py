"""
TESSPreprocessingPipeline birim testleri.

Strateji
--------
Alt moduller (normalizer, cleaner, detrend) gercek instance'lardir ama
`run()` icinde cagrilan metodlar monkeypatch ile mock'lanir. Boylece
pipeline orkestrasyonu test edilirken agir wotan/astropy islemleri atlanir.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from astrotransit.preprocessing.cleaning import CleanedLightCurve, LightCurveSegment
from astrotransit.preprocessing.normalization import NormalizedLightCurve
from astrotransit.preprocessing.pipeline import (
    PreprocessedLightCurve,
    PreprocessedMultiSector,
    TESSPreprocessingPipeline,
)
from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve

# ─────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────

def _normalized(target: str = "TIC-100", sector: int = 1, n: int = 200) -> NormalizedLightCurve:
    rng = np.random.default_rng(0)
    return NormalizedLightCurve(
        target_id=target,
        sector=sector,
        time=np.linspace(100.0, 120.0, n),
        flux=1.0 + rng.normal(0, 5e-4, size=n),
        flux_err=np.full(n, 5e-4),
        norm_factor=1.0,
        method="median",
        meta={"CADENCE": "120s"},
    )


def _cleaned(target: str = "TIC-100", sector: int = 1, n: int = 200) -> CleanedLightCurve:
    rng = np.random.default_rng(0)
    time = np.linspace(100.0, 120.0, n)
    flux = 1.0 + rng.normal(0, 5e-4, size=n)
    err = np.full(n, 5e-4)
    segment = LightCurveSegment(
        time=time,
        flux=flux,
        flux_err=err,
        start_time=float(time[0]),
        end_time=float(time[-1]),
        segment_index=0,
    )
    return CleanedLightCurve(
        target_id=target,
        sector=sector,
        time=time,
        flux=flux,
        flux_err=err,
        segments=[segment],
        n_points_input=n,
        n_gaps_detected=0,
        meta={"CADENCE": "120s"},
    )


def _detrended(target: str = "TIC-100", sector: int = 1, n: int = 200) -> DetrendedLightCurve:
    rng = np.random.default_rng(0)
    time = np.linspace(100.0, 120.0, n)
    flux = 1.0 + rng.normal(0, 5e-4, size=n)
    return DetrendedLightCurve(
        target_id=target,
        sector=sector,
        time=time,
        flux=flux,
        flux_err=np.full(n, 5e-4),
        trend=np.ones(n),
        raw_flux=flux + 0.001,
        method="biweight",
        window_length=0.5,
        break_tolerance=0.5,
        meta={"CADENCE": "120s"},
    )


def _raw_data(target: str = "TIC-100", sector: int = 1):
    """TESSLightCurveData benzeri bir mock."""
    m = MagicMock()
    m.target_id = target
    m.sector = sector
    return m


@pytest.fixture
def pipeline() -> TESSPreprocessingPipeline:
    return TESSPreprocessingPipeline()


# ─────────────────────────────────────────────────────────────────
# PreprocessedLightCurve.summary
# ─────────────────────────────────────────────────────────────────

def test_preprocessed_lightcurve_summary() -> None:
    p = PreprocessedLightCurve(
        target_id="TIC-1",
        sector=1,
        normalized=_normalized(),
        cleaned=_cleaned(),
        detrended=_detrended(),
    )
    s = p.summary()
    assert s["target_id"] == "TIC-1"
    assert s["sector"] == 1
    assert "normalization" in s
    assert "cleaning" in s
    assert "detrending" in s


# ─────────────────────────────────────────────────────────────────
# PreprocessedMultiSector
# ─────────────────────────────────────────────────────────────────

def test_preprocessed_multisector_n_sectors() -> None:
    m = PreprocessedMultiSector(
        target_id="TIC-1",
        sectors=[
            PreprocessedLightCurve(
                target_id="TIC-1", sector=1,
                normalized=_normalized(sector=1),
                cleaned=_cleaned(sector=1),
                detrended=_detrended(sector=1),
            ),
            PreprocessedLightCurve(
                target_id="TIC-1", sector=2,
                normalized=_normalized(sector=2),
                cleaned=_cleaned(sector=2),
                detrended=_detrended(sector=2),
            ),
        ],
    )
    assert m.n_sectors == 2


def test_preprocessed_multisector_empty() -> None:
    m = PreprocessedMultiSector(target_id="TIC-1", sectors=[])
    assert m.n_sectors == 0


def test_preprocessed_multisector_summary() -> None:
    m = PreprocessedMultiSector(
        target_id="TIC-1",
        sectors=[
            PreprocessedLightCurve(
                target_id="TIC-1", sector=1,
                normalized=_normalized(),
                cleaned=_cleaned(),
                detrended=_detrended(),
            ),
        ],
    )
    s = m.summary()
    assert s["target_id"] == "TIC-1"
    assert s["n_sectors"] == 1
    assert len(s["sectors"]) == 1


# ─────────────────────────────────────────────────────────────────
# __init__
# ─────────────────────────────────────────────────────────────────

def test_pipeline_init_default(pipeline: TESSPreprocessingPipeline) -> None:
    assert pipeline.settings is not None
    assert pipeline._normalizer is not None
    assert pipeline._cleaner is not None
    assert pipeline._detrend is not None


def test_pipeline_init_with_settings() -> None:
    from astrotransit.settings import get_settings
    p = TESSPreprocessingPipeline(settings=get_settings())
    assert p.settings is get_settings()


def test_pipeline_init_custom_norm_method() -> None:
    p = TESSPreprocessingPipeline(norm_method="median")
    assert p._normalizer is not None


def test_pipeline_init_window_override() -> None:
    p = TESSPreprocessingPipeline(window_length=1.5)
    assert p._detrend is not None


# ─────────────────────────────────────────────────────────────────
# run() — monkeypatch ile
# ─────────────────────────────────────────────────────────────────

def test_run_full_flow(pipeline: TESSPreprocessingPipeline, monkeypatch) -> None:
    raw = _raw_data()
    norm = _normalized()
    cln = _cleaned()
    det = _detrended()

    monkeypatch.setattr(
        pipeline._normalizer, "normalize", lambda data: norm,
    )
    monkeypatch.setattr(
        pipeline._cleaner, "clean", lambda n: cln,
    )
    monkeypatch.setattr(
        pipeline._detrend, "detrend", lambda c: det,
    )

    result = pipeline.run(raw)
    assert isinstance(result, PreprocessedLightCurve)
    assert result.target_id == "TIC-100"
    assert result.sector == 1
    assert result.normalized is norm
    assert result.cleaned is cln
    assert result.detrended is det


def test_run_calls_in_order(pipeline: TESSPreprocessingPipeline, monkeypatch) -> None:
    calls: list[str] = []

    def fake_normalize(data):
        calls.append("normalize")
        return _normalized()

    def fake_clean(n):
        calls.append("clean")
        return _cleaned()

    def fake_detrend(c):
        calls.append("detrend")
        return _detrended()

    monkeypatch.setattr(pipeline._normalizer, "normalize", fake_normalize)
    monkeypatch.setattr(pipeline._cleaner, "clean", fake_clean)
    monkeypatch.setattr(pipeline._detrend, "detrend", fake_detrend)

    pipeline.run(_raw_data())
    assert calls == ["normalize", "clean", "detrend"]


# ─────────────────────────────────────────────────────────────────
# run_multi()
# ─────────────────────────────────────────────────────────────────

def _multi_data(sectors: list[int], target: str = "TIC-100"):
    m = MagicMock()
    m.target_id = target
    m.sectors = [_raw_data(target, s) for s in sectors]
    m.n_sectors = len(sectors)
    return m


def test_run_multi_all_success(pipeline: TESSPreprocessingPipeline, monkeypatch) -> None:
    monkeypatch.setattr(pipeline._normalizer, "normalize", lambda data: _normalized(sector=data.sector))
    monkeypatch.setattr(pipeline._cleaner, "clean", lambda n: _cleaned())
    monkeypatch.setattr(pipeline._detrend, "detrend", lambda c: _detrended())

    multi = _multi_data([1, 2, 3])
    result = pipeline.run_multi(multi)
    assert isinstance(result, PreprocessedMultiSector)
    assert result.target_id == "TIC-100"
    assert result.n_sectors == 3


def test_run_multi_partial_failure(pipeline: TESSPreprocessingPipeline, monkeypatch) -> None:
    """Bir sektorde hata olsa bile digerleri devam eder."""
    call_count = {"n": 0}

    def maybe_fail(data):
        call_count["n"] += 1
        if data.sector == 2:
            raise RuntimeError("boom sector 2")
        return _normalized(sector=data.sector)

    monkeypatch.setattr(pipeline._normalizer, "normalize", maybe_fail)
    monkeypatch.setattr(pipeline._cleaner, "clean", lambda n: _cleaned())
    monkeypatch.setattr(pipeline._detrend, "detrend", lambda c: _detrended())

    result = pipeline.run_multi(_multi_data([1, 2, 3]))
    # 2 basarili, 1 fail
    assert result.n_sectors == 2


def test_run_multi_all_fail_raises(pipeline: TESSPreprocessingPipeline, monkeypatch) -> None:
    def always_fail(data):
        raise RuntimeError("all fail")

    monkeypatch.setattr(pipeline._normalizer, "normalize", always_fail)

    with pytest.raises(RuntimeError, match="hiçbir sektör işlenemedi"):
        pipeline.run_multi(_multi_data([1, 2]))


def test_run_multi_empty_sectors(pipeline: TESSPreprocessingPipeline) -> None:
    with pytest.raises(RuntimeError, match="hiçbir sektör işlenemedi"):
        pipeline.run_multi(_multi_data([]))
