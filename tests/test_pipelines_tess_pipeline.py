"""astrotransit/pipelines/tess_pipeline.py için testler."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from astrotransit.data.catalog_client import StellarProperties
from astrotransit.data.tess_client import TESSLightCurveData, TESSNoDataError
from astrotransit.detection.cascade import CascadeStatus
from astrotransit.pipelines.tess_pipeline import (
    TESSPipeline,
    TESSSectorResult,
    TESSTargetResult,
)


def _make_lc_data(sector=14, n=200, target="TIC 123"):
    return TESSLightCurveData(
        target_id=target, sector=sector,
        time=np.arange(n, dtype=float) + 1000.0,
        flux=np.ones(n), flux_err=np.full(n, 1e-4),
        quality=np.zeros(n, dtype=np.int32),
        cadence=120.0, time_format="btjd",
        meta={"SECTOR": sector},
        n_points_raw=n, n_points_clean=n,
    )


def _make_cascade_candidate(status=CascadeStatus.CONFIRMED, confirmed=True):
    return SimpleNamespace(
        status=status, confirmed=confirmed,
        bls_result=MagicMock(), tls_result=MagicMock(),
    )


def _make_quality_result(score=95.0, cls="A"):
    class _Class:
        value = cls
    return SimpleNamespace(
        score=SimpleNamespace(total_score=score, candidate_class=_Class()),
        vetting=MagicMock(),
    )


def _patch_pipeline_deps(monkeypatch):
    import astrotransit.pipelines.tess_pipeline as mod
    monkeypatch.setattr(mod, "TESSClient", lambda **kw: MagicMock())
    monkeypatch.setattr(mod, "CatalogClient", lambda: MagicMock())
    monkeypatch.setattr(mod, "TESSPreprocessingPipeline", lambda settings: MagicMock())
    monkeypatch.setattr(mod, "OutputManager", lambda settings=None: MagicMock())
    monkeypatch.setattr(mod, "VisualizationReportGenerator", lambda settings: MagicMock())


@pytest.fixture
def pipe(monkeypatch, tmp_path):
    _patch_pipeline_deps(monkeypatch)
    p = TESSPipeline()
    p._tess_client = MagicMock()
    p._catalog = MagicMock()
    p._preprocessing = MagicMock()
    p._output = MagicMock()
    p._viz = MagicMock()
    return p


# ═══════════════════════════════════════════════════════
# Dataclass summaries
# ═══════════════════════════════════════════════════════

def test_target_result_summary_minimal():
    r = TESSTargetResult(target_id="TIC 1")
    s = r.summary()
    assert s["target_id"] == "TIC 1"
    assert s["success"] is False
    assert "long_period" not in s


def test_target_result_summary_with_long_period():
    lp = SimpleNamespace(summary=lambda: {"P": 5.0})
    rec = SimpleNamespace(to_flat_dict=lambda: {"x": 1})
    r = TESSTargetResult(target_id="TIC 1", long_period=lp, long_period_record=rec)
    s = r.summary()
    assert s["long_period"] == {"P": 5.0}
    assert s["long_period_record"] == {"x": 1}


def test_sector_result_summary_without_quality():
    r = TESSSectorResult(target_id="TIC 1", sector=1)
    assert "score" not in r.summary()


def test_sector_result_summary_with_quality():
    q = _make_quality_result(score=80.0, cls="B")
    r = TESSSectorResult(target_id="TIC 1", sector=1, quality=q)
    s = r.summary()
    assert s["score"] == 80.0
    assert s["class"] == "B"


# ═══════════════════════════════════════════════════════
# __init__
# ═══════════════════════════════════════════════════════

def test_init_skip_catalog_and_visualization(monkeypatch):
    _patch_pipeline_deps(monkeypatch)
    p = TESSPipeline(skip_catalog=True, skip_visualization=True)
    assert p._catalog is None
    assert p._viz is None


def test_init_default_has_modules(monkeypatch):
    _patch_pipeline_deps(monkeypatch)
    p = TESSPipeline()
    assert p._catalog is not None
    assert p._viz is not None
    assert p._output is not None


def test_context_manager(monkeypatch):
    _patch_pipeline_deps(monkeypatch)
    with TESSPipeline() as p:
        assert isinstance(p, TESSPipeline)
    p._output.close.assert_called()


# ═══════════════════════════════════════════════════════
# _get_stellar_properties
# ═══════════════════════════════════════════════════════

def test_get_stellar_properties_no_catalog(monkeypatch):
    _patch_pipeline_deps(monkeypatch)
    p = TESSPipeline(skip_catalog=True)
    assert p._get_stellar_properties("TIC 123").source == "skipped"


def test_get_stellar_properties_valid(pipe):
    props = StellarProperties(teff=5700, radius=1.0, mass=1.0, source="catalog")
    pipe._catalog.get_stellar_properties.return_value = props
    assert pipe._get_stellar_properties("TIC 123").source == "catalog"


def test_get_stellar_properties_error(pipe):
    pipe._catalog.get_stellar_properties.side_effect = RuntimeError("net")
    assert pipe._get_stellar_properties("TIC 123").source == "failed"


# ═══════════════════════════════════════════════════════
# run_target hata yolları
# ═══════════════════════════════════════════════════════

def _stub_heavy_modules(monkeypatch):
    import astrotransit.pipelines.tess_pipeline as mod
    fake_cascade_cls = MagicMock()
    fake_cascade_inst = MagicMock()
    fake_cascade_inst.detect.return_value = _make_cascade_candidate(
        status=CascadeStatus.BLS_FAILED, confirmed=False
    )
    fake_cascade_cls.return_value = fake_cascade_inst
    monkeypatch.setattr(mod, "CascadeDetector", fake_cascade_cls)
    monkeypatch.setattr(mod, "ModelingOrchestrator", MagicMock())
    monkeypatch.setattr(mod, "QualityEvaluationPipeline", MagicMock())
    return fake_cascade_inst


def test_run_target_no_data(pipe, monkeypatch):
    pipe._catalog.get_stellar_properties.return_value = StellarProperties(source="skipped")
    pipe._tess_client.get_all_sectors.side_effect = TESSNoDataError("yok")
    _stub_heavy_modules(monkeypatch)
    result = pipe.run_target("TIC 123")
    assert result.success is False
    assert "yok" in result.error or "veri" in result.error.lower()


def test_run_target_explicit_sectors_all_empty(pipe, monkeypatch):
    pipe._catalog.get_stellar_properties.return_value = StellarProperties(source="skipped")
    pipe._tess_client.get_lightcurve.side_effect = TESSNoDataError("yok")
    _stub_heavy_modules(monkeypatch)
    result = pipe.run_target("TIC 123", sectors=[1, 2])
    assert result.success is False
    assert "Hiçbir sektörde" in result.error


def test_run_target_generic_error(pipe, monkeypatch):
    pipe._catalog.get_stellar_properties.return_value = StellarProperties(source="skipped")
    pipe._tess_client.get_all_sectors.side_effect = RuntimeError("kaboom")
    _stub_heavy_modules(monkeypatch)
    result = pipe.run_target("TIC 123")
    assert result.success is False
    assert "Veri indirme hatası" in result.error


def test_run_target_bls_failed_early_exit(pipe, monkeypatch):
    pipe._catalog.get_stellar_properties.return_value = StellarProperties(source="skipped")
    pipe._tess_client.get_all_sectors.return_value = SimpleNamespace(
        sectors=[_make_lc_data()]
    )
    pipe._preprocessing.run.return_value = SimpleNamespace(
        detrended=MagicMock(), normalized=MagicMock()
    )
    fake_cascade = _stub_heavy_modules(monkeypatch)
    result = pipe.run_target("TIC 123")
    assert result.sectors_processed == 1
    assert result.candidates_found == 0
    assert result.success is True
    fake_cascade.detect.assert_called_once()


def test_run_target_bls_failed_viz_error(pipe, monkeypatch):
    pipe._catalog.get_stellar_properties.return_value = StellarProperties(source="skipped")
    pipe._tess_client.get_all_sectors.return_value = SimpleNamespace(
        sectors=[_make_lc_data()]
    )
    pipe._preprocessing.run.return_value = SimpleNamespace(
        detrended=MagicMock(), normalized=MagicMock()
    )
    pipe._viz.generate.side_effect = RuntimeError("viz error")
    _stub_heavy_modules(monkeypatch)
    result = pipe.run_target("TIC 123")
    assert result.success is True


# ═══════════════════════════════════════════════════════
# _process_sector izole
# ═══════════════════════════════════════════════════════

def _sector_kwargs():
    return dict(
        cascade_detector=MagicMock(),
        modeling=MagicMock(),
        quality_pipeline=MagicMock(),
        stellar_props=StellarProperties(source="skipped"),
        stellar_radius=1.0,
        stellar_mass=1.0,
        stellar_teff=5778.0,
    )


def test_process_sector_preprocessing_error(pipe):
    pipe._preprocessing.run.side_effect = RuntimeError("prep fail")
    r = pipe._process_sector(lc_data=_make_lc_data(), **_sector_kwargs())
    assert r.error.startswith("Ön işleme hatası")
    assert r.success is False


def test_process_sector_detection_error(pipe):
    pipe._preprocessing.run.return_value = SimpleNamespace(
        detrended=MagicMock(), normalized=MagicMock()
    )
    kw = _sector_kwargs()
    kw["cascade_detector"].detect.side_effect = RuntimeError("detect fail")
    r = pipe._process_sector(lc_data=_make_lc_data(), **kw)
    assert r.error.startswith("Tespit hatası")


def test_process_sector_bls_failed(pipe):
    pipe._preprocessing.run.return_value = SimpleNamespace(
        detrended=MagicMock(), normalized=MagicMock()
    )
    kw = _sector_kwargs()
    kw["cascade_detector"].detect.return_value = _make_cascade_candidate(
        status=CascadeStatus.BLS_FAILED, confirmed=False
    )
    r = pipe._process_sector(lc_data=_make_lc_data(), **kw)
    assert r.success is True
    assert r.has_candidate is False


def test_process_sector_confirmed_full_flow(pipe):
    pipe._preprocessing.run.return_value = SimpleNamespace(
        detrended=MagicMock(), normalized=MagicMock()
    )
    kw = _sector_kwargs()
    kw["cascade_detector"].detect.return_value = _make_cascade_candidate(
        status=CascadeStatus.CONFIRMED, confirmed=True
    )
    kw["modeling"].fit.return_value = MagicMock()
    kw["quality_pipeline"].evaluate.return_value = _make_quality_result()
    pipe._output.write.return_value = MagicMock()
    pipe._viz.generate.return_value = MagicMock()

    r = pipe._process_sector(lc_data=_make_lc_data(), **kw)
    assert r.success is True
    assert r.has_candidate is True
    assert r.candidate_confirmed is True
    assert r.fit_result is not None
    assert r.quality is not None
    assert r.record is not None
    assert r.viz is not None


def test_process_sector_modeling_error_continues(pipe):
    pipe._preprocessing.run.return_value = SimpleNamespace(
        detrended=MagicMock(), normalized=MagicMock()
    )
    kw = _sector_kwargs()
    kw["cascade_detector"].detect.return_value = _make_cascade_candidate(
        status=CascadeStatus.CONFIRMED, confirmed=True
    )
    kw["modeling"].fit.side_effect = RuntimeError("fit fail")
    kw["quality_pipeline"].evaluate.return_value = _make_quality_result()
    r = pipe._process_sector(lc_data=_make_lc_data(), **kw)
    assert r.success is True


def test_process_sector_quality_error_continues(pipe):
    pipe._preprocessing.run.return_value = SimpleNamespace(
        detrended=MagicMock(), normalized=MagicMock()
    )
    kw = _sector_kwargs()
    kw["cascade_detector"].detect.return_value = _make_cascade_candidate(
        status=CascadeStatus.CONFIRMED, confirmed=True
    )
    kw["modeling"].fit.return_value = MagicMock()
    kw["quality_pipeline"].evaluate.side_effect = RuntimeError("quality fail")
    r = pipe._process_sector(lc_data=_make_lc_data(), **kw)
    assert r.success is True
    assert r.quality is None


def test_process_sector_output_error_continues(pipe):
    pipe._preprocessing.run.return_value = SimpleNamespace(
        detrended=MagicMock(), normalized=MagicMock()
    )
    kw = _sector_kwargs()
    kw["cascade_detector"].detect.return_value = _make_cascade_candidate(
        status=CascadeStatus.CONFIRMED, confirmed=True
    )
    kw["modeling"].fit.return_value = MagicMock()
    kw["quality_pipeline"].evaluate.return_value = _make_quality_result()
    pipe._output.write.side_effect = RuntimeError("output fail")
    r = pipe._process_sector(lc_data=_make_lc_data(), **kw)
    assert r.success is True
    assert r.record is None


def test_process_sector_visualization_error_continues(pipe):
    pipe._preprocessing.run.return_value = SimpleNamespace(
        detrended=MagicMock(), normalized=MagicMock()
    )
    kw = _sector_kwargs()
    kw["cascade_detector"].detect.return_value = _make_cascade_candidate(
        status=CascadeStatus.CONFIRMED, confirmed=True
    )
    kw["modeling"].fit.return_value = MagicMock()
    kw["quality_pipeline"].evaluate.return_value = _make_quality_result()
    pipe._viz.generate.side_effect = RuntimeError("viz fail")
    r = pipe._process_sector(lc_data=_make_lc_data(), **kw)
    assert r.success is True
    assert r.viz is None


def test_process_sector_no_viz(pipe):
    pipe._viz = None
    pipe._preprocessing.run.return_value = SimpleNamespace(
        detrended=MagicMock(), normalized=MagicMock()
    )
    kw = _sector_kwargs()
    kw["cascade_detector"].detect.return_value = _make_cascade_candidate(
        status=CascadeStatus.BLS_FAILED, confirmed=False
    )
    r = pipe._process_sector(lc_data=_make_lc_data(), **kw)
    assert r.success is True
    assert r.viz is None


# ═══════════════════════════════════════════════════════
# run_batch
# ═══════════════════════════════════════════════════════

def test_run_batch_happy(pipe, monkeypatch):
    def fake_run_target(target, sectors=None):
        return TESSTargetResult(target_id=str(target), success=True, sectors_processed=1)
    monkeypatch.setattr(pipe, "run_target", fake_run_target)
    results = pipe.run_batch(["TIC 1", "TIC 2"])
    assert len(results) == 2
    assert all(r.success for r in results)


def test_run_batch_exception_path(pipe, monkeypatch):
    calls = {"n": 0}

    def fake_run_target(target, sectors=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return TESSTargetResult(target_id=str(target), success=True)

    monkeypatch.setattr(pipe, "run_target", fake_run_target)
    results = pipe.run_batch(["TIC 1", "TIC 2"])
    assert len(results) == 2
    assert results[0].success is False
    assert "boom" in results[0].error
    assert results[1].success is True


# ═══════════════════════════════════════════════════════
# close
# ═══════════════════════════════════════════════════════

def test_close_own_output_manager(monkeypatch):
    _patch_pipeline_deps(monkeypatch)
    p = TESSPipeline()
    p._owns_output_manager = True
    p.close()
    p._output.close.assert_called()


def test_close_shared_output_manager(monkeypatch):
    _patch_pipeline_deps(monkeypatch)
    p = TESSPipeline()
    p._owns_output_manager = False
    p.close()
    p._output.close.assert_not_called()
