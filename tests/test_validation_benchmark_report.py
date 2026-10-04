"""astrotransit/validation/benchmark_report.py için kapsamlı testler."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from astrotransit.validation.benchmark_report import (
    BenchmarkPerformanceReport,
    BenchmarkTargetMeasurement,
    VerifiedTarget,
    _best_observation,
    _confirmed_observations,
    _first_positive,
    _mean,
    _median,
    _positive_float,
    _ratio,
    _sector_consistency,
    _value,
    evaluate_benchmark_results,
    load_verified_targets,
    normalize_target_id,
)

# ═══════════════════════════════════════════════════════
# normalize_target_id
# ═══════════════════════════════════════════════════════

def test_normalize_basic():
    assert normalize_target_id("TIC 123") == "TIC 123"
    assert normalize_target_id("tic 123") == "TIC 123"
    assert normalize_target_id("123") == "TIC 123"
    assert normalize_target_id(123) == "TIC 123"
    assert normalize_target_id(123.0) == "TIC 123"


def test_normalize_empty_and_bad():
    assert normalize_target_id(None) == ""
    assert normalize_target_id("") == ""
    assert normalize_target_id("not-a-number") == "not-a-number"


# ═══════════════════════════════════════════════════════
# VerifiedTarget
# ═══════════════════════════════════════════════════════

def test_verified_target_from_mapping():
    row = {
        "tic_id": "TIC 123", "name": "Test",
        "period": 3.5, "rp_rearth": 1.2, "difficulty": "EASY",
        "sector": 14, "available_sectors": [1, 2],
    }
    v = VerifiedTarget.from_mapping(row)
    assert v.tic_id == "TIC 123"
    assert v.name == "Test"
    assert v.expected_period_days == 3.5
    assert v.expected_radius_rearth == 1.2
    assert v.difficulty == "easy"
    assert v.sector == 14
    assert v.available_sectors == (1, 2)
    assert v.target_id == "TIC 123"


def test_verified_target_alternative_fields():
    row = {
        "source_id": "TIC 456", "target_id": "T456",
        "expected_period_days": 5.0, "expected_radius_rearth": 2.0,
    }
    v = VerifiedTarget.from_mapping(row)
    assert v.tic_id == "TIC 456"
    assert v.name == "T456"
    assert v.expected_period_days == 5.0


def test_verified_target_no_radius():
    row = {"tic_id": "TIC 1", "period": 3.5}
    v = VerifiedTarget.from_mapping(row)
    assert v.expected_radius_rearth is None
    assert v.difficulty == "unknown"


def test_verified_target_invalid_period():
    with pytest.raises(ValueError, match="period"):
        VerifiedTarget.from_mapping({"tic_id": "T", "period": -1.0})


def test_verified_target_invalid_radius():
    with pytest.raises(ValueError, match="radius"):
        VerifiedTarget.from_mapping({"tic_id": "T", "period": 3.5, "rp_rearth": -1.0})


def test_verified_target_to_dict():
    v = VerifiedTarget.from_mapping({
        "tic_id": "TIC 1", "name": "X", "period": 3.5,
        "rp_rearth": 1.0, "sector": 1, "available_sectors": [1],
    })
    d = v.to_dict()
    assert d["tic_id"] == "TIC 1"
    assert d["target_id"] == "TIC 1"
    assert d["expected_period_days"] == 3.5
    assert d["available_sectors"] == [1]


# ═══════════════════════════════════════════════════════
# load_verified_targets
# ═══════════════════════════════════════════════════════

def test_load_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_verified_targets(tmp_path / "missing.json")


def test_load_list_payload(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps([
        {"tic_id": "TIC 1", "name": "a", "period": 3.5},
    ]))
    targets = load_verified_targets(p)
    assert len(targets) == 1


def test_load_dict_payload(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"targets": [
        {"tic_id": "TIC 1", "name": "a", "period": 3.5},
    ]}))
    targets = load_verified_targets(p)
    assert len(targets) == 1


def test_load_invalid_payload(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"targets": "not a list"}))
    with pytest.raises(ValueError, match="liste"):
        load_verified_targets(p)


# ═══════════════════════════════════════════════════════
# BenchmarkTargetMeasurement
# ═══════════════════════════════════════════════════════

def _make_measurement(**kw):
    base = dict(
        target_id="TIC 1", name="X", difficulty="easy",
        expected_period_days=3.5, recovered_period_days=3.51,
        expected_radius_rearth=1.0, recovered_radius_rearth=1.05,
        detected=True, period_recovered=True, radius_recovered=True,
        correct=True, period_error_days=0.01, period_error_fraction=0.003,
        radius_error_rearth=0.05, radius_error_fraction=0.05,
        sector_consistent=True, n_sectors_evaluated=2,
        notes=("ok",),
    )
    base.update(kw)
    return BenchmarkTargetMeasurement(**base)


def test_measurement_to_dict():
    d = _make_measurement().to_dict()
    assert d["target_id"] == "TIC 1"
    assert d["detected"] is True
    assert d["period_error_days"] == 0.01
    assert d["notes"] == ["ok"]


# ═══════════════════════════════════════════════════════
# BenchmarkPerformanceReport
# ═══════════════════════════════════════════════════════

def _make_report(**kw):
    base = dict(
        pipeline_version="1.0", generated_at_utc="2026-01-01T00:00:00Z",
        period_tolerance_fraction=0.02, radius_tolerance_fraction=0.2,
        targets=(_make_measurement(),),
        metrics={"n_targets": 1, "detection_recall": 1.0},
        limitations=("test limitation",),
        provenance={"cfg": 1},
    )
    base.update(kw)
    return BenchmarkPerformanceReport(**base)


def test_report_to_dict():
    d = _make_report().to_dict()
    assert d["metadata"]["report_type"] == "known_target_benchmark_performance"
    assert d["metrics"]["n_targets"] == 1
    assert len(d["targets"]) == 1


def test_report_summary():
    s = _make_report().summary()
    assert "Benchmark performance" in s
    assert "targets=1" in s


def test_report_write_json(tmp_path):
    r = _make_report()
    out = r.write_json(tmp_path / "sub" / "report.json")
    assert out.exists()
    payload = json.loads(out.read_text())
    assert payload["metadata"]["report_type"] == "known_target_benchmark_performance"


def test_report_write_csv(tmp_path):
    r = _make_report()
    out = r.write_csv(tmp_path / "report.csv")
    assert out.exists()
    content = out.read_text()
    assert "target_id" in content
    assert "TIC 1" in content


# ═══════════════════════════════════════════════════════
# evaluate_benchmark_results — validation
# ═══════════════════════════════════════════════════════

def _verified(tic="TIC 1", period=3.5, radius=1.0, difficulty="easy"):
    return VerifiedTarget(
        tic_id=tic, name="X", expected_period_days=period,
        expected_radius_rearth=radius, difficulty=difficulty,
    )


def test_evaluate_invalid_period_tolerance():
    with pytest.raises(ValueError, match="period_tolerance"):
        evaluate_benchmark_results([], [], period_tolerance_fraction=0.0)
    with pytest.raises(ValueError, match="period_tolerance"):
        evaluate_benchmark_results([], [], period_tolerance_fraction=1.5)


def test_evaluate_invalid_radius_tolerance():
    with pytest.raises(ValueError, match="radius_tolerance"):
        evaluate_benchmark_results([], [], radius_tolerance_fraction=0.0)


# ═══════════════════════════════════════════════════════
# evaluate_benchmark_results — logic
# ═══════════════════════════════════════════════════════

def _make_pipeline_result(target="TIC 1", confirmed=True, period=3.5, radius=1.0):
    record = SimpleNamespace(period=period, planet_radius_rearth=radius)
    candidate = SimpleNamespace(period=period)
    sector_result = SimpleNamespace(
        candidate_confirmed=confirmed,
        sector=1, record=record, candidate=candidate, fit_result=None,
    )
    return SimpleNamespace(
        target_id=target, candidates_confirmed=1 if confirmed else 0,
        sector_results=[sector_result],
    )


def test_evaluate_empty():
    r = evaluate_benchmark_results([], [])
    assert r.metrics["n_targets"] == 0
    assert r.metrics["detection_recall"] is None


def test_evaluate_no_pipeline_results():
    r = evaluate_benchmark_results([_verified()], [])
    assert r.metrics["n_targets"] == 1
    assert r.metrics["n_detected"] == 0
    m = r.targets[0]
    assert m.detected is False
    assert "no_pipeline_result" in m.notes


def test_evaluate_detected_and_recovered():
    r = evaluate_benchmark_results(
        [_verified()],
        [_make_pipeline_result(period=3.51, radius=1.05)],
    )
    m = r.targets[0]
    assert m.detected is True
    assert m.period_recovered is True
    assert m.radius_recovered is True
    assert m.correct is True


def test_evaluate_detected_period_not_recovered():
    r = evaluate_benchmark_results(
        [_verified()],
        [_make_pipeline_result(period=5.0, radius=1.0)],
    )
    m = r.targets[0]
    assert m.detected is True
    assert m.period_recovered is False
    assert "period_not_recovered" in m.notes


def test_evaluate_radius_not_recovered():
    r = evaluate_benchmark_results(
        [_verified(radius=1.0)],
        [_make_pipeline_result(period=3.5, radius=2.0)],
    )
    m = r.targets[0]
    assert m.radius_recovered is False
    assert "radius_not_recovered" in m.notes


def test_evaluate_no_expected_radius():
    r = evaluate_benchmark_results(
        [_verified(radius=None)],
        [_make_pipeline_result(period=3.5, radius=1.0)],
    )
    m = r.targets[0]
    assert m.radius_recovered is False  # radius=None → False


def test_evaluate_sector_consistency_not_evaluated():
    r = evaluate_benchmark_results(
        [_verified()],
        [_make_pipeline_result()],
    )
    m = r.targets[0]
    assert m.sector_consistent is None
    assert "sector_consistency_not_evaluated" in m.notes


def test_evaluate_pipeline_version_default():
    r = evaluate_benchmark_results([], [])
    assert r.pipeline_version != ""


def test_evaluate_custom_pipeline_version():
    r = evaluate_benchmark_results([], [], pipeline_version="v9")
    assert r.pipeline_version == "v9"


def test_evaluate_with_provenance():
    r = evaluate_benchmark_results([], [], provenance={"key": "val"})
    assert r.provenance == {"key": "val"}


# ═══════════════════════════════════════════════════════
# Helper fonksiyonlar
# ═══════════════════════════════════════════════════════

def test_value_none():
    assert _value(None, "x", 99) == 99


def test_value_mapping():
    assert _value({"a": 1}, "a") == 1


def test_value_object():
    assert _value(SimpleNamespace(a=5), "a") == 5


def test_value_object_missing():
    assert _value(SimpleNamespace(), "x", 42) == 42


def test_positive_float_ok():
    assert _positive_float(3.5) == 3.5
    assert _positive_float("2.0") == 2.0


def test_positive_float_invalid():
    assert _positive_float(None) is None
    assert _positive_float(0) is None
    assert _positive_float(-1) is None
    assert _positive_float("bad") is None
    assert _positive_float(float("nan")) is None


def test_first_positive():
    assert _first_positive(None, -1, 0, 5) == 5
    assert _first_positive(None, 0, -1) is None


def test_ratio():
    assert _ratio(1, 2) == 0.5
    assert _ratio(1, 0) is None


def test_mean():
    assert _mean([1, 2, 3]) == 2.0
    assert _mean([None, None]) is None
    assert _mean([None, 5.0]) == 5.0


def test_median():
    assert _median([1, 2, 3]) == 2.0
    assert _median([]) is None
    assert _median([None, 10.0]) == 10.0


def test_sector_consistency_single():
    assert _sector_consistency([3.5], 0.02) is None


def test_sector_consistency_ok():
    assert _sector_consistency([3.5, 3.51, 3.49], 0.02) is True


def test_sector_consistency_inconsistent():
    assert _sector_consistency([3.5, 5.0], 0.02) is False


def test_best_observation_empty():
    assert _best_observation([], 3.5) is None


def test_best_observation_no_periods():
    obs = [{"period": None, "radius": 1.0}]
    assert _best_observation(obs, 3.5) is obs[0]


def test_best_observation_closest():
    obs = [
        {"period": 3.5, "radius": 1.0},
        {"period": 5.0, "radius": 2.0},
    ]
    best = _best_observation(obs, 3.5)
    assert best["period"] == 3.5


def test_confirmed_observations_empty():
    assert _confirmed_observations(None) == []
    assert _confirmed_observations(SimpleNamespace(sector_results=[])) == []


def test_confirmed_observations_skips_unconfirmed():
    sector_result = SimpleNamespace(candidate_confirmed=False)
    result = SimpleNamespace(sector_results=[sector_result])
    assert _confirmed_observations(result) == []


def test_confirmed_observations_with_data():
    record = SimpleNamespace(period=3.5, planet_radius_rearth=1.0)
    sector_result = SimpleNamespace(
        candidate_confirmed=True, sector=1,
        record=record, candidate=None, fit_result=None,
    )
    result = SimpleNamespace(sector_results=[sector_result])
    obs = _confirmed_observations(result)
    assert len(obs) == 1
    assert obs[0]["period"] == 3.5


# ═══════════════════════════════════════════════════════
# Ek coverage: 287->290 (radius_recovered False branch)
# ═══════════════════════════════════════════════════════

def test_evaluate_detected_but_no_recovered_radius():
    """expected_radius var ama recovered_radius None → False branch."""
    # sector_result içinde record var ama planet_radius_rearth None
    record = SimpleNamespace(period=3.5, planet_radius_rearth=None)
    candidate = SimpleNamespace(period=3.5)
    sector_result = SimpleNamespace(
        candidate_confirmed=True, sector=1,
        record=record, candidate=candidate, fit_result=None,
    )
    result = SimpleNamespace(
        target_id="TIC 1", candidates_confirmed=1,
        sector_results=[sector_result],
    )
    r = evaluate_benchmark_results([_verified(radius=1.0)], [result])
    m = r.targets[0]
    assert m.recovered_radius_rearth is None
    assert m.radius_recovered is False
