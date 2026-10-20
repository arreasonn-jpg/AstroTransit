"""Performans ölçüm kampanyası koşucusu.

``performance`` kapısının (program.json) `required_output` kanıtını
üretir: ``validation_runs/final_acceptance_v1/performance/report.json``.

Ölçüm birimi `astrotransit.validation.performance.measure_runtime`
(KiB/bayt birim sabitliği düzeltilmiş rss işaretlemesi) üzerinden;
`--op` ile ölçülecek işlem seçilir:

    noop      : sözleşme doğrulaması (içerik yok)
    csv-read  : belirtilen parquet/CSV boyut üstünden pandas okuma ölçümü

Eşikler çalıştırmadan önce CLI ile dondurulur; rapora aynen yazılır.

Kullanım:
    python scripts/validation/run_performance_campaign.py \
        --op noop --output validation_runs/final_acceptance_v1/performance/report.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Callable

from astrotransit.validation.artifacts import write_artifact
from astrotransit.validation.performance import measure_runtime


def _read_rows_for_read_op(source: Path) -> Callable[[], int]:
    """csv-read operasyonu: n satır okuma süresini ölçümlemeye bağler."""

    def op() -> int:
        import pandas as pd

        if source.suffix.lower() == ".parquet":
            frame = pd.read_parquet(source)
        else:
            frame = pd.read_csv(source)
        return len(frame)

    return op


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.validation.run_performance_campaign")
    parser.add_argument("--op", choices=["noop", "csv-read"], default="csv-read")
    parser.add_argument("--input", help="csv-read için parquet/CSV kaynağı")
    parser.add_argument("--repeat", type=int, default=3,
                        help="Ölçüm tekrar sayısı (medyan rapor edilir)")
    parser.add_argument("--declared-max-seconds-per-1k-rows", type=float, default=30.0,
                        help="Dondurulan kabul tavanı; saniye/1000 satır")
    parser.add_argument("--output", default="validation_runs/final_acceptance_v1/performance/report.json")
    args = parser.parse_args(argv)

    declared = {
        "op": args.op,
        "repeat": args.repeat,
        "declared_max_seconds_per_1k_rows": args.declared_max_seconds_per_1k_rows,
    }

    if args.op == "noop":
        rows_operated = 1
        op = lambda: None  # noqa: E731 — sözleşme ölçümü
    else:
        if not args.input:
            print("[error] --input zorunlu (--op csv-read)", file=sys.stderr)
            return 2
        source = Path(args.input)
        if not source.exists():
            print(f"[error] dosya yok: {source}", file=sys.stderr)
            return 2
        import pandas as pd

        if source.suffix.lower() == ".parquet":
            rows_operated = max(1, len(pd.read_parquet(source)))
        else:
            rows_operated = max(1, sum(1 for _ in source.open("rb")))
        op = _read_rows_for_read_op(source)

    measurements = []
    for i in range(max(1, args.repeat)):
        m = measure_runtime(f"{args.op}#{i + 1}", op, n_targets=rows_operated)
        measurements.append(m.to_dict())

    seconds_sorted = sorted(m["seconds"] for m in measurements)
    median_seconds = seconds_sorted[len(seconds_sorted) // 2]
    seconds_per_1k_rows = median_seconds / rows_operated * 1000
    # audit kapı sözleşmesi: closed için evidence status ∈ {"measured","pass"}.
    status = (
        "measured" if seconds_per_1k_rows <= args.declared_max_seconds_per_1k_rows
        else "measured_fail"
    )
    blocking = [] if status == "measured" else [
        f"saniye/1000 satır {seconds_per_1k_rows:.3f} > ilan edilen tavan "
        f"{args.declared_max_seconds_per_1k_rows:.3f}"
    ]
    payload = {
        "gate": "performance",
        "status": status,
        "declared": declared,
        "blocking_reasons": blocking,
        "result": {
            "rows_operated": rows_operated,
            "median_seconds": median_seconds,
            "seconds_per_1k_rows": seconds_per_1k_rows,
            "measurements": measurements,
        },
    }
    write_artifact(payload, args.output)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if status == "measured" else 1


if __name__ == "__main__":
    start = time.perf_counter()
    raise SystemExit(main())
