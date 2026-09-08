from pathlib import Path
import sys
import time
import json
import argparse

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def find_best_sector(tic_id: str):
    try:
        import lightkurve as lk
        r = lk.search_lightcurve(
            tic_id, mission="TESS", author="SPOC", exptime=120
        )
        for row in r.table:
            m = str(row.get("mission", ""))
            if "Sector" in m:
                try:
                    return int(m.split("Sector")[-1].strip())
                except Exception:
                    continue
    except Exception:
        pass
    return -1


def main():
    parser = argparse.ArgumentParser(description="TOI-disi kesif taramasi")
    parser.add_argument("--limit", type=int, default=None, help="Ilk N hedef")
    parser.add_argument("--resume", action="store_true", help="Kaldigi yerden devam")
    parser.add_argument("--no-viz", action="store_true", help="Gorsel uretme")
    args = parser.parse_args()

    import pandas as pd
    from astrotransit.logging_config import setup_logging
    from astrotransit.pipelines.orchestrator import AstroTransitOrchestrator

    setup_logging(log_level="WARNING")

    targets_file = project_root / "benchmarks" / "discovery_targets.csv"
    if not targets_file.exists():
        print(f"HATA: {targets_file} yok")
        print("Once calistir: python scripts/build_non_toi_target_pool.py")
        return 1

    df = pd.read_csv(targets_file)
    if args.limit:
        df = df.head(args.limit)

    checkpoint_file = project_root / "outputs_discovery" / "discovery_progress.json"
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)

    processed_ids = set()
    if args.resume and checkpoint_file.exists():
        progress = json.loads(checkpoint_file.read_text())
        processed_ids = set(progress.get("processed_ids", []))
        print(f"OK Checkpoint yuklendi: {len(processed_ids)} onceden islenmis")

    print("=" * 72)
    print("  TOI-Disi Kesif Taramasi")
    print("=" * 72)
    print(f"  Toplam hedef: {len(df)}")
    print(f"  Gorsel: {'kapali' if args.no_viz else 'acik'}")
    print("=" * 72)
    print()

    stats = {
        "total": len(df),
        "completed": 0,
        "failed": 0,
        "with_candidates": 0,
        "confirmed": 0,
        "processed_ids": list(processed_ids),
    }

    t0 = time.time()

    with AstroTransitOrchestrator(
        force_map=True,
        skip_visualization=args.no_viz,
        skip_catalog=False,
        log_level="WARNING",
    ) as orch:

        # output dizinini ayarla
        orch.settings.general.output_dir = "outputs_discovery"

        for idx, row in df.iterrows():
            tic_num = int(row["tid"])
            tic_id = f"TIC {tic_num}"

            if tic_id in processed_ids:
                continue

            sector = int(row.get("sector", -1))
            if sector < 0:
                sector = find_best_sector(tic_id)

            if sector < 0:
                print(f"  [{stats['completed'] + stats['failed'] + 1}/{len(df)}] {tic_id} - sektor bulunamadi")
                stats["failed"] += 1
                stats["processed_ids"].append(tic_id)
                checkpoint_file.write_text(json.dumps(stats, indent=2))
                continue

            print(f"  [{stats['completed'] + stats['failed'] + 1}/{len(df)}] {tic_id} S{sector}", end=" ", flush=True)

            try:
                result = orch.run_single(tic_id, sectors=[sector])

                if result.success:
                    stats["completed"] += 1
                    if result.candidates_confirmed > 0:
                        stats["with_candidates"] += 1
                        stats["confirmed"] += result.candidates_confirmed

                        if result.sector_results:
                            sr = result.sector_results[0]
                            cls = "?"
                            score = 0
                            if sr.quality:
                                cls = sr.quality.score.candidate_class.value
                                score = sr.quality.score.total_score
                            print(f"| ADAY BULUNDU | Sinif {cls} | Skor {score:.0f}")
                        else:
                            print("| ADAY BULUNDU")
                    else:
                        print("| aday yok")
                else:
                    stats["failed"] += 1
                    print("| basarisiz")

            except Exception as e:
                stats["failed"] += 1
                print(f"| HATA: {str(e)[:50]}")

            stats["processed_ids"].append(tic_id)
            checkpoint_file.write_text(json.dumps(stats, indent=2))

            done = stats["completed"] + stats["failed"]
            if done % 10 == 0:
                elapsed = time.time() - t0
                remaining = len(df) - done - len(processed_ids)
                if done > 0:
                    eta = (elapsed / done) * remaining
                else:
                    eta = 0
                print(f"\n  === ILERLEME ({done}/{len(df)}) | "
                      f"aday: {stats['with_candidates']} | "
                      f"ETA: {eta/60:.1f} dk ===\n")

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
    print("  Sonuclari incele:")
    print("    python scripts/classify_novelty.py")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())