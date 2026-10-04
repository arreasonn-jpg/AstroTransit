"""
BenchmarkPipeline ve BenchmarkMetrics birim testleri.

Strateji
--------
TESSPipeline, load_verified_targets ve evaluate_benchmark_results
module-level monkeypatch ile mock'lanir. Gerekli dosyalar tmp_path
uzerinde uretilir.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from astrotransit.pipelines import benchmark_pipeline as bp_module
from astrotransit.pipelines.benchmark_pipeline import (
    BenchmarkMetrics,
    BenchmarkPipeline,
    BenchmarkResult,
)

# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_settings() -> MagicMock:
    s = MagicMock()
    s.benchmark.confirmed_targets_file = ""
    s.benchmark.false_positives_file = ""
    s.benchmark.quiet_stars_file = ""
    s.benchmark.verified_targets_file = "benchmarks/verified.json"
    s.benchmark.period_tolerance_fraction = 0.02
    s.benchmark.radius_tolerance_fraction = 0.10
    return s


@pytest.fixture
def mock_tess_pipeline(monkeypatch) -> MagicMock:
    p = MagicMock()
    p.run_target.return_value = MagicMock(candidates_confirmed=1)

    def fake_ctor(**kwargs):
        return p

    monkeypatch.setattr(bp_module, "TESSPipeline", fake_ctor)
    return p


@pytest.fixture
def pipeline(mock_settings, mock_tess_pipeline, monkeypatch) -> BenchmarkPipeline:
    monkeypatch.setattr(bp_module, "load_verified_targets", lambda p: [])
    return BenchmarkPipeline(settings=mock_settings)


# ─────────────────────────────────────────────────────────────
# BenchmarkMetrics
# ─────────────────────────────────────────────────────────────

def test_metrics_defaults() -> None:
    m = BenchmarkMetrics()
    assert m.true_positives == 0
    assert m.precision is None
    assert m.recall is None
    assert m.f1_score is None


def test_metrics_compute_perfect() -> None:
    """TP=10, FP=0, FN=0 -> precision=1, recall=1, f1=1.

    Not: false_alarm_rate = fp/(fp+tn); tn de 0 ise (fp+tn)=0 olur ve
    None doner. Bu dogru davranis: hic negatif ornek yoksa false alarm
    orani tanimsizdir.
    """
    m = BenchmarkMetrics(true_positives=10, false_positives=0, false_negatives=0)
    m.compute()
    assert m.precision == 1.0
    assert m.recall == 1.0
    assert m.f1_score == 1.0
    assert m.recovery_rate == 1.0
    # tn=0 -> false_alarm_rate tanimsiz
    assert m.false_alarm_rate is None


def test_metrics_compute_no_positive() -> None:
    """TP=0 ve FP=0 -> precision=None."""
    m = BenchmarkMetrics(true_positives=0, false_positives=0, false_negatives=5)
    m.compute()
    assert m.precision is None
    assert m.recall == 0.0
    assert m.f1_score is None
    assert m.recovery_rate == 0.0


def test_metrics_compute_mixed() -> None:
    """TP=8, FP=2, FN=2, TN=10 -> precision=0.8, recall=0.8."""
    m = BenchmarkMetrics(
        true_positives=8, false_positives=2,
        false_negatives=2, true_negatives=10,
    )
    m.compute()
    assert m.precision == pytest.approx(0.8)
    assert m.recall == pytest.approx(0.8)
    assert m.f1_score == pytest.approx(0.8)
    assert m.false_alarm_rate == pytest.approx(2/12)


def test_metrics_compute_all_zero() -> None:
    m = BenchmarkMetrics()
    m.compute()
    assert m.precision is None
    assert m.recall is None
    assert m.f1_score is None
    assert m.recovery_rate is None
    assert m.false_alarm_rate is None


def test_metrics_to_dict() -> None:
    m = BenchmarkMetrics(
        n_confirmed_targets=10, n_false_positive_targets=5, n_quiet_targets=3,
        true_positives=8, false_positives=2, false_negatives=2, true_negatives=5,
    )
    m.compute()
    d = m.to_dict()
    assert d["n_confirmed_targets"] == 10
    assert d["precision"] == pytest.approx(0.8)
    assert d["recall"] == pytest.approx(0.8)


def test_metrics_to_dict_none_rounding() -> None:
    m = BenchmarkMetrics()
    m.compute()
    d = m.to_dict()
    assert d["precision"] is None


def test_metrics_report_contains_summary() -> None:
    m = BenchmarkMetrics(
        n_confirmed_targets=10, n_false_positive_targets=5, n_quiet_targets=3,
        true_positives=8, false_positives=2, false_negatives=2, true_negatives=5,
    )
    m.compute()
    report = m.report()
    assert "AstroTransit Benchmark Raporu" in report
    assert "True Positive" in report
    assert "Recall" in report
    assert "Precision" in report


def test_metrics_report_na_for_none() -> None:
    m = BenchmarkMetrics()
    m.compute()
    report = m.report()
    assert "NA" in report


# ─────────────────────────────────────────────────────────────
# BenchmarkResult
# ─────────────────────────────────────────────────────────────

def test_result_defaults() -> None:
    r = BenchmarkResult()
    assert r.metrics is not None
    assert r.confirmed_results == []
    assert r.fp_results == []
    assert r.quiet_results == []
    assert r.performance_report is None


def test_result_to_dict_without_perf_report() -> None:
    r = BenchmarkResult()
    d = r.to_dict()
    assert "metrics" in d
    assert d["performance_report"] is None


def test_result_to_dict_with_perf_report() -> None:
    r = BenchmarkResult()
    fake_report = MagicMock()
    fake_report.to_dict.return_value = {"foo": "bar"}
    r.performance_report = fake_report
    d = r.to_dict()
    assert d["performance_report"] == {"foo": "bar"}


# ─────────────────────────────────────────────────────────────
# __init__
# ─────────────────────────────────────────────────────────────

def test_pipeline_init(mock_settings, mock_tess_pipeline, monkeypatch) -> None:
    monkeypatch.setattr(bp_module, "load_verified_targets", lambda p: [])
    p = BenchmarkPipeline(settings=mock_settings)
    assert p.settings is mock_settings
    assert p._pipeline is not None


def test_pipeline_init_default_settings(mock_tess_pipeline, monkeypatch) -> None:
    mock_get = MagicMock()
    mock_get.return_value = MagicMock()
    monkeypatch.setattr(bp_module, "get_settings", mock_get)
    monkeypatch.setattr(bp_module, "load_verified_targets", lambda p: [])
    p = BenchmarkPipeline()
    assert p.settings is not None


# ─────────────────────────────────────────────────────────────
# load_verified_target_specs
# ─────────────────────────────────────────────────────────────

def test_load_verified_specs_success(pipeline, monkeypatch) -> None:
    fake_specs = [MagicMock(target_id="TIC 1"), MagicMock(target_id="TIC 2")]
    monkeypatch.setattr(bp_module, "load_verified_targets", lambda p: fake_specs)
    specs = pipeline.load_verified_target_specs()
    assert len(specs) == 2


def test_load_verified_specs_exception(pipeline, monkeypatch) -> None:
    def explode(p):
        raise ValueError("bad file")
    monkeypatch.setattr(bp_module, "load_verified_targets", explode)
    specs = pipeline.load_verified_target_specs()
    assert specs == []


# ─────────────────────────────────────────────────────────────
# _load_target_list
# ─────────────────────────────────────────────────────────────

def test_load_target_list_none() -> None:
    assert BenchmarkPipeline._load_target_list(None) == []


def test_load_target_list_missing_file(tmp_path: Path) -> None:
    result = BenchmarkPipeline._load_target_list(tmp_path / "missing.json")
    assert result == []


def test_load_target_list_json_list(tmp_path: Path) -> None:
    f = tmp_path / "targets.json"
    f.write_text(json.dumps([123456789, 987654321]))
    result = BenchmarkPipeline._load_target_list(f)
    assert len(result) == 2


def test_load_target_list_json_dict_with_targets(tmp_path: Path) -> None:
    f = tmp_path / "targets.json"
    f.write_text(json.dumps({"targets": [{"tic_id": 123456789}]}))
    result = BenchmarkPipeline._load_target_list(f)
    assert len(result) == 1


def test_load_target_list_json_dict_with_source_id(tmp_path: Path) -> None:
    f = tmp_path / "targets.json"
    f.write_text(json.dumps({"targets": [{"source_id": 111}]}))
    result = BenchmarkPipeline._load_target_list(f)
    assert len(result) == 1


def test_load_target_list_json_invalid_structure(tmp_path: Path) -> None:
    f = tmp_path / "targets.json"
    f.write_text(json.dumps({"targets": "not a list"}))
    result = BenchmarkPipeline._load_target_list(f)
    assert result == []


def test_load_target_list_csv(tmp_path: Path) -> None:
    f = tmp_path / "targets.csv"
    f.write_text("tic_id,foo\n123456789,a\n987654321,b\n")
    result = BenchmarkPipeline._load_target_list(f)
    assert len(result) == 2


def test_load_target_list_csv_source_id(tmp_path: Path) -> None:
    f = tmp_path / "targets.csv"
    f.write_text("source_id,foo\n111,a\n222,b\n")
    result = BenchmarkPipeline._load_target_list(f)
    assert len(result) == 2


def test_load_target_list_csv_first_column(tmp_path: Path) -> None:
    f = tmp_path / "targets.csv"
    f.write_text("id,x\n100,a\n")
    result = BenchmarkPipeline._load_target_list(f)
    assert len(result) == 1


def test_load_target_list_unsupported_format(tmp_path: Path) -> None:
    f = tmp_path / "targets.txt"
    f.write_text("hello")
    result = BenchmarkPipeline._load_target_list(f)
    assert result == []


def test_load_target_list_invalid_json(tmp_path: Path) -> None:
    f = tmp_path / "targets.json"
    f.write_text("{not valid json")
    result = BenchmarkPipeline._load_target_list(f)
    assert result == []


# ─────────────────────────────────────────────────────────────
# load_benchmark_targets
# ─────────────────────────────────────────────────────────────

def test_load_benchmark_targets_uses_settings(pipeline, monkeypatch) -> None:
    """confirmed_path verilmezse settings'ten okur."""
    pipeline.settings.benchmark.confirmed_targets_file = ""
    confirmed, _fp, _quiet = pipeline.load_benchmark_targets()
    # Bos string -> missing file -> empty
    assert confirmed == []


