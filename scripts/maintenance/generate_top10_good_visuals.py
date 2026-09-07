from pathlib import Path
import sys
import pandas as pd

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))


def main():
    from astrotransit.settings import load_settings
    from astrotransit.pipelines.tess_pipeline import TESSPipeline
    from astrotransit.outputs.writers import OutputManager

    recal_path = project_root / "outputs" / "parquet" / "astrotransit_candidates_recal.parquet"
    if not recal_path.exists():
        print(f"HATA: {recal_path} bulunamadi")
        print("Once calistir: python scripts/maintenance/recalibrate_pilot_classes.py")
        return 1

    df = pd.read_parquet(recal_path)

    # GOOD + A/B
    mask = pd.Series([True] * len(df), index=df.index)

    if "scientific_status" in df.columns:
        mask &= df["scientific_status"] == "SCIENTIFICALLY_CORRECT"
    if "candidate_class_recal" in df.columns:
        mask &= df["candidate_class_recal"].isin(["A", "B"])

    df_good = df[mask].copy()

    if len(df_good) == 0:
        print("HATA: Uygun GOOD aday bulunamadi")
        return 1

    sort_cols = [c for c in ["total_score", "snr_adopted"] if c in df_good.columns]
    df_good = df_good.sort_values(sort_cols, ascending=False).head(10)

    print("=" * 70)
    print("Top 10 GOOD Aday Icin Gorsel Uretimi")
    print("=" * 70)
    print(df_good[["source_id", "sector", "period", "candidate_class_recal", "scientific_status"]].to_string(index=False))
    print()

    # Ayri output klasoru
    settings = load_settings(project_root / "configs" / "default.toml")
    settings.general.output_dir = "outputs_top10"
    settings.outputs.save_figures = True

    output_manager = OutputManager(settings=settings)
    pipeline = TESSPipeline(
        settings=settings,
        output_manager=output_manager,
        force_map=True,
        skip_visualization=False,
        skip_catalog=False,
    )

    results = []

    try:
        for i, row in df_good.iterrows():
            target = row["source_id"]
            sector = int(row["sector"])

            print(f"[{len(results)+1}/{len(df_good)}] {target} S{sector}")
            try:
                r = pipeline.run_target(target, sectors=[sector])
                results.append(r)
                print(f"  OK - sectors={r.sectors_processed}, confirmed={r.candidates_confirmed}")
            except Exception as e:
                print(f"  HATA: {e}")

    finally:
        pipeline.close()

    print()
    print("=" * 70)
    print("Tamamlandi")
    print("Cikti klasoru: outputs_top10")
    print("Gorseller: outputs_top10/figures")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())