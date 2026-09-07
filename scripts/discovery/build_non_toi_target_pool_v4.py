from pathlib import Path
import sys
import time
import re
import argparse

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


def parse_args():
    p = argparse.ArgumentParser(
        description="Build TOI-excluded discovery target pool with science-priority ranking."
    )
    p.add_argument("--mode", choices=["general", "small-cool", "ultra-cool"], default="small-cool")
    p.add_argument("--max-targets", type=int, default=200)
    p.add_argument("--page-count", type=int, default=6)
    p.add_argument("--page-size", type=int, default=2000)
    p.add_argument("--top-pool-size", type=int, default=1500)
    p.add_argument("--tmag-min", type=float, default=5.0)
    p.add_argument("--tmag-max", type=float, default=11.0)
    p.add_argument(
        "--output",
        type=str,
        default="benchmarks/discovery_targets_v4.csv",
        help="Output CSV path relative to project root or absolute path",
    )
    return p.parse_args()


def score_preverification(row, mode):
    score = 0.0

    tmag = row.get("Tmag")
    teff = row.get("Teff")
    rad = row.get("rad")

    if tmag is not None and not pd.isna(tmag):
        score += max(0.0, 12.0 - float(tmag)) * 4.0

    if teff is not None and not pd.isna(teff):
        teff = float(teff)
        if mode == "ultra-cool":
            score += max(0.0, 3800.0 - teff) / 50.0
        elif mode == "small-cool":
            score += max(0.0, 6200.0 - teff) / 120.0
        else:
            score += max(0.0, 7000.0 - teff) / 250.0

    if rad is not None and not pd.isna(rad):
        rad = float(rad)
        if mode == "ultra-cool":
            score += max(0.0, 0.52 - rad) * 20.0
        elif mode == "small-cool":
            score += max(0.0, 1.4 - rad) * 10.0
        else:
            score += max(0.0, 2.0 - rad) * 3.0

    return score


def apply_mode_filters(df, mode):
    if mode == "ultra-cool":
        if "Teff" in df.columns:
            df = df[(df["Teff"] >= 2500) & (df["Teff"] <= 3800)]
        if "rad" in df.columns:
            df = df[(df["rad"] >= 0.10) & (df["rad"] <= 0.52)]
    elif mode == "small-cool":
        if "Teff" in df.columns:
            df = df[(df["Teff"] >= 3800) & (df["Teff"] <= 6200)]
        if "rad" in df.columns:
            df = df[(df["rad"] > 0.35) & (df["rad"] <= 1.2)]
    else:
        if "Teff" in df.columns:
            df = df[(df["Teff"] > 3000) & (df["Teff"] < 8000)]
        if "rad" in df.columns:
            df = df[(df["rad"] > 0.1) & (df["rad"] < 10)]
    return df


