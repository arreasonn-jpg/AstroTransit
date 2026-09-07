from pathlib import Path
import sys
import pandas as pd
import numpy as np

project_root = Path(__file__).resolve().parent.parent


def main():
    recal_path = project_root / "outputs" / "parquet" / "astrotransit_candidates_recal.parquet"
    if not recal_path.exists():
        print(f"HATA: {recal_path} bulunamadi")
        print("Once calistir: python scripts/recalibrate_pilot_classes.py")
        return 1

    df = pd.read_parquet(recal_path)

    total = len(df)
    class_counts = df["candidate_class_recal"].value_counts(dropna=False) if "candidate_class_recal" in df.columns else pd.Series()
    sci_counts = df["scientific_status"].value_counts(dropna=False) if "scientific_status" in df.columns else pd.Series()

    good_df = df[df.get("scientific_status", pd.Series(index=df.index, dtype=str)) == "SCIENTIFICALLY_CORRECT"].copy()
    good_df = good_df.sort_values(
        [c for c in ["total_score", "snr_adopted"] if c in good_df.columns],
        ascending=False,
    )

    top5 = good_df.head(5)

    reports_dir = project_root / "outputs" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    linkedin_file = reports_dir / "linkedin_post_tr.txt"
    md_file = reports_dir / "pilot_summary.md"

    # LinkedIn metni
    lines = []
    lines.append("AstroTransit pilot taramasindan ilk sonuclar")
    lines.append("")
    lines.append("NASA TESS verileri uzerinde 100 hedeflik pilot taramayi tamamladim.")
    lines.append("")
    lines.append(f"- Islenen aday sayisi: {total}")
    if len(class_counts) > 0:
        lines.append(f"- Yeniden siniflandirma sonrasi A sinifi: {int(class_counts.get('A', 0))}")
        lines.append(f"- B sinifi: {int(class_counts.get('B', 0))}")
        lines.append(f"- C sinifi: {int(class_counts.get('C', 0))}")
        lines.append(f"- D sinifi: {int(class_counts.get('D', 0))}")
    if len(sci_counts) > 0:
        lines.append(f"- Bilimsel olarak dogru eslesmeler: {int(sci_counts.get('SCIENTIFICALLY_CORRECT', 0))}")
    lines.append("")
    lines.append("Pipeline ozellikleri:")
    lines.append("- TESS light curve indirme")
    lines.append("- Normalize + temizleme + detrending")
    lines.append("- BLS -> TLS transit arama")
    lines.append("- MAP fit ile parametre cikartimi")
    lines.append("- Otomatik kalite skorlama ve standardize katalog")
    lines.append("")
    lines.append("Top ornek adaylar:")
    for _, row in top5.iterrows():
        lines.append(
            f"- {row.get('source_id','?')} | P={row.get('period', np.nan):.5f} d | "
            f"Rp={row.get('planet_radius_rearth', np.nan):.2f} R_earth | "
            f"SNR={row.get('snr_adopted', np.nan):.2f}"
        )
    lines.append("")
    lines.append("Sonraki adimlar:")
    lines.append("- Top 10 aday icin detayli gorsel rapor")
    lines.append("- Skorlama sisteminin daha da iyilestirilmesi")
    lines.append("- Daha buyuk olcekli pilot taramalar")
    lines.append("")
    lines.append("#astronomy #exoplanet #tess #python #datascience #astrophysics")

    linkedin_file.write_text("\n".join(lines), encoding="utf-8")

    # Markdown rapor
    md = []
    md.append("# AstroTransit Pilot Tarama Ozeti\n")
    md.append(f"- Toplam aday: **{total}**\n")

    if len(class_counts) > 0:
        md.append("## Sinif Dagilimi\n")
        for cls, cnt in class_counts.items():
            md.append(f"- {cls}: **{cnt}**")
        md.append("")

    if len(sci_counts) > 0:
        md.append("## Bilimsel Durum\n")
        for cls, cnt in sci_counts.items():
            md.append(f"- {cls}: **{cnt}**")
        md.append("")

    md.append("## Top 5 GOOD Aday\n")
    md.append("| source_id | sector | period | radius_rearth | snr | score |")
    md.append("|---|---:|---:|---:|---:|---:|")
    for _, row in top5.iterrows():
        md.append(
            f"| {row.get('source_id','')} | {row.get('sector','')} | "
            f"{row.get('period', np.nan):.5f} | "
            f"{row.get('planet_radius_rearth', np.nan):.2f} | "
            f"{row.get('snr_adopted', np.nan):.2f} | "
            f"{row.get('total_score', np.nan):.1f} |"
        )

    md_file.write_text("\n".join(md), encoding="utf-8")

    print("=" * 70)
    print("Share Pack Hazirlandi")
    print("=" * 70)
    print(f"LinkedIn metni: {linkedin_file}")
    print(f"Markdown rapor: {md_file}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())