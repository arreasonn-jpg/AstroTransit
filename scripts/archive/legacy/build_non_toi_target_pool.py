from pathlib import Path
import sys
import time

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def main():
    import pandas as pd
    import numpy as np

    print("=" * 72)
    print("  TOI Disi Kesif Havuzu Olusturma")
    print("=" * 72)

    benchmarks_dir = project_root / "benchmarks"
    benchmarks_dir.mkdir(parents=True, exist_ok=True)

    # ────────────────────────────────────────────
    # 1. TOI listesini yukle (bilinen hedefler)
    # ────────────────────────────────────────────
    toi_file = benchmarks_dir / "toi_catalog.csv"
    if not toi_file.exists():
        print("HATA: toi_catalog.csv yok")
        print("Once calistir: python scripts/download_toi_catalog.py")
        return 1

    toi_df = pd.read_csv(toi_file)
    toi_tic_ids = set(toi_df["tid"].dropna().astype(int).tolist())
    print(f"OK TOI katalogu yuklendi: {len(toi_tic_ids)} benzersiz TIC ID")

    # ────────────────────────────────────────────
    # 2. Bilinen gezegen katalogunu da disla
    # ────────────────────────────────────────────
    known_ids = set(toi_tic_ids)

    try:
        from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchive

        print("Bilinen gezegen katalogu indiriliyor...")
        confirmed = NasaExoplanetArchive.query_criteria(
            table="pscomppars",
            select="tic_id",
            where="disc_facility like '%TESS%'",
        )
        confirmed_df = confirmed.to_pandas()
        if "tic_id" in confirmed_df.columns:
            confirmed_tics = set(confirmed_df["tic_id"].dropna().astype(int).tolist())
            known_ids.update(confirmed_tics)
            print(f"OK Bilinen gezegenler eklendi: {len(confirmed_tics)} TIC ID")
    except Exception as e:
        print(f"UYARI: Bilinen gezegen katalogu alinamadi: {e}")
        print("Sadece TOI listesi ile devam ediliyor")

    print(f"Toplam dislanacak TIC ID: {len(known_ids)}")

    # ────────────────────────────────────────────
    # 3. TESS SPOC hedef listesini olustur
    # ────────────────────────────────────────────
    print()
    print("TESS SPOC hedef listesi olusturuluyor...")
    print("Secilen sektorler: 1-26 (birincil gorev)")
    print()

    import lightkurve as lk

    all_targets = []
    sectors_to_scan = list(range(1, 27))

    for sector in sectors_to_scan:
        print(f"  Sektor {sector:>2d}: ", end="", flush=True)
        try:
            search = lk.search_lightcurve(
                f"sector {sector}",
                mission="TESS",
                author="SPOC",
                exptime=120,
            )

            if search is None or len(search) == 0:
                print("sonuc yok")
                continue

            for row in search.table:
                target_name = str(row.get("target_name", ""))
                digits = "".join(ch for ch in target_name if ch.isdigit())
                if digits:
                    tic_id = int(digits)
                    if tic_id not in known_ids:
                        all_targets.append({
                            "tid": tic_id,
                            "sector": sector,
                        })

            print(f"{len(search)} sonuc")
            time.sleep(0.5)

        except Exception as e:
            print(f"hata: {e}")
            time.sleep(2)
            continue

    if not all_targets:
        print("HATA: Hicbir hedef bulunamadi")
        return 1

    df = pd.DataFrame(all_targets)
    df = df.drop_duplicates(subset="tid", keep="first")

    print(f"\nToplam TOI-disi benzersiz hedef: {len(df)}")

    # ────────────────────────────────────────────
    # 4. TIC katalogundan yildiz bilgilerini al
    # ────────────────────────────────────────────
    print("Yildiz bilgileri aliniyor (ilk 500 hedef)...")

    from astroquery.mast import Catalogs

    df_sample = df.head(500).copy()

    tmags = []
    teffs = []
    rads = []

    for i, row in df_sample.iterrows():
        tid = row["tid"]
        try:
            result = Catalogs.query_object(
                f"TIC {tid}", catalog="TIC", radius=0.001
            )
            if result is not None and len(result) > 0:
                r = result[0]
                tmag = float(r.get("Tmag", np.nan))
                teff = float(r.get("Teff", np.nan))
                rad = float(r.get("rad", np.nan))
                tmags.append(tmag)
                teffs.append(teff)
                rads.append(rad)
            else:
                tmags.append(np.nan)
                teffs.append(np.nan)
                rads.append(np.nan)
        except Exception:
            tmags.append(np.nan)
            teffs.append(np.nan)
            rads.append(np.nan)

        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(df_sample)} tamamlandi")
            time.sleep(1)

    df_sample["st_tmag"] = tmags
    df_sample["st_teff"] = teffs
    df_sample["st_rad"] = rads

    # ────────────────────────────────────────────
    # 5. Filtrele
    # ────────────────────────────────────────────
    print("\nFiltreleme...")
    initial = len(df_sample)

    df_filtered = df_sample.dropna(subset=["st_tmag", "st_teff"])
    df_filtered = df_filtered[df_filtered["st_tmag"] > 5.0]
    df_filtered = df_filtered[df_filtered["st_tmag"] < 11.0]
    df_filtered = df_filtered[df_filtered["st_teff"] > 3000]
    df_filtered = df_filtered[df_filtered["st_teff"] < 8000]

    df_filtered = df_filtered.sort_values("st_tmag")

    print(f"Filtreleme: {initial} -> {len(df_filtered)}")

    # ────────────────────────────────────────────
    # 6. Ilk 100-200 hedefi sec ve kaydet
    # ────────────────────────────────────────────
    N = min(200, len(df_filtered))
    df_final = df_filtered.head(N).copy()

    output_file = benchmarks_dir / "discovery_targets.csv"
    df_final.to_csv(output_file, index=False)

    print(f"\nKaydedildi: {output_file}")
    print(f"Toplam kesif hedefi: {len(df_final)}")

    if len(df_final) > 0:
        print(f"Tmag araligi: {df_final['st_tmag'].min():.2f} - {df_final['st_tmag'].max():.2f}")
        print(f"Teff araligi: {df_final['st_teff'].min():.0f} - {df_final['st_teff'].max():.0f}")

    print()
    print("=" * 72)
    print(f"  HAZIR - {len(df_final)} TOI-disi kesif hedefi")
    print("=" * 72)
    print()
    print("Sonraki adim:")
    print("  python scripts/run_discovery_pilot.py --limit 10")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())