def test_load_benchmark_targets_with_paths(tmp_path: Path, mock_settings, mock_tess_pipeline, monkeypatch) -> None:
    monkeypatch.setattr(bp_module, "load_verified_targets", lambda p: [])
    p = BenchmarkPipeline(settings=mock_settings)

    cfile = tmp_path / "conf.json"
    cfile.write_text(json.dumps([100, 200]))
    fpfile = tmp_path / "fp.json"
    fpfile.write_text(json.dumps([300]))
    qfile = tmp_path / "q.json"
    qfile.write_text(json.dumps([400, 500]))

    confirmed, fp, quiet = p.load_benchmark_targets(
        confirmed_path=cfile, fp_path=fpfile, quiet_path=qfile,
    )
    assert len(confirmed) == 2
    assert len(fp) == 1
    assert len(quiet) == 2


# ─────────────────────────────────────────────────────────────
# run()
# ─────────────────────────────────────────────────────────────

def test_run_empty_targets(pipeline, monkeypatch) -> None:
    monkeypatch.setattr(bp_module, "load_verified_targets", lambda p: [])
    # Tum listeler bos ve settings default'lari da bos
    pipeline.settings.benchmark.confirmed_targets_file = ""
    pipeline.settings.benchmark.false_positives_file = ""
    pipeline.settings.benchmark.quiet_stars_file = ""

    result = pipeline.run(confirmed_targets=[], fp_targets=[], quiet_targets=[])
    assert isinstance(result, BenchmarkResult)
    assert result.metrics.n_confirmed_targets == 0


