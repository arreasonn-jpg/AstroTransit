"""Generate only figures supported by an existing validation report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from astrotransit.validation.plots import generate_validation_figures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    paths = generate_validation_figures(report, args.output_dir)
    print(f"Generated {len(paths)} figures in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
