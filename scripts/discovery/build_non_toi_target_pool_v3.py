from pathlib import Path
import sys
import time
import re
import random

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))


def normalize_tic_value(value):
    if value is None:
        return None
    s = str(value).strip().upper()
    digits = re.sub(r"\D", "", s)
    if not digits:
        return None
    try:
        return int(digits)
    except Exception:
        return None


def main():
    print("=" * 72)
    print("  TOI Disi Kesif Havuzu Olusturma v3")
    print("=" * 72)

    import pandas as pd
    import numpy as np
    from astroquery.mast import Catalogs
    import lightkurve as lk

    benchmarks_dir = project_root / "benchmarks"
    benchmarks_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------
    # 1. TOI katalogu yukle
    # ------------------------------------------------------------
    toi_file = benchmarks_dir / "toi_catalog.csv"
    if not toi_file.exists():
        print("HATA: toi_catalog.csv yok")
        print("Once calistir: python scripts/discovery/download_toi_catalog.py")
        return 1

    toi_df = pd.read_csv(toi_file)
    toi_tic_ids = set(
        tid for tid in (normalize_tic_value(v) for v in toi_df["tid"].tolist())
        if tid is not None
    )
    print(f"OK TOI katalogu yuklendi: {len(toi_tic_ids)} TIC")

    # ------------------------------------------------------------
    # 2. Bilinen TESS gezegenlerini disla
    # ------------------------------------------------------------
    known_ids = set(toi_tic_ids)

    try:
        from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchive

        print("Bilinen TESS gezegenleri sorgulaniyor...")
        confirmed = NasaExoplanetArchive.query_criteria(
            table="pscomppars",
            select="tic_id, pl_name",
            where="disc_facility like '%TESS%'",
        )
        confirmed_df = confirmed.to_pandas()

        if "tic_id" in confirmed_df.columns:
            confirmed_tics = set(
                tid for tid in (normalize_tic_value(v) for v in confirmed_df["tic_id"].tolist())
                if tid is not None
            )
            known_ids.update(confirmed_tics)
            print(f"OK Bilinen TESS gezegenleri eklendi: {len(confirmed_tics)} TIC")
    except Exception as e:
        print(f"UYARI: Bilinen gezegen katalogu alinamadi: {e}")
        print("Sadece TOI dislama ile devam ediliyor")

    print(f"Toplam dislanacak TIC ID: {len(known_ids)}")

    # ------------------------------------------------------------
    # 3. TIC katalogundan parlak yildiz orneklemi al
    # ------------------------------------------------------------
    print()
    print("TIC katalogundan parlak yildiz havuzu aliniyor...")

    # Not: all-sky TIC query cok buyuk oldugu icin sayfali/limitli gidiyoruz
    # Burada ilk etapta birden fazla sayfa cekip aday havuz olusturuyoruz
    candidate_rows = []

    page_sizes = [2000, 2000, 2000]
    page_numbers = [1, 2, 3]

    for page_size, page_num in zip(page_sizes, page_numbers):
        print(f"  TIC page {page_num} indiriliyor...")
        try:
            tbl = Catalogs.query_criteria(
                catalog="TIC",
                Tmag=[5, 11],
                pagesize=page_size,
                page=page_num,
            )
            if tbl is None or len(tbl) == 0:
                print("    bos")
                continue

            df_page = tbl.to_pandas()

            # Beklenen kolonlar: ID, Tmag, Teff, rad, ra, dec
            keep_cols = [c for c in ["ID", "Tmag", "Teff", "rad", "ra", "dec"] if c in df_page.columns]
            df_page = df_page[keep_cols].copy()

            # Filtreler
            if "Teff" in df_page.columns:
                df_page = df_page[(df_page["Teff"] > 3000) & (df_page["Teff"] < 8000)]

            if "rad" in df_page.columns:
                df_page = df_page[(df_page["rad"] > 0.1) & (df_page["rad"] < 10)]

            # known_ids disla
            if "ID" in df_page.columns:
                df_page["tid"] = df_page["ID"].astype("Int64")
                df_page = df_page[~df_page["tid"].isin(list(known_ids))]

            candidate_rows.append(df_page)
            print(f"    kalan: {len(df_page)}")
            time.sleep(1)

        except Exception as e:
            print(f"    hata: {e}")
            time.sleep(2)
            continue

    if not candidate_rows:
        print("HATA: TIC katalogundan aday havuz olusturulamadi")
        return 1

    pool = pd.concat(candidate_rows, ignore_index=True)
    pool = pool.drop_duplicates(subset="tid", keep="first")

    print(f"\nTOI-disi TIC havuzu: {len(pool)} hedef")

    # ------------------------------------------------------------
    # 4. Rastgele/dengeleyici orneklem sec
    # ------------------------------------------------------------
    # Hep en parlaklara bakmamak icin ilk 1000 icinde karisik secelim
    pool = pool.sort_values("Tmag").reset_index(drop=True)
    top_pool = pool.head(min(1000, len(pool))).copy()

    # Karisik secim
    rng = random.Random(42)
    idxs = list(top_pool.index)
    rng.shuffle(idxs)
    top_pool = top_pool.loc[idxs].reset_index(drop=True)

    # ------------------------------------------------------------
    # 5. TESS SPOC 120s var mi kontrol et
    # ------------------------------------------------------------
    print()
    print("TESS SPOC 120s dogrulamasi yapiliyor...")
    print("Bu adim zaman alabilir...")

    verified = []
    target_goal = 200

    for i, row in top_pool.iterrows():
        if len(verified) >= target_goal:
            break

        tid = int(row["tid"])
        tic_id = f"TIC {tid}"

        try:
            search = lk.search_lightcurve(
                tic_id,
                mission="TESS",
                author="SPOC",
                exptime=120,
            )

            if search is None or len(search) == 0:
                continue

            # ilk bulunan sektoru sec
            found_sector = None
            for r in search.table:
                mission = str(r.get("mission", ""))
                if "Sector" in mission:
                    try:
                        found_sector = int(mission.split("Sector")[-1].strip())
                        break
                    except Exception:
                        continue

            if found_sector is None:
                continue

            verified.append({
                "tid": tid,
                "source_id": tic_id,
                "sector": found_sector,
                "st_tmag": float(row["Tmag"]) if "Tmag" in row and pd.notna(row["Tmag"]) else np.nan,
                "st_teff": float(row["Teff"]) if "Teff" in row and pd.notna(row["Teff"]) else np.nan,
                "st_rad": float(row["rad"]) if "rad" in row and pd.notna(row["rad"]) else np.nan,
                "ra": float(row["ra"]) if "ra" in row and pd.notna(row["ra"]) else np.nan,
                "dec": float(row["dec"]) if "dec" in row and pd.notna(row["dec"]) else np.nan,
            })

        except Exception:
            continue

        if (i + 1) % 25 == 0:
            print(f"  kontrol: {i + 1} / {len(top_pool)} | dogrulanan: {len(verified)}")
            time.sleep(0.2)

    if not verified:
        print("HATA: Dogrulanmis TOI-disi hedef bulunamadi")
        return 1

    df_final = pd.DataFrame(verified)
    df_final = df_final.drop_duplicates(subset="tid", keep="first")
    df_final = df_final.sort_values("st_tmag")

    output_file = benchmarks_dir / "discovery_targets.csv"
    df_final.to_csv(output_file, index=False)

    print()
    print(f"Kaydedildi: {output_file}")
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
    print("  python scripts/discovery/run_discovery_pilot_v2.py --limit 10 --no-viz")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())