#!/usr/bin/env python3
"""
Architecture anomaly pilot wrapper.

Mevcut discovery target pool'u kullanır, discovery taramasını çalıştırır
ve sonrasında candidate parquet'i architecture-anomaly açısından sıralar.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger


def run_cmd(cmd: str, logfile: Path) -> None:
    logfile.parent.mkdir(parents=True, exist_ok=True)
    bash_cmd = f"set -o pipefail; {cmd} 2>&1 | tee '{logfile}'"
    logger.info(f"Çalıştırılıyor: {cmd}")
    subprocess.run(["bash", "-lc", bash_cmd], check=True)


def backup_file(src: Path, backup_dir: Path, label: str) -> Path | None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        return None
    dst = backup_dir / f"{label}.backup"
    shutil.copy2(src, dst)
    return dst


def restore_file(backup: Path | None, dst: Path) -> None:
    if backup is None:
        return
    shutil.copy2(backup, dst)


def remove_known_outputs(outputs_dir: Path) -> None:
    outputs_dir.mkdir(parents=True, exist_ok=True)

    removed = 0

    root_patterns = [
        "novel_candidates*.parquet",
        "novel_candidates*.csv",
        "novel_candidates*.json",
        "discovery_classified.parquet",
        "discovery_progress.json",
    ]
    for pat in root_patterns:
        for p in outputs_dir.glob(pat):
            try:
                p.unlink()
                removed += 1
            except Exception:
                logger.warning(f"Silinemedi: {p}")

    for sub in ["json", "parquet", "csv"]:
        subdir = outputs_dir / sub
        if subdir.exists():
            for p in subdir.glob("*"):
                if p.is_file():
                    try:
                        p.unlink()
                        removed += 1
                    except Exception:
                        logger.warning(f"Silinemedi: {p}")

    logger.info(f"outputs_discovery temizliği tamamlandı, kaldırılan dosya sayısı: {removed}")


def main():
    parser = argparse.ArgumentParser(description="Run architecture anomaly pilot")
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--config", default="configs/default.toml")
    parser.add_argument("--clean-known-outputs", action="store_true")
    parser.add_argument("--viz", action="store_true")
    args = parser.parse_args()

    runroot = Path("campaign_runs") / args.campaign
    (runroot / "logs").mkdir(parents=True, exist_ok=True)
    (runroot / "config").mkdir(parents=True, exist_ok=True)
    (runroot / "snapshots").mkdir(parents=True, exist_ok=True)

    default_cfg = Path("configs/default.toml")
    selected_cfg = Path(args.config)
    default_cfg_backup = backup_file(default_cfg, runroot / "config", "default_toml")
    if selected_cfg.exists():
        shutil.copy2(selected_cfg, default_cfg)
        shutil.copy2(selected_cfg, runroot / "config" / "selected_config.toml")

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "campaign": args.campaign,
        "limit": args.limit,
        "config": args.config,
        "viz": bool(args.viz),
    }
    with (runroot / "config" / "campaign_manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    try:
        if args.clean_known_outputs:
            remove_known_outputs(Path("outputs_discovery"))

        run_cmd("python scripts/maintenance/verify_install.py", runroot / "logs" / "00_verify.log")
        run_cmd("python scripts/maintenance/check_project.py", runroot / "logs" / "01_check_project.log")

        no_viz_flag = "" if args.viz else "--no-viz"
        run_cmd(
            f"python scripts/discovery/run_discovery_pilot_v2.py --limit {args.limit} {no_viz_flag}".strip(),
            runroot / "logs" / "10_discovery.log",
        )

        run_cmd("python scripts/discovery/classify_novelty.py", runroot / "logs" / "11_classify_novelty.log")
        run_cmd("python scripts/discovery/filter_discovery_candidates.py", runroot / "logs" / "12_filter_candidates.log")
        run_cmd("python scripts/discovery/refine_architecture_anomalies.py", runroot / "logs" / "13_refine_architecture.log")

        # snapshot
        for p in [
            Path("outputs_discovery/parquet/astrotransit_candidates.parquet"),
            Path("outputs_discovery/novel_candidates.csv"),
            Path("outputs_discovery/novel_candidates.parquet"),
            Path("outputs_discovery/novel_candidates_prioritized.csv"),
            Path("outputs_discovery/novel_candidates_prioritized.parquet"),
            Path("outputs_discovery/novel_candidates_architecture_prioritized.csv"),
            Path("outputs_discovery/novel_candidates_architecture_prioritized.parquet"),
        ]:
            if p.exists():
                shutil.copy2(p, runroot / "snapshots" / p.name)

        print()
        print("=" * 100)
        print("ARCHITECTURE ANOMALY PILOT COMPLETE")
        print("=" * 100)
        print(f"Campaign : {args.campaign}")
        print(f"Runroot  : {runroot}")
        print(f"Snapshots: {runroot / 'snapshots'}")
        print("=" * 100)

    finally:
        restore_file(default_cfg_backup, default_cfg)
        logger.info("default.toml geri yüklendi.")


if __name__ == "__main__":
    main()
