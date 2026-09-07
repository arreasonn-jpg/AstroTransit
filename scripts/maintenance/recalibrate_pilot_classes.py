from pathlib import Path
import sys
import pandas as pd
import numpy as np

project_root = Path(__file__).resolve().parents[2]


def safe_bool(v):
    if pd.isna(v):
        return False
    return bool(v)


def classify_row(row):
    """
    Pilot benchmark icin daha kati siniflandirma.

    reference_match kolonunu kullanir:
      GOOD        -> A/B
      RADIUS_OFF  -> C
      PERIOD_OFF  -> D
      BOTH_OFF    -> D
      NO_REFERENCE -> fallback rule
    """
    confirmed = safe_bool(row.get("cascade_confirmed", False))
    score = float(row.get("total_score", 0.0) or 0.0)
    snr = float(row.get("snr_adopted", 0.0) or 0.0)
    fpp = float(row.get("fpp", 1.0) or 1.0)
    radius = float(row.get("planet_radius_rearth", np.nan)) if not pd.isna(row.get("planet_radius_reearth", np.nan)) else row.get("planet_radius_rearth", np.nan)
    ref_match = str(row.get("reference_match", "NO_REFERENCE"))

    period_err = row.get("period_error_pct_ref", None)
    radius_err = row.get("radius_error_pct_ref", None)

    # Referans bazli karar
    if ref_match == "GOOD":
        if confirmed and score >= 90 and snr >= 15 and fpp <= 0.05:
            return "A"
        return "B"

    if ref_match == "RADIUS_OFF":
        # Periyot dogru ama fiziksel boyut kaymis
        return "C"

    if ref_match == "PERIOD_OFF":
        return "D"

    if ref_match == "BOTH_OFF":
        return "D"

    # Referans yoksa konservatif fallback
    if confirmed and score >= 92 and snr >= 20 and fpp <= 0.03:
        if pd.isna(radius) or (0.5 <= float(radius) <= 20.0):
            return "A"

    if confirmed and score >= 80 and snr >= 10 and fpp <= 0.10:
        if pd.isna(radius) or (0.5 <= float(radius) <= 25.0):
            return "B"

    if score >= 55:
        return "C"

    return "D"


def scientific_status(row):
    ref_match = str(row.get("reference_match", "NO_REFERENCE"))
    if ref_match == "GOOD":
        return "SCIENTIFICALLY_CORRECT"
    if ref_match in ("PERIOD_OFF", "RADIUS_OFF", "BOTH_OFF"):
        return "SCIENTIFICALLY_INCORRECT"
    return "UNKNOWN"


def main():
    dedup_path = project_root / "outputs" / "parquet" / "astrotransit_candidates_dedup.parquet"
    analysis_csv = project_root / "outputs" / "csv" / "top_candidates_analysis.csv"

    if not dedup_path.exists():
        print(f"HATA: {dedup_path} bulunamadi")
        return 1

    if not analysis_csv.exists():
        print(f"HATA: {analysis_csv} bulunamadi")
        print("Once calistir: python scripts/maintenance/analyze_top_candidates.py")
        return 1

    df = pd.read_parquet(dedup_path)
    analysis = pd.read_csv(analysis_csv)

    # analysis csv'sinde source_id + sector unique varsayiyoruz
    merge_cols = [c for c in ["source_id", "sector"] if c in df.columns and c in analysis.columns]
    if not merge_cols:
        print("HATA: merge icin source_id/sector kolonlari yok")
        return 1

    extra_cols = [
        c for c in [
            "period_error_pct_ref",
            "radius_error_pct_ref",
            "reference_match",
        ]
        if c in analysis.columns
    ]

    merged = df.merge(
        analysis[merge_cols + extra_cols].drop_duplicates(subset=merge_cols),
        on=merge_cols,
        how="left",
    )

    merged["candidate_class_recal"] = merged.apply(classify_row, axis=1)
    merged["scientific_status"] = merged.apply(scientific_status, axis=1)

    out_parquet = project_root / "outputs" / "parquet" / "astrotransit_candidates_recal.parquet"
    out_csv = project_root / "outputs" / "csv" / "astrotransit_candidates_recal.csv"

    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    merged.to_parquet(out_parquet, index=False)
    merged.to_csv(out_csv, index=False)

    print("=" * 70)
    print("Pilot Yeniden Siniflandirma")
    print("=" * 70)
    print(f"Toplam aday: {len(merged)}")
    print()
    print("Eski sinif dagilimi:")
    if "candidate_class" in merged.columns:
        print(merged["candidate_class"].value_counts(dropna=False))
    print()
    print("Yeni sinif dagilimi:")
    print(merged["candidate_class_recal"].value_counts(dropna=False))
    print()
    print("Bilimsel durum:")
    print(merged["scientific_status"].value_counts(dropna=False))
    print()
    print(f"Parquet: {out_parquet}")
    print(f"CSV:     {out_csv}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())