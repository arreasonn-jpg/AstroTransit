"""Compare two benchmark runs and emit a machine-readable determinism gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from astrotransit.validation.determinism import compare_benchmark_artifacts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JSON, CSV, metrics ve hedef sırasını iki benchmark koşusu arasında karşılaştır."
    )
    parser.add_argument("json_a", type=Path, help="Run A benchmark JSON")
    parser.add_argument("csv_a", type=Path, help="Run A targets CSV")
    parser.add_argument("json_b", type=Path, help="Run B benchmark JSON")
    parser.add_argument("csv_b", type=Path, help="Run B targets CSV")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="İsteğe bağlı determinism report JSON yolu",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = compare_benchmark_artifacts(args.json_a, args.csv_a, args.json_b, args.csv_b)
    payload = report.to_dict()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
