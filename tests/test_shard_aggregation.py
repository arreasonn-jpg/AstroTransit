"""Deterministic known-planet benchmark shard aggregation tests."""
from __future__ import annotations

import copy

import pytest

from astrotransit.validation.shard_aggregation import aggregate_benchmark_shards


def _target(target_id: str, *, recovered: bool, consistent: bool | None) -> dict:
    error = 0.01 if recovered else 0.5
    return {
        "target_id": target_id,
        "detected": True,
        "correct": recovered,
        "period_recovered": recovered,
        "radius_recovered": recovered,
        "period_error_days": error,
        "period_error_fraction": error,
        "radius_error_rearth": error,
        "radius_error_fraction": error,
        "sector_consistent": consistent,
    }


def _shard(target: dict, *, generated: str = "2026-01-01T00:00:00Z") -> dict:
    return {
        "metadata": {
            "report_type": "known_target_benchmark_performance",
            "pipeline_version": "0.3.0",
            "generated_at_utc": generated,
            "period_tolerance_fraction": 0.02,
            "radius_tolerance_fraction": 0.2,
        },
        "metrics": {"intentionally": "ignored"},
        "targets": [target],
        "limitations": ["Known-target recovery is not completeness."],
        "provenance": {"git_commit": "a" * 40},
    }


def test_aggregation_recomputes_metrics_from_target_rows() -> None:
    first = _shard(_target("TIC 2", recovered=False, consistent=False))
    second = _shard(
        _target("TIC 1", recovered=True, consistent=True),
        generated="2026-01-02T00:00:00Z",
    )
    report = aggregate_benchmark_shards([first, second])

    assert [row["target_id"] for row in report["targets"]] == ["TIC 1", "TIC 2"]
    assert report["metrics"]["n_targets"] == 2
    assert report["metrics"]["n_detected"] == 2
    assert report["metrics"]["n_correct"] == 1
    assert report["metrics"]["correct_recovery_rate"] == 0.5
    assert report["metrics"]["sector_consistency_rate"] == 0.5
    assert report["metadata"]["n_shards"] == 2
    assert report["metadata"]["generated_at_utc"] == "2026-01-02T00:00:00Z"


def test_explicit_target_order_is_preserved() -> None:
    shards = [
        _shard(_target("TIC 1", recovered=True, consistent=None)),
        _shard(_target("TIC 2", recovered=True, consistent=None)),
    ]
    report = aggregate_benchmark_shards(shards, target_order=["TIC 2", "TIC 1"])
    assert [row["target_id"] for row in report["targets"]] == ["TIC 2", "TIC 1"]


def test_duplicate_target_across_shards_is_rejected() -> None:
    shard = _shard(_target("TIC 1", recovered=True, consistent=True))
    with pytest.raises(ValueError, match="Duplicate target"):
        aggregate_benchmark_shards([shard, copy.deepcopy(shard)])


def test_mismatched_scientific_tolerance_is_rejected() -> None:
    first = _shard(_target("TIC 1", recovered=True, consistent=True))
    second = _shard(_target("TIC 2", recovered=True, consistent=True))
    second["metadata"]["period_tolerance_fraction"] = 0.05
    with pytest.raises(ValueError, match="period_tolerance_fraction"):
        aggregate_benchmark_shards([first, second])


def test_incomplete_target_order_is_rejected() -> None:
    shard = _shard(_target("TIC 1", recovered=True, consistent=True))
    with pytest.raises(ValueError, match="does not match"):
        aggregate_benchmark_shards([shard], target_order=["TIC 2"])
