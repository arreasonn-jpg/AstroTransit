from pathlib import Path
import sys
import time
import json
import argparse

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))


def main():
    parser = argparse.ArgumentParser(description="TOI-disi kesif taramasi v2")
    parser.add_argument("--limit", type=int, default=None, help="Ilk N hedef")
    parser.add_argument("--resume", action="store_true", help="Kaldigi yerden devam")
    parser.add_argument("--no-viz", action="store_true", help="Gorsel uretme")
    args = parser.parse_args()

    import pandas as pd
    from astrotransit.logging_config import setup_logging
    from astrotransit.settings import load_settings
    from astrotransit.pipelines.tess_pipeline import TESSPipeline
    from astrotransit.outputs.writers import OutputManager

    setup_logging(log_level="WARNING")

    targets_file = project_root / "benchmarks" / "discovery_targets.csv"
    if not targets_file.exists():
        print(f"HATA: {targets_file} yok")
        print("Once calistir: python scripts/discovery/build_non_toi_target_pool_v3.py")
        return 1

    df = pd.read_csv(targets_file)
    if args.limit:
        df = df.head(args.limit)

    # discovery icin ayri output klasoru
    settings = load_settings(project_root / "configs" / "default.toml")
    settings.general.output_dir = "outputs_discovery"
    settings.outputs.save_figures = not args.no_viz

    out = OutputManager(settings=settings)
    pipe = TESSPipeline(
        settings=settings,
        output_manager=out,
        force_map=True,
        skip_visualization=args.no_viz,
        skip_catalog=False,
    )

    checkpoint_file = project_root / "outputs_discovery" / "discovery_progress.json"
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)

    processed_ids = set()
    stats = {
        "total": len(df),
        "completed": 0,
        "failed": 0,
        "with_candidates": 0,
        "confirmed": 0,
        "processed_ids": [],
        "failed_ids": [],
    }

    if args.resume and checkpoint_file.exists():
        try:
            progress = json.loads(checkpoint_file.read_text(encoding="utf-8"))
            processed_ids = set(progress.get("processed_ids", []))
            stats = progress
            print(f"OK Checkpoint yuklendi: {len(processed_ids)} islenmis hedef")
        except Exception as e:
            print(f"UYARI checkpoint okunamadi: {e}")

    print("=" * 72)
    print("  TOI-Disi Kesif Taramasi v2")
    print("=" * 72)
    print(f"  Toplam hedef: {len(df)}")
    print(f"  Gorsel: {'kapali' if args.no_viz else 'acik'}")
    print("  Output: outputs_discovery/")
    print("=" * 72)
    print()

    t0 = time.time()

    try:
        for i, row in df.iterrows():
            tid = int(row["tid"])
            tic_id = f"TIC {tid}"
            sector = int(row["sector"])

            if tic_id in processed_ids:
                continue

            step = stats["completed"] + stats["failed"] + 1
            print(f"[{step}/{len(df)}] {tic_id} S{sector}", end=" ", flush=True)

            try:
                result = pipe.run_target(tic_id, sectors=[sector])

                if result.success:
                    stats["completed"] += 1

                    if result.candidates_confirmed > 0:
                        stats["with_candidates"] += 1
                        stats["confirmed"] += result.candidates_confirmed

                        if result.sector_results:
                            sr = result.sector_results[0]
                            cls = "?"
                            score = 0.0
                            if sr.quality is not None:
                                cls = sr.quality.score.candidate_class.value
                                score = sr.quality.score.total_score
                            print(f"| ADAY BULUNDU | Sinif {cls} | Skor {score:.0f}")
                        else:
                            print("| ADAY BULUNDU")
                    else:
                        print("| aday yok")
                else:
                    stats["failed"] += 1
                    stats["failed_ids"].append(tic_id)
                    print(f"| basarisiz: {result.error[:50]}")

            except Exception as e:
                stats["failed"] += 1
                stats["failed_ids"].append(tic_id)
                print(f"| HATA: {str(e)[:60]}")

            stats["processed_ids"].append(tic_id)
            checkpoint_file.write_text(json.dumps(stats, indent=2), encoding="utf-8")

            done = stats["completed"] + stats["failed"]
            if done % 10 == 0:
                elapsed = time.time() - t0
                remaining = len(df) - done
                eta = (elapsed / done) * remaining if done > 0 else 0
                print()
                print(f"  === ILERLEME ({done}/{len(df)}) ===")
                print(f"  Tamamlanan:   {stats['completed']}")
                print(f"  Basarisiz:    {stats['failed']}")
                print(f"  Aday bulunan: {stats['with_candidates']}")
                print(f"  Onayli:       {stats['confirmed']}")
                print(f"  Sure:         {elapsed/60:.1f} dk")
                print(f"  ETA:          {eta/60:.1f} dk")
                print()

    finally:
        pipe.close()

    elapsed = time.time() - t0

    print()
    print("=" * 72)
    print("  KESIF TARAMASI TAMAMLANDI")
    print("=" * 72)
    print(f"  Sure: {elapsed/60:.1f} dk")
    print(f"  Basarili: {stats['completed']}")
    print(f"  Basarisiz: {stats['failed']}")
    print(f"  Aday bulunan: {stats['with_candidates']}")
    print(f"  Onayli: {stats['confirmed']}")
    print()
    print("  Sonraki adim:")
    print("    python scripts/discovery/classify_novelty.py")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())