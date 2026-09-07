from pathlib import Path
import sys
import pandas as pd
import numpy as np

project_root = Path(__file__).resolve().parents[2]


def classify_discovery_row(row):
    period = row.get("period", np.nan)
    depth_ppm = row.get("depth_ppm", np.nan)
    radius = row.get("planet_radius_rearth", np.nan)
    snr = row.get("snr_adopted", np.nan)
    cand_class = str(row.get("candidate_class", ""))

    # Bozuk kayıt
    if pd.isna(period) or period <= 0:
        return "REJECT", "invalid period"

    if pd.isna(depth_ppm) or depth_ppm <= 0:
        return "REJECT", "invalid depth"

    if pd.isna(radius) or radius <= 0:
        return "REJECT", "invalid radius"

    # Muhtemel false positive
    if radius > 20:
        return "REJECT", "radius too large"

    if depth_ppm > 10000:
        return "REJECT", "depth too large"

    # Güçlü follow-up adayları
    if cand_class == "A" and snr >= 10 and 0.5 <= radius <= 6.0 and depth_ppm <= 3000:
        return "FOLLOWUP", "strong candidate"

    # Orta kalite - saklanabilir
    if cand_class in ("B", "C") and snr >= 5 and 0.5 <= radius <= 8.0 and depth_ppm <= 5000:
        return "WATCHLIST", "moderate candidate"

    return "REJECT", "low quality or likely false positive"


def main():
    in_path = project_root / "outputs_discovery" / "novel_candidates.parquet"
    if not in_path.exists():
        print(f"HATA: {in_path} bulunamadi")
        print("Once calistir: python scripts/discovery/classify_novelty.py")
        return 1

    df = pd.read_parquet(in_path)

    labels = []
    reasons = []

    for _, row in df.iterrows():
        label, reason = classify_discovery_row(row)
        labels.append(label)
        reasons.append(reason)

    df["discovery_priority"] = labels
    df["discovery_reason"] = reasons

    out_dir = project_root / "outputs_discovery"
    out_dir.mkdir(parents=True, exist_ok=True)

    full_csv = out_dir / "novel_candidates_prioritized.csv"
    full_parquet = out_dir / "novel_candidates_prioritized.parquet"

    df.to_csv(full_csv, index=False)
    df.to_parquet(full_parquet, index=False)

    print("=" * 72)
    print("Discovery Candidate Prioritization")
    print("=" * 72)
    print(df["discovery_priority"].value_counts(dropna=False))
    print()

    cols = [c for c in [
        "source_id", "sector", "period", "depth_ppm",
        "planet_radius_rearth", "snr_adopted",
        "candidate_class", "total_score",
        "discovery_priority", "discovery_reason"
    ] if c in df.columns]

    print(df[cols].sort_values(
        by=["discovery_priority", "snr_adopted"],
        ascending=[True, False]
    ).to_string(index=False))

    print()
    print(f"CSV: {full_csv}")
    print(f"Parquet: {full_parquet}")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())