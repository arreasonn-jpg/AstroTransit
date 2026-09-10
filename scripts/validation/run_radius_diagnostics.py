#!/usr/bin/env python3
"""Run known targets and emit TLS-versus-MAP radius diagnostic artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from astrotransit.pipelines.benchmark_pipeline import BenchmarkPipeline
from astrotransit.validation.radius_diagnostics import (
    build_radius_diagnostic_report,
    write_radius_diagnostic_report,
)


def _load_targets(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("targets", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("Target payload must be a list or an object containing 'targets'.")
    targets = []
    for row in rows:
        value = row.get("tic_id", row.get("source_id")) if isinstance(row, dict) else row
        if value is None:
            raise ValueError("Every target row must contain tic_id or source_id.")
        targets.append(str(value))
    return targets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-targets", type=int)
    args = parser.parse_args()

    targets = _load_targets(args.targets)
    if args.max_targets is not None:
        if args.max_targets < 0:
            raise ValueError("--max-targets cannot be negative")
        targets = targets[: args.max_targets]

    pipeline = BenchmarkPipeline()
    result = pipeline.run(confirmed_targets=targets)
    cadence_seconds = float(pipeline.settings.tess.exptime)
    report = build_radius_diagnostic_report(
        result.confirmed_results,
        configured_cadence_seconds=cadence_seconds,
    )
    json_path, csv_path = write_radius_diagnostic_report(report, args.output_dir)
    print(json_path)
    print(csv_path)


if __name__ == "__main__":
    main()