def main():
    print("=" * 72)
    print("  TOI Disi Kesif Havuzu Olusturma v4")
    print("=" * 72)

    args = parse_args()

    import pandas as pd
    import numpy as np
    from astroquery.mast import Catalogs
    import lightkurve as lk

    benchmarks_dir = project_root / "benchmarks"
    benchmarks_dir.mkdir(parents=True, exist_ok=True)

    output_file = Path(args.output)
    if not output_file.is_absolute():
        output_file = project_root / output_file

    print(f"Mod             : {args.mode}")
    print(f"Maks hedef      : {args.max_targets}")
    print(f"Page count      : {args.page_count}")
    print(f"Page size       : {args.page_size}")
    print(f"Top pool size   : {args.top_pool_size}")
    print(f"Tmag araligi    : {args.tmag_min} - {args.tmag_max}")
    print(f"Cikti           : {output_file}")

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
    # 3. TIC katalogundan aday havuz cek
    # ------------------------------------------------------------
    print()
    print("TIC katalogundan aday havuz aliniyor...")

    candidate_rows = []

    for page_num in range(1, args.page_count + 1):
        print(f"  TIC page {page_num} indiriliyor...")
        try:
            tbl = Catalogs.query_criteria(
                catalog="TIC",
                Tmag=[args.tmag_min, args.tmag_max],
                pagesize=args.page_size,
                page=page_num,
            )
            if tbl is None or len(tbl) == 0:
                print("    bos")
                continue

            df_page = tbl.to_pandas()

            keep_cols = [c for c in ["ID", "Tmag", "Teff", "rad", "ra", "dec"] if c in df_page.columns]
            df_page = df_page[keep_cols].copy()

            if "ID" not in df_page.columns:
                print("    ID kolonu yok, geciliyor")
                continue

            df_page["tid"] = df_page["ID"].astype("Int64")

            # known TIC disla
            df_page = df_page[~df_page["tid"].isin(list(known_ids))]

            # mode-specific filtre
            df_page = apply_mode_filters(df_page, args.mode)

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

    if len(pool) == 0:
        print("HATA: Filtreler sonrasi havuz bos kaldi")
        return 1

    # preverification ranking
    pool["pre_priority_score"] = pool.apply(lambda r: score_preverification(r, args.mode), axis=1)

    # ön siralama
    pool = pool.sort_values(
        ["pre_priority_score", "Tmag", "Teff", "rad"],
        ascending=[False, True, True, True]
    ).reset_index(drop=True)

    top_pool = pool.head(min(args.top_pool_size, len(pool))).copy()

    print(f"\nTOI-disi aday havuz: {len(pool)} hedef")
    print(f"Dogrulama icin secilen top havuz: {len(top_pool)} hedef")

    # ------------------------------------------------------------
    # 4. TESS SPOC 120s dogrulama
    # ------------------------------------------------------------
    print()
    print("TESS SPOC 120s dogrulamasi yapiliyor...")
    print("Bu adim zaman alabilir...")

    verified = []

    for i, row in top_pool.iterrows():
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

            sectors = []
            for r in search.table:
                mission = str(r.get("mission", ""))
                if "Sector" in mission:
                    try:
                        sec = int(mission.split("Sector")[-1].strip())
                        sectors.append(sec)
                    except Exception:
                        continue

            sectors = sorted(set(sectors))
            if not sectors:
                continue

            sector_count = len(sectors)
            primary_sector = sectors[0]

            verified_priority_score = float(row["pre_priority_score"]) + sector_count * 8.0

            verified.append({
                "tid": tid,
                "source_id": tic_id,
                "sector": primary_sector,
                "sector_count": sector_count,
                "sector_list": ",".join(str(s) for s in sectors),
                "pool_priority_score": float(row["pre_priority_score"]),
                "verified_priority_score": verified_priority_score,
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

    df_final = df_final.sort_values(
        ["verified_priority_score", "sector_count", "st_rad", "st_teff", "st_tmag"],
        ascending=[False, False, True, True, True]
    ).reset_index(drop=True)

    df_final = df_final.head(min(args.max_targets, len(df_final))).copy()

    output_file.parent.mkdir(parents=True, exist_ok=True)
    df_final.to_csv(output_file, index=False)

    print()
    print(f"Kaydedildi: {output_file}")
    print(f"Toplam kesif hedefi: {len(df_final)}")

    if len(df_final) > 0:
        print(f"Tmag araligi     : {df_final['st_tmag'].min():.2f} - {df_final['st_tmag'].max():.2f}")
        print(f"Teff araligi     : {df_final['st_teff'].min():.0f} - {df_final['st_teff'].max():.0f}")
        print(f"Rstar araligi    : {df_final['st_rad'].min():.2f} - {df_final['st_rad'].max():.2f}")
        print(f"Sector count max : {df_final['sector_count'].max()}")
        print(f"Sector count med : {df_final['sector_count'].median():.1f}")

    print()
    print("=" * 72)
    print(f"  HAZIR - {len(df_final)} TOI-disi kesif hedefi ({args.mode})")
    print("=" * 72)
    print()
    print("Sonraki adim:")
    print("  python scripts/discovery/run_discovery_pilot_v2.py --limit 50 --no-viz")

    return 0


if __name__ == "__main__":
    import pandas as pd
    raise SystemExit(main())