def test_run_with_confirmed_targets(pipeline, monkeypatch) -> None:
    monkeypatch.setattr(bp_module, "load_verified_targets", lambda p: [])
    pipeline._pipeline.run_target.return_value = MagicMock(candidates_confirmed=1)

    result = pipeline.run(confirmed_targets=["TIC 123456789"])
    assert result.metrics.true_positives == 1
    assert result.metrics.n_confirmed_targets == 1


def test_run_confirmed_not_found(pipeline, monkeypatch) -> None:
    monkeypatch.setattr(bp_module, "load_verified_targets", lambda p: [])
    pipeline._pipeline.run_target.return_value = MagicMock(candidates_confirmed=0)

    result = pipeline.run(confirmed_targets=["TIC 123456789"])
    assert result.metrics.false_negatives == 1
    assert result.metrics.true_positives == 0


def test_run_confirmed_exception(pipeline, monkeypatch) -> None:
    monkeypatch.setattr(bp_module, "load_verified_targets", lambda p: [])
    pipeline._pipeline.run_target.side_effect = RuntimeError("boom")

    result = pipeline.run(confirmed_targets=["TIC 123456789"])
    assert result.metrics.false_negatives == 1


def test_run_fp_targets(pipeline, monkeypatch) -> None:
    monkeypatch.setattr(bp_module, "load_verified_targets", lambda p: [])
    pipeline._pipeline.run_target.return_value = MagicMock(candidates_confirmed=1)

    result = pipeline.run(fp_targets=["TIC 123456789"])
    assert result.metrics.false_positives == 1
    assert result.metrics.n_false_positive_targets == 1


