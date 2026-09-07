from pathlib import Path
import sys
import pandas as pd

project_root = Path(__file__).resolve().parents[2]


def main():
    parquet_path = project_root / "outputs" / "parquet" / "astrotransit_candidates.parquet"
    out_path = project_root / "outputs" / "parquet" / "astrotransit_candidates_dedup.parquet"
    csv_out = project_root / "outputs" / "csv" / "astrotransit_candidates_dedup.csv"

    if not parquet_path.exists():
        print(f"HATA: {parquet_path} bulunamadi")
        return 1

    df = pd.read_parquet(parquet_path)

    print("=" * 60)
    print("Duplikasyon Temizleme")
    print("=" * 60)
    print(f"Toplam satir: {len(df)}")
    print(f"Benzersiz source_id: {df['source_id'].nunique()}")

    # Eksik kolonlara karsi koruma
    if "cascade_confirmed" not in df.columns:
        df["cascade_confirmed"] = False
    if "total_score" not in df.columns:
        df["total_score"] = 0.0
    if "snr_adopted" not in df.columns:
        df["snr_adopted"] = 0.0

    # Siralama: confirmed önce, sonra score, sonra snr
    df_sorted = df.sort_values(
        by=["source_id", "cascade_confirmed", "total_score", "snr_adopted"],
        ascending=[True, False, False, False],
    )

    # source_id bazlı ilk kaydı al
    df_dedup = df_sorted.drop_duplicates(subset="source_id", keep="first").copy()

    # kaç tane tekrar vardı?
    dup_counts = df.groupby("source_id").size().reset_index(name="duplicate_count")
    df_dedup = df_dedup.merge(dup_counts, on="source_id", how="left")

    print(f"Temizlenmis satir: {len(df_dedup)}")
    print(f"Silinen tekrar kayit: {len(df) - len(df_dedup)}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    csv_out.parent.mkdir(parents=True, exist_ok=True)

    df_dedup.to_parquet(out_path, index=False)
    df_dedup.to_csv(csv_out, index=False)

    print()
    print(f"Parquet yazildi: {out_path}")
    print(f"CSV yazildi: {csv_out}")
    print("=" * 60)

    print("\nSinif dagilimi (dedup):")
    if "candidate_class" in df_dedup.columns:
        print(df_dedup["candidate_class"].value_counts(dropna=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())