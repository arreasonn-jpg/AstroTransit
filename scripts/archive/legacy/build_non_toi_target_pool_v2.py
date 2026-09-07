from pathlib import Path
import sys
import time
import re

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def normalize_tic_value(value):
    """
    TIC alanini güvenli biçimde sayıya çevirir.
    Ornekler:
      123456789 -> 123456789
      '123456789' -> 123456789
      'TIC 123456789' -> 123456789
    """
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
    print("  TOI Disi Kesif Havuzu Olusturma v2")
    print("=" * 72)

    import pandas as pd
    import numpy as np
    from astroquery.mast import Observations, Catalogs

    benchmarks_dir = project_root / "benchmarks"
    benchmarks_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------
    # 1. TOI katalogunu yukle
    # ------------------------------------------------------------
    toi_file = benchmarks_dir / "toi_catalog.csv"
    if not toi_file.exists():
        print("HATA: toi_catalog.csv yok")
        print("Once calistir: python scripts/download_toi_catalog.py")
        return 1

    toi_df = pd.read_csv(toi_file)

    if "tid" not in toi_df.columns:
        print("HATA: toi_catalog.csv icinde tid kolonu yok")
        return 1

    toi_tic_ids = set(
        tid for tid in (
            normalize_tic_value(v) for v in toi_df["tid"].tolist()
        )
        if tid is not None
    )

    print(f"OK TOI katalogu yuklendi: {len(toi_tic_ids)} benzersiz TIC ID")

    # ------------------------------------------------------------
    # 2. Bilinen gezegenleri de disla
    # ------------------------------------------------------------
    known_ids = set(toi_tic_ids)

    try:
        print("Bilinen TESS gezegenleri sorgulaniyor...")
        from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchive

        confirmed = NasaExoplanetArchive.query_criteria(
            table="pscomppars",
            select="tic_id, pl_name",
            where="disc_facility like '%TESS%'",
        )

        confirmed_df = confirmed.to_pandas()

        if "tic_id" in confirmed_df.columns:
            confirmed_tics = set(
                tid for tid in (
                    normalize_tic_value(v) for v in confirmed_df["tic_id"].tolist()
                )
                if tid is not None
            )
            known_ids.update(confirmed_tics)
            print(f"OK Bilinen TESS gezegenleri eklendi: {len(confirmed_tics)} TIC ID")

    except Exception as e:
        print(f"UYARI: Bilinen gezegen katalogu alinamadi: {e}")
        print("Sadece TOI listesi ile devam ediliyor")

    print(f"Toplam dislanacak TIC ID: {len(known_ids)}")

    # ------------------------------------------------------------
    # 3. MAST'tan sektor bazli TESS timeseries hedeflerini cek
    # ------------------------------------------------------------
    print()
    print("TESS SPOC hedef havuzu sorgulaniyor...")
    print("Kaynak: MAST Observations.query_criteria")
    print()

    sectors_to_scan = list(range(1, 27))
    all_targets = []

    for sector in sectors_to_scan:
        print(f"  Sektor {sector:>2d}: ", end="", flush=True)
        try:
            obs = Observations.query_criteria(
                obs_collection="TESS",
                dataproduct_type="timeseries",
                sequence_number=sector,
            )

            if obs is None or len(obs) == 0:
                print("sonuc yok")
                continue

            # SPOC ve light curve benzeri satirlari filtrelemeye calis
            count_before = len(obs)

            # Güvenli kolon kontrolü
            colnames = set(obs.colnames)

            mask = np.ones(len(obs), dtype=bool)

            if "target_name" in colnames:
                target_names = np.array([str(x) for x in obs["target_name"]])
                # TIC içerenler öncelik
                mask &= np.array(["TIC" in x.upper() for x in target_names])

            if "provenance_name" in colnames:
                prov = np.array([str(x).upper() for x in obs["provenance_name"]])
                # SPOC öncelikli
                spoc_mask = np.array(["SPOC" in x for x in prov])
                if spoc_mask.any():
                    mask &= spoc_mask

            filtered = obs[mask]

            # TIC ID çıkar
            added = 0
            for row in filtered:
                target_name = str(row["target_name"]) if "target_name" in colnames else ""
                tic_id = normalize_tic_value(target_name)

                if tic_id is None:
                    continue
                if tic_id in known_ids:
                    continue

                all_targets.append({
                    "tid": tic_id,
                    "sector": sector,
                })
                added += 1

            print(f"{count_before} sonuc -> {added} TOI-disi TIC")
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

    # ------------------------------------------------------------
    # 4. TIC katalog bilgileri cek (ilk 500 hedef)
    # ------------------------------------------------------------
    print("Yildiz bilgileri aliniyor (ilk 500 hedef)...")

    df_sample = df.head(500).copy()

    tmags = []
    teffs = []
    rads = []

    for i, row in df_sample.iterrows():
        tid = row["tid"]
        try:
            result = Catalogs.query_object(
                f"TIC {tid}",
                catalog="TIC",
                radius=0.001,
            )

            if result is not None and len(result) > 0:
                r = result[0]

                def safe_float(x):
                    try:
                        if x is None:
                            return np.nan
                        return float(x)
                    except Exception:
                        return np.nan

                tmag = safe_float(r["Tmag"]) if "Tmag" in result.colnames else np.nan
                teff = safe_float(r["Teff"]) if "Teff" in result.colnames else np.nan
                rad = safe_float(r["rad"]) if "rad" in result.colnames else np.nan

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

    # ------------------------------------------------------------
    # 5. Filtrele
    # ------------------------------------------------------------
    print("\nFiltreleme...")
    initial = len(df_sample)

    df_filtered = df_sample.dropna(subset=["st_tmag", "st_teff"])
    df_filtered = df_filtered[df_filtered["st_tmag"] > 5.0]
    df_filtered = df_filtered[df_filtered["st_tmag"] < 11.0]
    df_filtered = df_filtered[df_filtered["st_teff"] > 3000]
    df_filtered = df_filtered[df_filtered["st_teff"] < 8000]

    df_filtered = df_filtered.sort_values("st_tmag")

    print(f"Filtreleme: {initial} -> {len(df_filtered)}")

    # ------------------------------------------------------------
    # 6. Kaydet
    # ------------------------------------------------------------
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
    print("  python scripts/run_discovery_pilot.py --limit 10 --no-viz")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())