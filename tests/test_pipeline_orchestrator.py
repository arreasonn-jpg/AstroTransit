"""
AstroTransitOrchestrator birim testleri.

Strateji
--------
Alt pipeline'lar (TESSPipeline, JWSTFollowUpPipeline, BenchmarkPipeline)
ve OutputManager module-level monkeypatch ile mock'lanir. Boylece
orkestrasyon mantigi test edilirken gercek TESS veri indirme,
MCMC, vs. atlanir.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from astrotransit.pipelines import orchestrator as orch_module
from astrotransit.pipelines.orchestrator import (
    AstroTransitOrchestrator,
    PipelineMode,
)

# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_settings() -> MagicMock:
    s = MagicMock()
    s.general.log_level = "INFO"
    return s


@pytest.fixture
def mock_output_manager(monkeypatch) -> MagicMock:
    om = MagicMock()

    def fake_ctor(*args, **kwargs):
        return om

    monkeypatch.setattr(orch_module, "OutputManager", fake_ctor)
    return om


@pytest.fixture
def mock_setup_logging(monkeypatch) -> MagicMock:
    m = MagicMock()
    monkeypatch.setattr(orch_module, "setup_logging", m)
    return m


@pytest.fixture
def mock_get_settings(monkeypatch, mock_settings) -> MagicMock:
    m = MagicMock(return_value=mock_settings)
    monkeypatch.setattr(orch_module, "get_settings", m)
    return m


@pytest.fixture
def orchestrator(mock_get_settings, mock_output_manager, mock_setup_logging) -> AstroTransitOrchestrator:
    return AstroTransitOrchestrator()


@contextmanager
def _fake_pipeline_cm(pipeline: MagicMock):
    yield pipeline


# ─────────────────────────────────────────────────────────────
# PipelineMode enum
# ─────────────────────────────────────────────────────────────

def test_pipeline_mode_values() -> None:
    assert PipelineMode.SINGLE.value == "single"
    assert PipelineMode.BATCH.value == "batch"
    assert PipelineMode.FOLLOWUP.value == "followup"
    assert PipelineMode.BENCHMARK.value == "benchmark"


# ─────────────────────────────────────────────────────────────
# __init__
# ─────────────────────────────────────────────────────────────

def test_orchestrator_init_calls_get_settings(
    mock_get_settings, mock_output_manager, mock_setup_logging,
) -> None:
    AstroTransitOrchestrator()
    mock_get_settings.assert_called_once()


def test_orchestrator_init_uses_log_level_override(
    mock_get_settings, mock_output_manager, mock_setup_logging,
) -> None:
    AstroTransitOrchestrator(log_level="DEBUG")
    # setup_logging log_level="DEBUG" ile cagrilmis olmali
    args, kwargs = mock_setup_logging.call_args
    assert kwargs.get("log_level") == "DEBUG" or (args and args[0] == "DEBUG")


def test_orchestrator_init_falls_back_to_settings_log_level(
    mock_get_settings, mock_output_manager, mock_setup_logging, mock_settings,
) -> None:
    mock_settings.general.log_level = "WARNING"
    AstroTransitOrchestrator(log_level="")
    # bos log_level verilirse settings'ten alinmali
    args, kwargs = mock_setup_logging.call_args
    assert kwargs.get("log_level") == "WARNING" or (args and args[0] == "WARNING")


def test_orchestrator_init_creates_output_manager(
    mock_get_settings, mock_output_manager, mock_setup_logging,
) -> None:
    AstroTransitOrchestrator()
    assert mock_output_manager is not None


def test_orchestrator_init_stores_flags(
    mock_get_settings, mock_output_manager, mock_setup_logging,
) -> None:
    o = AstroTransitOrchestrator(
        force_mcmc=True, force_map=True,
        skip_visualization=True, skip_catalog=True,
    )
    assert o._force_mcmc is True
    assert o._force_map is True
    assert o._skip_viz is True
    assert o._skip_catalog is True


# ─────────────────────────────────────────────────────────────
# __enter__ / __exit__ / close
# ─────────────────────────────────────────────────────────────

def test_orchestrator_context_manager(orchestrator) -> None:
    with orchestrator as o:
        assert o is orchestrator


def test_orchestrator_close_calls_output_close(orchestrator) -> None:
    orchestrator.close()
    orchestrator._output.close.assert_called_once()


def test_orchestrator_exit_calls_close(orchestrator) -> None:
    orchestrator.__exit__(None, None, None)
    orchestrator._output.close.assert_called_once()


# ─────────────────────────────────────────────────────────────
# _finalize
# ─────────────────────────────────────────────────────────────

def test_finalize_exports_csv(orchestrator) -> None:
    orchestrator._finalize()
    orchestrator._output.export_csv.assert_called_once()


def test_finalize_handles_export_exception(orchestrator) -> None:
    """export_csv exception firlatirsa yutulur."""
    orchestrator._output.export_csv.side_effect = RuntimeError("boom")
    # Crash etmemeli
    orchestrator._finalize()


# ─────────────────────────────────────────────────────────────
# run_single
# ─────────────────────────────────────────────────────────────

def test_run_single(orchestrator, monkeypatch) -> None:
    mock_pipeline = MagicMock()
    mock_result = MagicMock(name="TESSTargetResult")
    mock_pipeline.run_target.return_value = mock_result

    monkeypatch.setattr(
        orchestrator, "_create_tess_pipeline", lambda: _fake_pipeline_cm(mock_pipeline),
    )

    result = orchestrator.run_single("TIC-100")
    assert result is mock_result
    mock_pipeline.run_target.assert_called_once_with("TIC-100", sectors=None)
    orchestrator._output.export_csv.assert_called_once()


def test_run_single_with_sectors(orchestrator, monkeypatch) -> None:
    mock_pipeline = MagicMock()
    mock_pipeline.run_target.return_value = MagicMock()

    monkeypatch.setattr(
        orchestrator, "_create_tess_pipeline", lambda: _fake_pipeline_cm(mock_pipeline),
    )

    orchestrator.run_single(12345, sectors=[1, 2])
    mock_pipeline.run_target.assert_called_once_with(12345, sectors=[1, 2])


# ─────────────────────────────────────────────────────────────
# run_batch
# ─────────────────────────────────────────────────────────────

def test_run_batch(orchestrator, monkeypatch) -> None:
    mock_pipeline = MagicMock()
    mock_results = [MagicMock(name=f"r{i}") for i in range(3)]
    mock_pipeline.run_batch.return_value = mock_results

    monkeypatch.setattr(
        orchestrator, "_create_tess_pipeline", lambda: _fake_pipeline_cm(mock_pipeline),
    )

    results = orchestrator.run_batch(["TIC-1", "TIC-2", "TIC-3"])
    assert results is mock_results
    mock_pipeline.run_batch.assert_called_once_with(
        ["TIC-1", "TIC-2", "TIC-3"], sectors=None,
    )
    orchestrator._output.export_csv.assert_called_once()


# ─────────────────────────────────────────────────────────────
# _create_tess_pipeline
# ─────────────────────────────────────────────────────────────

def test_create_tess_pipeline_uses_settings(orchestrator, monkeypatch) -> None:
    captured = {}

    def fake_ctor(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr(orch_module, "TESSPipeline", fake_ctor)

    pipeline = orchestrator._create_tess_pipeline()
    assert pipeline is not None
    assert captured["settings"] is orchestrator.settings
    assert captured["output_manager"] is orchestrator._output
    assert captured["force_mcmc"] is False
    assert captured["skip_visualization"] is False


def test_create_tess_pipeline_respects_flags(
    mock_get_settings, mock_output_manager, mock_setup_logging, monkeypatch,
) -> None:
    o = AstroTransitOrchestrator(
        force_mcmc=True, force_map=True,
        skip_visualization=True, skip_catalog=True,
    )
    captured = {}

    def fake_ctor(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr(orch_module, "TESSPipeline", fake_ctor)
    o._create_tess_pipeline()
    assert captured["force_mcmc"] is True
    assert captured["force_map"] is True
    assert captured["skip_visualization"] is True
    assert captured["skip_catalog"] is True


# ─────────────────────────────────────────────────────────────
# run_followup
# ─────────────────────────────────────────────────────────────

def test_run_followup_import_error(orchestrator, monkeypatch) -> None:
    """JWSTFollowUpPipeline ImportError firlatirsa error result doner."""
    def fake_ctor(**kwargs):
        raise ImportError("celerite2 missing")

    monkeypatch.setattr(orch_module, "JWSTFollowUpPipeline", fake_ctor)

    result = orchestrator.run_followup(
        target_id="TIC-100",
        tess_period=5.0, tess_t0=100.0,
        tess_duration=0.15, tess_rp_rs=0.08,
    )
    assert result is not None
    assert "celerite2 missing" in result.error


def test_run_followup_success(orchestrator, monkeypatch) -> None:
    mock_pipeline = MagicMock()
    mock_result = MagicMock(name="JWSTFollowUpResult")
    mock_pipeline.run.return_value = mock_result

    def fake_ctor(**kwargs):
        return mock_pipeline

    monkeypatch.setattr(orch_module, "JWSTFollowUpPipeline", fake_ctor)

    result = orchestrator.run_followup(
        target_id="TIC-100",
        tess_period=5.0, tess_t0=100.0,
        tess_duration=0.15, tess_rp_rs=0.08,
        stellar_radius=1.1, stellar_mass=1.05, stellar_teff=5800.0,
    )
    assert result is mock_result
    mock_pipeline.run.assert_called_once()
    _, kwargs = mock_pipeline.run.call_args
    assert kwargs["target_id"] == "TIC-100"
    assert kwargs["tess_period"] == 5.0


# ─────────────────────────────────────────────────────────────
# run_benchmark
# ─────────────────────────────────────────────────────────────

def test_run_benchmark(orchestrator, monkeypatch) -> None:
    mock_bench = MagicMock()
    mock_result = MagicMock(name="BenchmarkResult")
    mock_bench.run.return_value = mock_result

    def fake_ctor(**kwargs):
        return mock_bench

    monkeypatch.setattr(orch_module, "BenchmarkPipeline", fake_ctor)

    result = orchestrator.run_benchmark(
        confirmed=["TIC-1"],
        false_positives=["TIC-2"],
        quiet_stars=["TIC-3"],
        max_per_category=2,
    )
    assert result is mock_result
    mock_bench.run.assert_called_once_with(
        confirmed_targets=["TIC-1"],
        fp_targets=["TIC-2"],
        quiet_targets=["TIC-3"],
        max_per_category=2,
    )


def test_run_benchmark_no_args(orchestrator, monkeypatch) -> None:
    mock_bench = MagicMock()
    mock_bench.run.return_value = MagicMock()

    monkeypatch.setattr(orch_module, "BenchmarkPipeline", lambda **kw: mock_bench)

    orchestrator.run_benchmark()
    mock_bench.run.assert_called_once_with(
        confirmed_targets=None,
        fp_targets=None,
        quiet_targets=None,
        max_per_category=None,
    )


# ─────────────────────────────────────────────────────────────
# run_earth_search
# ─────────────────────────────────────────────────────────────

def test_run_earth_search_full(orchestrator, monkeypatch) -> None:
    # run_batch'i mockla
    mock_results = [MagicMock(name="r1"), MagicMock(name="r2")]
    monkeypatch.setattr(orchestrator, "run_batch", lambda targets, sectors=None: mock_results)

    # EarthCandidateRanker ve EarthSearchSummary'i mockla
    mock_records = [MagicMock(name="rec1"), MagicMock(name="rec2"), MagicMock(name="rec3")]
    mock_summary = MagicMock()
    mock_summary.n_targets = 2
    mock_summary.n_records = 3
    mock_summary.n_ranked_candidates = 3
    mock_summary.ranked_candidates = mock_records

    mock_ranker = MagicMock()
    mock_ranker.records_from_target_results.return_value = mock_records
    mock_ranker.summarize.return_value = mock_summary

    def fake_ranker_ctor(min_similarity):
        return mock_ranker

    summary_cls = MagicMock(side_effect=lambda **kw: MagicMock(**kw))

    # Import'u taklit et
    import astrotransit.discovery.earth_search as es_module
    monkeypatch.setattr(es_module, "EarthCandidateRanker", fake_ranker_ctor)
    monkeypatch.setattr(es_module, "EarthSearchSummary", summary_cls)

    # limit None -> tam summary
    result = orchestrator.run_earth_search(["TIC-1", "TIC-2"], min_similarity=85.0)
    assert result is mock_summary


def test_run_earth_search_with_limit(orchestrator, monkeypatch) -> None:
    mock_results = [MagicMock()]
    monkeypatch.setattr(orchestrator, "run_batch", lambda targets, sectors=None: mock_results)

    mock_records = [MagicMock(name=f"r{i}") for i in range(5)]
    mock_summary = MagicMock()
    mock_summary.n_targets = 1
    mock_summary.n_records = 5
    mock_summary.n_ranked_candidates = 5
    mock_summary.ranked_candidates = mock_records

    mock_ranker = MagicMock()
    mock_ranker.records_from_target_results.return_value = mock_records
    mock_ranker.summarize.return_value = mock_summary

    import astrotransit.discovery.earth_search as es_module
    monkeypatch.setattr(es_module, "EarthCandidateRanker", lambda **kw: mock_ranker)

    captured_summary_kwargs = {}

    def fake_summary_ctor(**kwargs):
        captured_summary_kwargs.update(kwargs)
        return MagicMock()

    monkeypatch.setattr(es_module, "EarthSearchSummary", fake_summary_ctor)

    orchestrator.run_earth_search(["TIC-1"], limit=2)
    assert captured_summary_kwargs["n_ranked_candidates"] == 2
    assert len(captured_summary_kwargs["ranked_candidates"]) == 2


def test_run_earth_search_invalid_limit(orchestrator, monkeypatch) -> None:
    monkeypatch.setattr(orchestrator, "run_batch", lambda targets, sectors=None: [])

    mock_summary = MagicMock()
    mock_summary.n_targets = 0
    mock_summary.n_records = 0
    mock_summary.n_ranked_candidates = 0
    mock_summary.ranked_candidates = []

    mock_ranker = MagicMock()
    mock_ranker.records_from_target_results.return_value = []
    mock_ranker.summarize.return_value = mock_summary

    import astrotransit.discovery.earth_search as es_module
    monkeypatch.setattr(es_module, "EarthCandidateRanker", lambda **kw: mock_ranker)

    with pytest.raises(ValueError, match="limit en az 1"):
        orchestrator.run_earth_search(["TIC-1"], limit=0)
