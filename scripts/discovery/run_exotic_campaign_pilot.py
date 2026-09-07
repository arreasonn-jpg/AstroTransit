#!/usr/bin/env python3
"""
Exotic/temperate discovery campaign wrapper.

Yapar:
- exotic target pool yükleme
- tema filtresi
- önceki adayları blacklist ile dışlama
- aktif discovery target pool'u geçici değiştirme
- seçili config ile discovery zincirini çalıştırma
- snapshot / log / manifest üretme
- iş bitince config ve aktif pool'u geri yükleme

Örnek:
    python scripts/discovery/run_exotic_campaign_pilot.py \
      --input-pool benchmarks/discovery_targets_temperate_small.csv \
      --theme temperate-small \
      --config configs/exotic_temperate.toml \
      --campaign 2026-07-17_exotic_temperate_pilot \
      --max-targets 120 \
      --limit 80 \
      --clean-known-outputs

    python scripts/discovery/run_exotic_campaign_pilot.py \
      --input-pool benchmarks/discovery_targets_giant_hz.csv \
      --theme giant-hz \
      --config configs/exotic_giant_hz.toml \
      --campaign 2026-07-17_exotic_giant_hz_pilot \
      --max-targets 120 \
      --limit 80 \
      --clean-known-outputs
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from loguru import logger


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def write_table(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".parquet":
        df.to_parquet(path, index=False)
    else:
        df.to_csv(path, index=False)


def extract_tic_from_row(row: pd.Series) -> int | None:
    for col in ["tic_id", "tid"]:
        if col in row.index and pd.notna(row[col]):
            try:
                return int(float(row[col]))
            except Exception:
                pass

    for col in ["source_id", "target_id"]:
        if col in row.index and pd.notna(row[col]):
            m = re.search(r"(\d+)", str(row[col]))
            if m:
                try:
                    return int(m.group(1))
                except Exception:
                    pass

    return None


def read_exclude_tics(path: Path | None) -> set[int]:
    if path is None or not path.exists():
        return set()

    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.search(r"(\d+)", s)
        if m:
            out.add(int(m.group(1)))
    return out


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

    # 1) root dosyalar
    root_patterns = [
        "novel_candidates*.parquet",
        "novel_candidates*.csv",
        "novel_candidates*.json",
        "discovery_classified.parquet",
        "discovery_progress.json",
        "candidates*.parquet",
        "candidates*.csv",
    ]
    for pat in root_patterns:
        for p in outputs_dir.glob(pat):
            try:
                p.unlink()
                removed += 1
            except Exception:
                logger.warning(f"Silinemedi: {p}")

    # 2) json alt klasörü
    json_dir = outputs_dir / "json"
    if json_dir.exists():
        for p in json_dir.glob("*.json"):
            try:
                p.unlink()
                removed += 1
            except Exception:
                logger.warning(f"Silinemedi: {p}")
        for p in json_dir.glob("*.jsonl"):
            try:
                p.unlink()
                removed += 1
            except Exception:
                logger.warning(f"Silinemedi: {p}")

    # 3) parquet alt klasörü
    parquet_dir = outputs_dir / "parquet"
    if parquet_dir.exists():
        for p in parquet_dir.glob("*.parquet"):
            try:
                p.unlink()
                removed += 1
            except Exception:
                logger.warning(f"Silinemedi: {p}")

    # 4) csv alt klasörü
    csv_dir = outputs_dir / "csv"
    if csv_dir.exists():
        for p in csv_dir.glob("*.csv"):
            try:
                p.unlink()
                removed += 1
            except Exception:
                logger.warning(f"Silinemedi: {p}")

    logger.info(f"outputs_discovery temizliği tamamlandı, kaldırılan dosya sayısı: {removed}")


def run_cmd(cmd: str, logfile: Path) -> None:
    logfile.parent.mkdir(parents=True, exist_ok=True)
    bash_cmd = f"set -o pipefail; {cmd} 2>&1 | tee '{logfile}'"
    logger.info(f"Çalıştırılıyor: {cmd}")
    subprocess.run(["bash", "-lc", bash_cmd], check=True)


def theme_filter(df: pd.DataFrame, theme: str) -> pd.DataFrame:
    if "exotic_target_theme" not in df.columns or theme == "auto":
        return df.copy()

    if theme == "temperate-small":
        keep = {"TEMPERATE_SMALL_HOST", "HZ_ACCESSIBLE_COOL_STAR"}
        return df[df["exotic_target_theme"].isin(keep)].copy()

    if theme == "giant-hz":
        keep = {"GIANT_HZ_HOST_SYSTEM"}
        return df[df["exotic_target_theme"].isin(keep)].copy()

    return df.copy()


def sort_pool(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["exotic_target_score", "verified_priority_score", "pool_priority_score"]:
        if col in df.columns:
            return df.sort_values(col, ascending=False).reset_index(drop=True)
    return df.reset_index(drop=True)


def snapshot_outputs(runroot: Path) -> None:
    snap = runroot / "snapshots"
    snap.mkdir(parents=True, exist_ok=True)

    candidates = [
        Path("outputs_discovery/novel_candidates_prioritized.parquet"),
        Path("outputs_discovery/novel_candidates_prioritized.csv"),
        Path("outputs_discovery/novel_candidates_science_prioritized.parquet"),
        Path("outputs_discovery/novel_candidates_science_prioritized.csv"),
        Path("outputs_discovery/novel_candidates_exotic_prioritized.parquet"),
        Path("outputs_discovery/novel_candidates_exotic_prioritized.csv"),
    ]

    for src in candidates:
        if src.exists():
            shutil.copy2(src, snap / src.name)


def main():
    parser = argparse.ArgumentParser(description="Run exotic discovery campaign pilot")
    parser.add_argument("--input-pool", required=True, help="Input exotic target pool CSV/parquet")
    parser.add_argument("--theme", choices=["temperate-small", "giant-hz", "auto"], default="auto")
    parser.add_argument("--config", required=True, help="Config to use temporarily as configs/default.toml")
    parser.add_argument("--campaign", required=True, help="Campaign name")
    parser.add_argument("--exclude-tics-file", default="benchmarks/exotic_exclude_tics.txt")
    parser.add_argument("--max-targets", type=int, default=120)
    parser.add_argument("--limit", type=int, default=80, help="Discovery run limit")
    parser.add_argument("--viz", action="store_true", help="Enable visualization (default: disabled)")
    parser.add_argument("--clean-known-outputs", action="store_true", help="Clear known outputs_discovery files before run")
    args = parser.parse_args()

    input_pool = Path(args.input_pool)
    config_path = Path(args.config)
    exclude_file = Path(args.exclude_tics_file) if args.exclude_tics_file else None

    if not input_pool.exists():
        raise FileNotFoundError(f"Input pool not found: {input_pool}")
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    runroot = Path("campaign_runs") / args.campaign
    (runroot / "config").mkdir(parents=True, exist_ok=True)
    (runroot / "logs").mkdir(parents=True, exist_ok=True)
    (runroot / "notes").mkdir(parents=True, exist_ok=True)
    (runroot / "snapshots").mkdir(parents=True, exist_ok=True)

    logger.info(f"Campaign başlıyor: {args.campaign}")

    # 1) pool yükle
    df = read_table(input_pool)
    logger.info(f"Girdi pool yüklendi: {input_pool} | satır={len(df)}")

    # 2) theme filtresi
    df = theme_filter(df, args.theme)
    logger.info(f"Tema filtresi sonrası satır={len(df)}")

    # 3) blacklist
    exclude_tics = read_exclude_tics(exclude_file)
    if exclude_tics:
        tic_series = df.apply(extract_tic_from_row, axis=1)
        df = df.loc[~tic_series.isin(exclude_tics)].copy()
        logger.info(f"Blacklist sonrası satır={len(df)} | excluded={len(exclude_tics)}")

    # 4) sırala ve kes
    df = sort_pool(df)
    if args.max_targets > 0:
        df = df.head(args.max_targets).copy()

    logger.info(f"Nihai campaign pool satırı: {len(df)}")

    # 5) frozen pool yaz
    frozen_csv = runroot / "config" / "discovery_targets_frozen.csv"
    write_table(df, frozen_csv)

    # ayrıca aktif dosya için csv üret
    active_pool_path = Path("benchmarks/discovery_targets.csv")
    active_pool_backup = backup_file(active_pool_path, runroot / "config", "discovery_targets_csv")

    if frozen_csv.suffix.lower() == ".parquet":
        active_df = pd.read_parquet(frozen_csv)
        active_df.to_csv(active_pool_path, index=False)
    else:
        shutil.copy2(frozen_csv, active_pool_path)

    # 6) config swap
    default_cfg = Path("configs/default.toml")
    default_cfg_backup = backup_file(default_cfg, runroot / "config", "default_toml")
    shutil.copy2(config_path, default_cfg)
    shutil.copy2(config_path, runroot / "config" / "selected_config.toml")

    # 7) manifest
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "campaign": args.campaign,
        "input_pool": str(input_pool),
        "theme": args.theme,
        "config": str(config_path),
        "exclude_tics_file": str(exclude_file) if exclude_file else None,
        "n_targets": int(len(df)),
        "max_targets": args.max_targets,
        "discovery_limit": args.limit,
        "viz_enabled": bool(args.viz),
        "columns": list(df.columns),
        "top10_source_ids": [str(x) for x in df.get("source_id", pd.Series(dtype=str)).head(10).tolist()],
    }
    with (runroot / "config" / "campaign_manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    try:
        # 8) outputs temizliği opsiyonel
        if args.clean_known_outputs:
            remove_known_outputs(Path("outputs_discovery"))

        # 9) preflight
        run_cmd("python scripts/maintenance/verify_install.py", runroot / "logs" / "00_verify.log")
        run_cmd("python scripts/maintenance/check_project.py", runroot / "logs" / "01_check_project.log")

        # 10) discovery
        no_viz_flag = "" if args.viz else "--no-viz"
        run_cmd(
            f"python scripts/discovery/run_discovery_pilot_v2.py --limit {args.limit} {no_viz_flag}".strip(),
            runroot / "logs" / "10_discovery.log",
        )

        # 11) novelty zinciri
        run_cmd("python scripts/discovery/classify_novelty.py", runroot / "logs" / "11_classify_novelty.log")
        run_cmd("python scripts/discovery/filter_discovery_candidates.py", runroot / "logs" / "12_filter_candidates.log")
        run_cmd("python scripts/discovery/refine_science_priorities.py", runroot / "logs" / "13_refine_science.log")
        run_cmd("python scripts/discovery/refine_exotic_priorities.py", runroot / "logs" / "14_refine_exotic.log")

        # 12) snapshot
        snapshot_outputs(runroot)

        logger.info("Exotic campaign başarıyla tamamlandı.")
        print()
        print("=" * 100)
        print("EXOTIC CAMPAIGN COMPLETE")
        print("=" * 100)
        print(f"Campaign : {args.campaign}")
        print(f"Runroot  : {runroot}")
        print(f"Pool     : {frozen_csv}")
        print("Snapshots:")
        print(f"  {runroot / 'snapshots'}")
        print("=" * 100)

    finally:
        # restore active pool and config
        restore_file(default_cfg_backup, default_cfg)
        restore_file(active_pool_backup, active_pool_path)
        logger.info("default.toml ve discovery_targets.csv geri yüklendi.")


if __name__ == "__main__":
    main()
