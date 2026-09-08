"""
Tam tarama sistemi.

Pilot mod (--pilot): 100 hedef, benchmarks/pilot_targets.csv
Custom mod (--targets FILE): kendi hedef listeniz

Ozellikler:
- Checkpoint (kesildiginde devam edilir)
- Hata toleransi (bir hedef fail -> devam)
- Progress bar
- Otomatik cache ve retry
"""

from __future__ import annotations

import sys
import time
import json
import argparse
from pathlib import Path
from dataclasses import dataclass, field, asdict

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


@dataclass
class ScanProgress:
    """Tarama ilerleme durumu."""
    total_targets: int = 0
    completed: int = 0
    failed: int = 0
    with_candidates: int = 0
    confirmed_planets: int = 0
    processed_ids: list = field(default_factory=list)
    failed_ids: list = field(default_factory=list)
    start_time: float = 0.0

    @property
    def remaining(self) -> int:
        return self.total_targets - self.completed - self.failed

    @property
    def elapsed_sec(self) -> float:
        return time.time() - self.start_time if self.start_time > 0 else 0

    @property
    def eta_sec(self) -> float:
        if self.completed == 0:
            return 0
        avg_time = self.elapsed_sec / (self.completed + self.failed)
        return avg_time * self.remaining


def save_checkpoint(progress: ScanProgress, path: Path):
    """Ilerlemeyi kaydet."""
    data = asdict(progress)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_checkpoint(path: Path) -> ScanProgress:
    """Ilerlemeyi yukle."""
    if not path.exists():
        return ScanProgress()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return ScanProgress(**data)


def format_time(sec: float) -> str:
    """Saniyeyi okunaklı hale getir."""
    if sec < 60:
        return f"{sec:.0f}s"
    elif sec < 3600:
        return f"{sec/60:.1f}dk"
    else:
        return f"{sec/3600:.1f}sa"


def find_best_sector(tic_id: str) -> int:
    """MAST'tan hedefin ilk sektorunu bul."""
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
                except (ValueError, TypeError):
                    continue
    except Exception:
        pass
    return -1


