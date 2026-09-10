#!/usr/bin/env python3
"""Aggregate independently executed known-planet benchmark shard reports."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from astrotransit.validation.artifacts import write_artifact
from astrotransit.validation.benchmark_report import normalize_target_id
from astrotransit.validation.shard_aggregation import aggregate_benchmark_shards


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _target_order(path: Path | None) -> list[str] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("targets", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("Target order JSON must be a list or {targets: [...]} object")
    return [normalize_target_id(row.get("tic_id", row.get("target_id"))) for row in rows]


def _write_csv(path: Path, targets: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(targets[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for target in targets:
            row = dict(target)
            if isinstance(row.get("notes"), list):
                row["notes"] = "; ".join(str(note) for note in row["notes"])
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shards", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--csv-output", required=True, type=Path)
    parser.add_argument("--target-order-file", type=Path)
    args = parser.parse_args()

    reports = [_load_object(path) for path in args.shards]
    aggregate = aggregate_benchmark_shards(
        reports,
        target_order=_target_order(args.target_order_file),
    )
    write_artifact(aggregate, args.output, provenance=aggregate["provenance"])
    _write_csv(args.csv_output, aggregate["targets"])
    print(
        f"Aggregated {len(reports)} shards and "
        f"{aggregate['metrics']['n_targets']} targets -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
