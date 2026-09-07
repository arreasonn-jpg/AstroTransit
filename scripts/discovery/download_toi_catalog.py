"""
NASA Exoplanet Archive'dan TOI (TESS Objects of Interest)
katalogunu indirir.

Cikti: benchmarks/toi_catalog.csv
"""

from pathlib import Path
import sys
import time

project_root = Path(__file__).resolve().parents[2]


def main():
    print("=" * 60)
    print("  NASA Exoplanet Archive - TOI Katalog Indirici")
    print("=" * 60)

    try:
        from astroquery.ipac.nexsci.nasa_exoplanet_archive import (
            NasaExoplanetArchive
        )
        print("OK astroquery yuklendi")
    except ImportError:
        print("HATA: astroquery gerekli")
        print("Kurulum: pip install astroquery")
        return 1

    output_dir = project_root / "benchmarks"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "toi_catalog.csv"

    print(f"\n[1] TOI kataloğu indiriliyor (NASA Exoplanet Archive)...")
    print(f"    Bu ~30 saniye surer")

    t_start = time.time()

    try:
        # TOI tablosu - dogru sutun adlari
        # NOT: TOI tablosunda st_mass yok, sadece TIC ID uzerinden alinir
        toi_table = NasaExoplanetArchive.query_criteria(
            table="toi",
            select="toi,tid,tfopwg_disp,pl_orbper,pl_trandep,"
                   "pl_trandurh,pl_rade,st_teff,st_rad,"
                   "st_tmag,ra,dec",
        )

        elapsed = time.time() - t_start
        print(f"    OK {len(toi_table)} kayit indirildi ({elapsed:.1f}s)")

        # DataFrame'e cevir
        import pandas as pd
        df = toi_table.to_pandas()

        # st_mass icin yaklaşık deger olarak st_rad**1.2 formulu ekle
        # (Basit yaklaşım: ana sekans yildizlar icin M ~ R^1.2)
        if "st_rad" in df.columns:
            df["st_mass_est"] = df["st_rad"] ** 1.2
            print(f"    Yildiz kutlesi tahmini eklendi (M = R^1.2)")

        # Ozet istatistikler
        print(f"\n[2] Katalog istatistikleri:")
        print(f"    Toplam TOI: {len(df)}")

        if "tfopwg_disp" in df.columns:
            print(f"\n    TFOP WG Dispositions:")
            for disp, count in df["tfopwg_disp"].value_counts().head(10).items():
                print(f"      {disp}: {count}")

        # Parlaklik dagilimi
        if "st_tmag" in df.columns:
            tmag_valid = df["st_tmag"].dropna()
            if len(tmag_valid) > 0:
                print(f"\n    Tmag dagilimi:")
                print(f"      < 8:   {(tmag_valid < 8).sum()}")
                print(f"      8-10:  {((tmag_valid >= 8) & (tmag_valid < 10)).sum()}")
                print(f"      10-12: {((tmag_valid >= 10) & (tmag_valid < 12)).sum()}")
                print(f"      > 12:  {(tmag_valid >= 12).sum()}")

        # Kaydet
        df.to_csv(output_file, index=False)
        print(f"\n[3] Kaydedildi: {output_file}")
        print(f"    Boyut: {output_file.stat().st_size / 1024:.1f} KB")

        print()
        print("=" * 60)
        print(f"  BASARILI - {len(df)} TOI kaydi indirildi")
        print(f"  Dosya: {output_file}")
        print("=" * 60)
        print()
        print("Sonraki adim: Hedef filtreleme")
        print("  python scripts/discovery/build_non_toi_target_pool_v3.py")

        return 0

    except Exception as e:
        print(f"\nHATA: {e}")
        print("\nAlternatif yontem: Manuel indirme")
        print("  https://exoplanetarchive.ipac.caltech.edu/cgi-bin/TblView/nph-tblView?app=ExoTbls&config=TOI")
        return 1


if __name__ == "__main__":
    sys.exit(main())