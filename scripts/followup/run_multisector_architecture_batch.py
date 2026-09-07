#!/usr/bin/env python3
"""
Batch multi-sector architecture search runner.

Amaç
----
Bir hedef havuzundan çok sektörlü adayları seçip
`multi_sector_coorbital_search.py` scriptini toplu çalıştırmak,
çıkan JSON raporlarını okuyup tek bir summary CSV/JSON üretmek.

Varsayılan kullanım:
    python scripts/followup/run_multisector_architecture_batch.py \
        --input benchmarks/discovery_targets_temperate_small_strict.csv \
        --top-n 5

Opsiyonel:
    --min-sectors 4
    --max-hz-period 200
    --max-tmag 10.5
    --auto-period-min 0.5
    --auto-period-max 20.0
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import pandas as pd
from loguru import logger


def extract_tic(x) -> int | None:
    if x is None:
        return None
    m = re.search(r"(\d+)", str(x))
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def main():
    parser = argparse.ArgumentParser(description="Batch multi-sector architecture runner")
    parser.add_argument("--input", required=True, help="Input target pool CSV/parquet")
    parser.add_argument("--top-n", type=int, default=5, help="How many targets to run")
    parser.add_argument("--min-sectors", type=int, default=4)
    parser.add_argument("--max-hz-period", type=float, default=200.0)
    parser.add_argument("--max-tmag", type=float, default=10.5)
    parser.add_argument("--auto-period-min", type=float, default=0.5)
    parser.add_argument("--auto-period-max", type=float, default=20.0)
    parser.add_argument("--duration-hours", type=float, default=2.0)
    parser.add_argument("--max-sectors", type=int, default=6)
    parser.add_argument("--output-dir", type=str, default="outputs_architecture_batch")
    parser.add_argument("--review-dir", type=str, default="outputs_architecture_review")
    parser.add_argument("--resume", action="store_true", help="Skip TICs that already have JSON output")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    review_dir = Path(args.review_dir)
    review_dir.mkdir(parents=True, exist_ok=True)

    if input_path.suffix.lower() == ".parquet":
        df = pd.read_parquet(input_path)
    else:
        df = pd.read_csv(input_path)

    # normalize TIC
    if "source_id" in df.columns:
        df["tic_id_extracted"] = df["source_id"].apply(extract_tic)
    elif "tid" in df.columns:
        df["tic_id_extracted"] = df["tid"].apply(extract_tic)
    else:
        raise ValueError("Input table has neither source_id nor tid")

    # filter
    keep = df.copy()
    if "sector_count_resolved" in keep.columns:
        keep = keep[keep["sector_count_resolved"] >= args.min_sectors]
    if "hz_center_period_days" in keep.columns:
        keep = keep[keep["hz_center_period_days"] <= args.max_hz_period]
    if "st_tmag" in keep.columns:
        keep = keep[keep["st_tmag"] <= args.max_tmag]

    if "exotic_target_score" in keep.columns:
        keep = keep.sort_values(
            ["sector_count_resolved", "exotic_target_score"],
            ascending=[False, False],
        )
    else:
        keep = keep.sort_values(
            ["sector_count_resolved"],
            ascending=[False],
        )

    keep = keep.head(args.top_n).copy()

    logger.info(f"Batch seçimi: {len(keep)} hedef")

    selected_csv = outdir / "batch_selected_targets.csv"
    keep.to_csv(selected_csv, index=False)

    results = []

    for _, row in keep.iterrows():
        tic = int(row["tic_id_extracted"])
        source_id = row.get("source_id", f"TIC {tic}")
        existing_json = review_dir / f"TIC_{tic}_multisector_coorbital.json"

        if args.resume and existing_json.exists():
            logger.info(f"Skip (resume): {source_id}")
            json_path = existing_json
            status = "SKIPPED_EXISTING"
            stdout_tail = ""
            stderr_tail = ""
        else:
            cmd = [
                "python",
                "scripts/followup/multi_sector_coorbital_search.py",
                "--tic", str(tic),
                "--auto-period",
                "--min-period", str(args.auto_period_min),
                "--max-period", str(args.auto_period_max),
                "--duration-hours", str(args.duration_hours),
                "--max-sectors", str(args.max_sectors),
                "--output-dir", str(review_dir),
            ]

            logger.info(f"Running: {' '.join(cmd)}")
            rc, stdout, stderr = run_cmd(cmd)

            stdout_tail = "\n".join(stdout.splitlines()[-20:]) if stdout else ""
            stderr_tail = "\n".join(stderr.splitlines()[-20:]) if stderr else ""

            if rc == 0 and existing_json.exists():
                status = "OK"
                json_path = existing_json
            else:
                status = f"FAILED_{rc}"
                json_path = None

        summary_row = {
            "source_id": source_id,
            "tic_id": tic,
            "sector_count_resolved": row.get("sector_count_resolved"),
            "st_tmag": row.get("st_tmag"),
            "st_teff": row.get("st_teff"),
            "st_rad": row.get("st_rad"),
            "hz_center_period_days": row.get("hz_center_period_days"),
            "exotic_target_score": row.get("exotic_target_score"),
            "status": status,
            "json_path": str(json_path) if json_path else "",
            "period": None,
            "t0": None,
            "duration_hours_used": None,
            "dur_phase": None,
            "n_sectors_analyzed": None,
            "sectors_analyzed": None,
            "L4_ASI": None,
            "L5_ASI": None,
            "verdict": None,
            "reason": None,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
        }

        if json_path and Path(json_path).exists():
            try:
                with open(json_path, encoding="utf-8") as f:
                    rep = json.load(f)

                summary_row.update({
                    "period": rep.get("parameters", {}).get("period"),
                    "t0": rep.get("parameters", {}).get("t0"),
                    "duration_hours_used": rep.get("parameters", {}).get("duration_hours"),
                    "dur_phase": rep.get("parameters", {}).get("dur_phase"),
                    "n_sectors_analyzed": len(rep.get("sectors_analyzed", [])),
                    "sectors_analyzed": ",".join(map(str, rep.get("sectors_analyzed", []))),
                    "L4_ASI": rep.get("cross_sector", {}).get("L4_ASI"),
                    "L5_ASI": rep.get("cross_sector", {}).get("L5_ASI"),
                    "verdict": rep.get("verdict"),
                    "reason": rep.get("reason"),
                })
            except Exception as exc:
                summary_row["status"] = "JSON_PARSE_FAILED"
                summary_row["stderr_tail"] = str(exc)

        results.append(summary_row)

    res_df = pd.DataFrame(results)

    # summary outputs
    csv_path = outdir / "multisector_architecture_summary.csv"
    json_path = outdir / "multisector_architecture_summary.json"

    res_df.to_csv(csv_path, index=False)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "n_targets": len(results),
                "results": results,
            },
            f,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    print()
    print("=" * 120)
    print("MULTI-SECTOR ARCHITECTURE BATCH SUMMARY")
    print("=" * 120)
    show_cols = [
        c for c in [
            "source_id", "status", "sector_count_resolved", "period",
            "n_sectors_analyzed", "L4_ASI", "L5_ASI", "verdict", "reason"
        ] if c in res_df.columns
    ]
    print(res_df[show_cols].to_string(index=False))
    print("=" * 120)
    print(f"Selected targets : {selected_csv}")
    print(f"Summary CSV      : {csv_path}")
    print(f"Summary JSON     : {json_path}")


if __name__ == "__main__":
    main()
