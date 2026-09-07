from pathlib import Path
import sys
import pandas as pd
import numpy as np

project_root = Path(__file__).resolve().parents[2]


def normalize_source_id_to_tid(source_id: str):
    if not isinstance(source_id, str):
        return None
    source_id = source_id.strip().upper().replace("TIC", "").strip()
    digits = "".join(ch for ch in source_id if ch.isdigit())
    return int(digits) if digits else None


def classify_match(period_err_pct, radius_err_pct):
    if period_err_pct is None and radius_err_pct is None:
        return "NO_REFERENCE"
    if period_err_pct is None:
        return "RADIUS_ONLY"
    if radius_err_pct is None:
        return "PERIOD_ONLY"

    good_period = period_err_pct <= 5.0
    good_radius = radius_err_pct <= 30.0

    if good_period and good_radius:
        return "GOOD"
    if (not good_period) and good_radius:
        return "PERIOD_OFF"
    if good_period and (not good_radius):
        return "RADIUS_OFF"
    return "BOTH_OFF"


def fmt_num(val, fmt=".2f"):
    if val is None:
        return "NA"
    try:
        if pd.isna(val):
            return "NA"
    except Exception:
        pass
    return format(float(val), fmt)


def main():
    dedup_path = project_root / "outputs" / "parquet" / "astrotransit_candidates_dedup.parquet"
    raw_path = project_root / "outputs" / "parquet" / "astrotransit_candidates.parquet"
    pilot_path = project_root / "benchmarks" / "pilot_targets.csv"

    if dedup_path.exists():
        candidates_path = dedup_path
    elif raw_path.exists():
        candidates_path = raw_path
    else:
        print("HATA: aday parquet dosyasi yok")
        return 1

    if not pilot_path.exists():
        print("HATA: pilot_targets.csv yok")
        return 1

    df = pd.read_parquet(candidates_path)
    pilot = pd.read_csv(pilot_path)

    df = df.copy()
    df["tid"] = df["source_id"].apply(normalize_source_id_to_tid)

    if "tid" not in pilot.columns:
        print("HATA: pilot_targets.csv icinde tid kolonu yok")
        return 1

    merged = df.merge(
        pilot,
        on="tid",
        how="left",
        suffixes=("", "_ref"),
    )

    period_ref_col = "pl_orbper" if "pl_orbper" in merged.columns else None
    radius_ref_col = "pl_rade" if "pl_rade" in merged.columns else None
    toi_col = "toi" if "toi" in merged.columns else None

    period_errs = []
    radius_errs = []
    classes = []

    for _, row in merged.iterrows():
        p_found = row["period"] if "period" in row and pd.notna(row["period"]) else None
        p_ref = row[period_ref_col] if period_ref_col and pd.notna(row[period_ref_col]) else None

        if p_found is not None and p_ref is not None and p_ref > 0:
            period_err_pct = abs(p_found - p_ref) / p_ref * 100.0
        else:
            period_err_pct = None

        r_found = row["planet_radius_rearth"] if "planet_radius_rearth" in row and pd.notna(row["planet_radius_rearth"]) else None
        r_ref = row[radius_ref_col] if radius_ref_col and pd.notna(row[radius_ref_col]) else None

        if r_found is not None and r_ref is not None and r_ref > 0:
            radius_err_pct = abs(r_found - r_ref) / r_ref * 100.0
        else:
            radius_err_pct = None

        period_errs.append(period_err_pct)
        radius_errs.append(radius_err_pct)
        classes.append(classify_match(period_err_pct, radius_err_pct))

    merged["period_error_pct_ref"] = period_errs
    merged["radius_error_pct_ref"] = radius_errs
    merged["reference_match"] = classes

    sort_cols = [c for c in ["total_score", "snr_adopted"] if c in merged.columns]
    merged = merged.sort_values(sort_cols, ascending=False)

    out_csv = project_root / "outputs" / "csv" / "top_candidates_analysis.csv"
    out_md = project_root / "outputs" / "reports" / "top_candidates_analysis.md"

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    merged.to_csv(out_csv, index=False)

    topn = merged.head(20).copy()

    md_lines = []
    md_lines.append("# AstroTransit Top Aday Analizi\n")
    md_lines.append(f"- Toplam aday: **{len(merged)}**\n")
    md_lines.append(f"- Kaynak dosya: `{candidates_path.name}`\n")
    md_lines.append("")
    md_lines.append("## İlk 20 Aday\n")
    md_lines.append("| source_id | TOI | sector | found_period | ref_period | period_err_% | found_radius | ref_radius | radius_err_% | class | score | match |")
    md_lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|")

    for _, row in topn.iterrows():
        source_id = row.get("source_id", "")
        toi_val = row.get(toi_col, "") if toi_col else ""
        sector_val = row.get("sector", "")
        found_period = fmt_num(row.get("period", None), ".5f")
        ref_period = fmt_num(row.get(period_ref_col, None), ".5f") if period_ref_col else "NA"
        period_err = fmt_num(row.get("period_error_pct_ref", None), ".2f")
        found_radius = fmt_num(row.get("planet_radius_rearth", None), ".2f")
        ref_radius = fmt_num(row.get(radius_ref_col, None), ".2f") if radius_ref_col else "NA"
        radius_err = fmt_num(row.get("radius_error_pct_ref", None), ".2f")
        cand_class = row.get("candidate_class", "")
        total_score = fmt_num(row.get("total_score", None), ".1f")
        ref_match = row.get("reference_match", "")

        md_lines.append(
            f"| {source_id} | {toi_val} | {sector_val} | {found_period} | {ref_period} | "
            f"{period_err} | {found_radius} | {ref_radius} | {radius_err} | "
            f"{cand_class} | {total_score} | {ref_match} |"
        )

    out_md.write_text("\n".join(md_lines), encoding="utf-8")

    print("=" * 70)
    print("Top Aday Analizi")
    print("=" * 70)
    print(f"Toplam aday: {len(merged)}")
    print()
    print("Reference match dagilimi:")
    print(merged["reference_match"].value_counts(dropna=False))
    print()

    cols = [
        "source_id",
        "sector",
        "period",
        "planet_radius_rearth",
        "candidate_class",
        "total_score",
        "period_error_pct_ref",
        "radius_error_pct_ref",
        "reference_match",
    ]
    cols = [c for c in cols if c in merged.columns]

    print("Top 10:")
    print(merged[cols].head(10).to_string(index=False))
    print()
    print(f"CSV rapor: {out_csv}")
    print(f"Markdown rapor: {out_md}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())