def main():
    parser = argparse.ArgumentParser(description="Tam TESS taramasi")
    parser.add_argument(
        "--pilot",
        action="store_true",
        help="Pilot mod: 100 TOI hedef",
    )
    parser.add_argument(
        "--targets",
        type=str,
        default=None,
        help="Ozel hedef listesi (CSV)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Kaldigi yerden devam et",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Ilk N hedefi isle (test icin)",
    )
    parser.add_argument(
        "--no-viz",
        action="store_true",
        help="Gorsel uretme (hizli)",
    )
    args = parser.parse_args()

    import pandas as pd
    from astrotransit.logging_config import setup_logging
    from astrotransit.pipelines.orchestrator import AstroTransitOrchestrator

    setup_logging(log_level="WARNING")

    # Hedef dosyasi
    if args.pilot:
        targets_file = project_root / "benchmarks" / "pilot_targets.csv"
    elif args.targets:
        targets_file = Path(args.targets)
    else:
        print("HATA: --pilot veya --targets belirtin")
        return 1

    if not targets_file.exists():
        print(f"HATA: {targets_file} yok")
        return 1

    # Yukle
    df = pd.read_csv(targets_file)
    print(f"OK {len(df)} hedef yuklendi: {targets_file.name}")

    if args.limit:
        df = df.head(args.limit)
        print(f"   Limit uygulandi: {args.limit}")

    # Checkpoint
    checkpoint_file = project_root / "outputs" / "scan_progress.json"
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)

    if args.resume:
        progress = load_checkpoint(checkpoint_file)
        print(f"OK Checkpoint yuklendi: {progress.completed} tamamlanmis")
    else:
        progress = ScanProgress(total_targets=len(df))
        progress.start_time = time.time()

    # Islenmemis hedefler
    processed_set = set(progress.processed_ids + progress.failed_ids)

    # Baslama
    print()
    print("=" * 70)
    print("  TAM TESS TARAMASI - BASLADI")
    print("=" * 70)
    print(f"  Toplam hedef: {progress.total_targets}")
    print(f"  Islenecek:    {progress.total_targets - len(processed_set)}")
    print(f"  Gorsel:       {'kapali' if args.no_viz else 'acik'}")
    print("=" * 70)
    print()

    # Orchestrator
    with AstroTransitOrchestrator(
        force_map=True,
        skip_visualization=args.no_viz,
        skip_catalog=False,
        log_level="WARNING",
    ) as orch:

        for idx, row in df.iterrows():
            tic_num = int(row.get("tid", row.get("tic_id", 0)))
            tic_id = f"TIC {tic_num}"

            if tic_id in processed_set:
                continue

            progress_now = progress.completed + progress.failed + 1
            print(f"\n[{progress_now}/{progress.total_targets}] "
                  f"TIC {tic_num} - TOI-{row.get('toi', '?')}")

            # Sektor bul
            sector = find_best_sector(tic_id)
            if sector < 0:
                print("  ⚠ Sektor bulunamadi, atlaniyor")
                progress.failed += 1
                progress.failed_ids.append(tic_id)
                save_checkpoint(progress, checkpoint_file)
                continue

            print(f"  Sektor: {sector}", end=" ")

            try:
                t0 = time.time()
                result = orch.run_single(tic_id, sectors=[sector])
                dt = time.time() - t0

                if result.success:
                    n_conf = result.candidates_confirmed
                    if n_conf > 0:
                        progress.with_candidates += 1
                        progress.confirmed_planets += n_conf

                        # Sinif bilgisi
                        if result.sector_results:
                            sr = result.sector_results[0]
                            if sr.quality:
                                cls = sr.quality.score.candidate_class.value
                                skor = sr.quality.score.total_score
                                print(f"| {dt:.0f}s | Sinif {cls} | Skor {skor:.0f}")
                            else:
                                print(f"| {dt:.0f}s | Onaylandi")
                        else:
                            print(f"| {dt:.0f}s | Onaylandi")
                    else:
                        print(f"| {dt:.0f}s | Aday yok")

                    progress.completed += 1
                    progress.processed_ids.append(tic_id)
                else:
                    print(f"| {dt:.0f}s | Basarisiz: {result.error[:40]}")
                    progress.failed += 1
                    progress.failed_ids.append(tic_id)

            except Exception as e:
                print(f"| HATA: {str(e)[:50]}")
                progress.failed += 1
                progress.failed_ids.append(tic_id)

            # Checkpoint kaydet
            save_checkpoint(progress, checkpoint_file)

            # Her 10 hedefte ozet
            if progress_now % 10 == 0:
                print()
                print(f"  === ILERLEME ({progress_now}/{progress.total_targets}) ===")
                print(f"  Tamamlanan:      {progress.completed}")
                print(f"  Aday bulunan:    {progress.with_candidates}")
                print(f"  Onaylı gezegen:  {progress.confirmed_planets}")
                print(f"  Basarisiz:       {progress.failed}")
                print(f"  Sure:            {format_time(progress.elapsed_sec)}")
                print(f"  ETA:             {format_time(progress.eta_sec)}")
                print()

    # Nihai rapor
    elapsed = progress.elapsed_sec
    print()
    print("=" * 70)
    print("  TARAMA TAMAMLANDI")
    print("=" * 70)
    print(f"  Toplam sure:       {format_time(elapsed)}")
    print(f"  Islenen hedef:     {progress.completed + progress.failed}")
    print(f"  Basarili:          {progress.completed}")
    print(f"  Basarisiz:         {progress.failed}")
    print(f"  Aday bulunan:      {progress.with_candidates}")
    print(f"  Onaylı gezegen:    {progress.confirmed_planets}")
    print()
    print(f"  Basari orani:      {100*progress.completed/max(1,progress.total_targets):.1f}%")
    print(f"  Aday orani:        {100*progress.with_candidates/max(1,progress.completed):.1f}%")
    print()
    print("=" * 70)
    print()
    print("  Sonuclari incele:")
    print("    python -c \"import pandas as pd; "
          "df=pd.read_parquet('outputs/parquet/astrotransit_candidates.parquet'); "
          "print(f'{len(df)} kayit'); "
          "print(df['candidate_class'].value_counts())\"")
    print()
    print("  Dashboard:")
    print("    streamlit run dashboard/app.py")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())