from pathlib import Path
import sys

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))


def main():
    import pandas as pd

    print("=" * 72)
    print("  Kesif Sonuclari Yenilik Siniflandirmasi")
    print("=" * 72)

    discovery_parquet = project_root / "outputs_discovery" / "parquet" / "astrotransit_candidates.parquet"
    if not discovery_parquet.exists():
        print(f"HATA: {discovery_parquet} yok")
        print("Once calistir: python scripts/discovery/run_discovery_pilot_v2.py")
        return 1

    df = pd.read_parquet(discovery_parquet)
    print(f"OK {len(df)} aday yuklendi")

    # TOI listesini yukle
    toi_file = project_root / "benchmarks" / "toi_catalog.csv"
    toi_tics = set()
    if toi_file.exists():
        toi_df = pd.read_csv(toi_file)
        toi_tics = set(toi_df["tid"].dropna().astype(int).tolist())
        print(f"OK TOI katalogu: {len(toi_tics)} TIC ID")

    # TIC numarasi cikar
    def extract_tic(source_id):
        if not isinstance(source_id, str):
            return None
        digits = "".join(ch for ch in source_id if ch.isdigit())
        return int(digits) if digits else None

    df["tid"] = df["source_id"].apply(extract_tic)

    # Siniflandir
    novelty = []
    for _, row in df.iterrows():
        tid = row.get("tid", None)
        if tid is None:
            novelty.append("UNKNOWN")
        elif tid in toi_tics:
            novelty.append("KNOWN_TOI")
        else:
            novelty.append("NOVEL_CANDIDATE")

    df["novelty_status"] = novelty

    # Sonuc
    print()
    print("Yenilik dagilimi:")
    print(df["novelty_status"].value_counts(dropna=False))
    print()

    novel = df[df["novelty_status"] == "NOVEL_CANDIDATE"].copy()

    if len(novel) > 0:
        sort_cols = [c for c in ["total_score", "snr_adopted"] if c in novel.columns]
        novel = novel.sort_values(sort_cols, ascending=False)

        print(f"YENI ADAYLAR: {len(novel)}")
        print()

        cols = [c for c in [
            "source_id", "sector", "period", "depth_ppm",
            "planet_radius_rearth", "snr_adopted",
            "candidate_class", "total_score", "novelty_status",
        ] if c in novel.columns]

        print(novel[cols].head(20).to_string(index=False))
        print()

        # Kaydet
        out_csv = project_root / "outputs_discovery" / "novel_candidates.csv"
        novel.to_csv(out_csv, index=False)
        print(f"Yeni adaylar CSV: {out_csv}")

        out_parquet = project_root / "outputs_discovery" / "novel_candidates.parquet"
        novel.to_parquet(out_parquet, index=False)
        print(f"Yeni adaylar Parquet: {out_parquet}")
    else:
        print("Hicbir yeni aday bulunamadi.")
        print("Bu normal - ilk pilotta olasilik dusuktur.")
        print("Daha fazla hedefle tekrar deneyin.")

    # Tam sonucu da kaydet
    out_full = project_root / "outputs_discovery" / "discovery_classified.parquet"
    df.to_parquet(out_full, index=False)
    print(f"\nTum sonuclar: {out_full}")

    print()
    print("=" * 72)
    if len(novel) > 0:
        print(f"  {len(novel)} POTANSIYEL YENI GEZEGEN ADAYI BULUNDU")
    else:
        print("  Bu turda yeni aday bulunamadi")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())