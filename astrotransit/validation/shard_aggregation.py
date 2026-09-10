"""Deterministic aggregation for independently executed benchmark shards."""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from statistics import mean, median
from typing import Any

from astrotransit.validation.determinism import output_hash

_REQUIRED_METADATA = (
    "report_type",
    "pipeline_version",
    "period_tolerance_fraction",
    "radius_tolerance_fraction",
)


def aggregate_benchmark_shards(
    reports: Iterable[Mapping[str, Any]],
    *,
    target_order: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Merge benchmark shard reports and recompute every aggregate metric.

    Shard-level metrics are deliberately ignored. Target rows are the measured
    source of truth, so aggregation cannot hide a partial or duplicated shard.
    """

    shards = [dict(report) for report in reports]
    if not shards:
        raise ValueError("At least one benchmark shard is required")

    reference = _validated_metadata(shards[0])
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()
    limitations: list[str] = []
    source_hashes: list[str] = []
    source_commits: set[str] = set()

    for index, shard in enumerate(shards):
        metadata = _validated_metadata(shard)
        for key in _REQUIRED_METADATA:
            if metadata[key] != reference[key]:
                raise ValueError(f"Shard {index} metadata mismatch: {key}")
        rows = shard.get("targets")
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"Shard {index} has no measured target rows")
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError(f"Shard {index} contains a non-object target")
            target = dict(row)
            target_id = str(target.get("target_id", "")).strip()
            if not target_id:
                raise ValueError(f"Shard {index} contains a target without target_id")
            if target_id in seen:
                raise ValueError(f"Duplicate target across shards: {target_id}")
            seen.add(target_id)
            targets.append(target)
        for limitation in shard.get("limitations", []):
            text = str(limitation)
            if text and text not in limitations:
                limitations.append(text)
        provenance = shard.get("provenance", {})
        if isinstance(provenance, Mapping) and provenance.get("git_commit"):
            source_commits.add(str(provenance["git_commit"]))
        source_hashes.append(output_hash(shard))

    targets = _ordered_targets(targets, target_order)
    timestamps = [
        str(shard.get("metadata", {}).get("generated_at_utc", ""))
        for shard in shards
    ]
    metadata = dict(reference)
    metadata["generated_at_utc"] = max(timestamps)
    metadata["aggregation_method"] = "deterministic_target_row_merge_v1"
    metadata["n_shards"] = len(shards)

    limitations.append(
        "Aggregate metrics were recomputed from target rows; shard metrics were not averaged."
    )
    provenance = {
        "aggregation_method": "deterministic_target_row_merge_v1",
        "source_shard_count": len(shards),
        "source_output_hashes": source_hashes,
        "source_git_commits": sorted(source_commits),
    }
    return {
        "metadata": metadata,
        "metrics": _metrics(targets),
        "targets": targets,
        "limitations": limitations,
        "provenance": provenance,
    }


def _validated_metadata(report: Mapping[str, Any]) -> dict[str, Any]:
    metadata = report.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError("Benchmark shard metadata must be an object")
    missing = [key for key in _REQUIRED_METADATA if key not in metadata]
    if missing:
        raise ValueError(f"Benchmark shard metadata missing: {missing}")
    if metadata["report_type"] != "known_target_benchmark_performance":
        raise ValueError("Unsupported benchmark report_type")
    return dict(metadata)


def _ordered_targets(
    targets: list[dict[str, Any]],
    target_order: Sequence[str] | None,
) -> list[dict[str, Any]]:
    if target_order is None:
        return sorted(targets, key=lambda row: str(row["target_id"]))
    order = [str(target_id) for target_id in target_order]
    if len(order) != len(set(order)):
        raise ValueError("target_order contains duplicates")
    measured = {str(row["target_id"]) for row in targets}
    if set(order) != measured:
        raise ValueError("target_order does not match measured target IDs")
    rank = {target_id: index for index, target_id in enumerate(order)}
    return sorted(targets, key=lambda row: rank[str(row["target_id"])])


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _rounded_mean(values: list[float]) -> float | None:
    return round(mean(values), 8) if values else None


def _rounded_median(values: list[float]) -> float | None:
    return round(median(values), 8) if values else None


def _numbers(targets: list[dict[str, Any]], key: str) -> list[float]:
    return [float(row[key]) for row in targets if row.get(key) is not None]


def _metrics(targets: list[dict[str, Any]]) -> dict[str, Any]:
    n_targets = len(targets)
    n_detected = sum(bool(row.get("detected")) for row in targets)
    n_correct = sum(bool(row.get("correct")) for row in targets)
    n_period = sum(bool(row.get("period_recovered")) for row in targets)
    n_radius = sum(bool(row.get("radius_recovered")) for row in targets)
    consistency = [row for row in targets if row.get("sector_consistent") is not None]
    period_days = _numbers(targets, "period_error_days")
    period_fraction = _numbers(targets, "period_error_fraction")
    radius_rearth = _numbers(targets, "radius_error_rearth")
    radius_fraction = _numbers(targets, "radius_error_fraction")
    return {
        "n_targets": n_targets,
        "n_detected": n_detected,
        "detection_recall": _ratio(n_detected, n_targets),
        "n_correct": n_correct,
        "correct_recovery_rate": _ratio(n_correct, n_targets),
        "n_period_recovered": n_period,
        "period_recovery_rate": _ratio(n_period, n_targets),
        "period_recovery_error_mean_days": _rounded_mean(period_days),
        "period_recovery_error_median_days": _rounded_median(period_days),
        "period_recovery_error_mean_fraction": _rounded_mean(period_fraction),
        "period_recovery_error_median_fraction": _rounded_median(period_fraction),
        "n_radius_recovered": n_radius,
        "radius_recovery_rate": _ratio(n_radius, n_targets),
        "radius_recovery_error_mean_rearth": _rounded_mean(radius_rearth),
        "radius_recovery_error_median_rearth": _rounded_median(radius_rearth),
        "radius_recovery_error_mean_fraction": _rounded_mean(radius_fraction),
        "radius_recovery_error_median_fraction": _rounded_median(radius_fraction),
        "n_sector_consistency_evaluated": len(consistency),
        "sector_consistency_rate": _ratio(
            sum(bool(row["sector_consistent"]) for row in consistency),
            len(consistency),
        ),
        "false_positive_rejection": None,
        "false_positive_rejection_status": "not_evaluated_no_labeled_false_positive_set",
        "n_false_positive_targets": 0,
    }


__all__ = ["aggregate_benchmark_shards"]