def test_run_fp_not_triggered(pipeline, monkeypatch) -> None:
    monkeypatch.setattr(bp_module, "load_verified_targets", lambda p: [])
    pipeline._pipeline.run_target.return_value = MagicMock(candidates_confirmed=0)

    result = pipeline.run(fp_targets=["TIC 123456789"])
    assert result.metrics.true_negatives == 1
    assert result.metrics.false_positives == 0


def test_run_fp_exception(pipeline, monkeypatch) -> None:
    monkeypatch.setattr(bp_module, "load_verified_targets", lambda p: [])
    pipeline._pipeline.run_target.side_effect = RuntimeError("boom")

    result = pipeline.run(fp_targets=["TIC 123456789"])
    assert result.metrics.n_evaluation_errors == 1
    assert result.metrics.n_negative_not_evaluated == 1


def test_run_quiet_targets(pipeline, monkeypatch) -> None:
    monkeypatch.setattr(bp_module, "load_verified_targets", lambda p: [])
    pipeline._pipeline.run_target.return_value = MagicMock(candidates_confirmed=0)

    result = pipeline.run(quiet_targets=["TIC 123456789"])
    assert result.metrics.true_negatives == 1
    assert result.metrics.n_quiet_targets == 1


def test_run_quiet_false_alarm(pipeline, monkeypatch) -> None:
    monkeypatch.setattr(bp_module, "load_verified_targets", lambda p: [])
    pipeline._pipeline.run_target.return_value = MagicMock(candidates_confirmed=1)

    result = pipeline.run(quiet_targets=["TIC 123456789"])
    assert result.metrics.false_positives == 1


def test_run_max_per_category(pipeline, monkeypatch) -> None:
    monkeypatch.setattr(bp_module, "load_verified_targets", lambda p: [])
    pipeline._pipeline.run_target.return_value = MagicMock(candidates_confirmed=1)

    result = pipeline.run(
        confirmed_targets=["TIC 1", "TIC 2", "TIC 3", "TIC 4"],
        max_per_category=2,
    )
    assert result.metrics.n_confirmed_targets == 2


def test_run_max_per_category_negative(pipeline, monkeypatch) -> None:
    monkeypatch.setattr(bp_module, "load_verified_targets", lambda p: [])
    with pytest.raises(ValueError, match="max_per_category"):
        pipeline.run(confirmed_targets=["TIC 1"], max_per_category=-1)


def test_run_closes_pipeline(pipeline, monkeypatch) -> None:
    monkeypatch.setattr(bp_module, "load_verified_targets", lambda p: [])
    pipeline.run(confirmed_targets=[])
    pipeline._pipeline.close.assert_called_once()


def test_run_with_verified_specs_generates_performance_report(pipeline, monkeypatch) -> None:
    fake_spec = MagicMock()
    fake_spec.target_id = "TIC 123456789"
    monkeypatch.setattr(bp_module, "load_verified_targets", lambda p: [fake_spec])

    fake_report = MagicMock()
    fake_report.summary.return_value = "summary"
    monkeypatch.setattr(
        bp_module, "evaluate_benchmark_results",
        lambda *a, **kw: fake_report,
    )

    pipeline._pipeline.run_target.return_value = MagicMock(candidates_confirmed=1)
    result = pipeline.run(confirmed_targets=["TIC 123456789"])
    assert result.performance_report is fake_report


def test_run_without_verified_specs_no_report(pipeline, monkeypatch) -> None:
    monkeypatch.setattr(bp_module, "load_verified_targets", lambda p: [])
    pipeline._pipeline.run_target.return_value = MagicMock(candidates_confirmed=1)
    result = pipeline.run(confirmed_targets=["TIC 123456789"])
    assert result.performance_report is None
