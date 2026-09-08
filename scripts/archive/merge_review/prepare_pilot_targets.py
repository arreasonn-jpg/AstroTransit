"""
TOI katalogundan pilot tarama icin 100 hedef secer.

Kriterler:
- Tmag < 11 (parlak, iyi kalite)
- TFOPWG dispositoin: PC, KP, CP, APC
- P orbital < 15 gun
- Rp < 15 R_earth
"""

from pathlib import Path
import sys

project_root = Path(__file__).resolve().parent.parent


def main():
    print("=" * 60)
    print("  Pilot Hedef Hazirlama (100 TOI)")
    print("=" * 60)

    import pandas as pd

    toi_file = project_root / "benchmarks" / "toi_catalog.csv"

    if not toi_file.exists():
        print(f"HATA: {toi_file} yok")
        print("Once calistir: python scripts/download_toi_catalog.py")
        return 1

    df = pd.read_csv(toi_file)
    print(f"OK TOI katalogu yuklendi: {len(df)} kayit")

    # Filtreler
    print("\n[1] Filtreleme uygulaniyor...")

    initial = len(df)

    # 1. TFOPWG dispositoin
    good_dispositions = ["PC", "KP", "CP", "APC"]
    if "tfopwg_disp" in df.columns:
        df = df[df["tfopwg_disp"].isin(good_dispositions)]
        print(f"   TFOP disposition (PC/KP/CP/APC): {initial} -> {len(df)}")

    # 2. Parlaklik
    if "st_tmag" in df.columns:
        df = df[df["st_tmag"] < 11.0]
        df = df[df["st_tmag"] > 5.0]  # cok parlak degil (saturation)
        print(f"   5 < Tmag < 11: -> {len(df)}")

    # 3. Periyot
    if "pl_orbper" in df.columns:
        df = df[df["pl_orbper"] > 0.5]
        df = df[df["pl_orbper"] < 15.0]
        print(f"   0.5 < P < 15 gun: -> {len(df)}")

    # 4. Gezegen yaricapi
    if "pl_rade" in df.columns:
        df = df[df["pl_rade"] > 0.5]
        df = df[df["pl_rade"] < 15.0]
        print(f"   0.5 < Rp < 15 R_earth: -> {len(df)}")

    # 5. NaN yildiz parametreleri temizle (st_mass yok, st_rad yeter)
    required_cols = ["st_teff", "st_rad", "tid"]
    for col in required_cols:
        if col in df.columns:
            df = df.dropna(subset=[col])
    print(f"   Yildiz parametreleri var: -> {len(df)}")

    # Parlaklığa göre sırala
    if "st_tmag" in df.columns:
        df = df.sort_values("st_tmag")

    N_TARGETS = 100
    df_pilot = df.head(N_TARGETS).copy()

    print(f"\n[2] Ilk {N_TARGETS} hedef secildi")

    pilot_file = project_root / "benchmarks" / "pilot_targets.csv"
    df_pilot.to_csv(pilot_file, index=False)
    print(f"\n[3] Kaydedildi: {pilot_file}")

    # Ozet
    print("\n[4] Pilot hedef ozeti:")
    print(f"    Toplam: {len(df_pilot)}")

    if "st_tmag" in df_pilot.columns:
        print(f"    Tmag: {df_pilot['st_tmag'].min():.2f} - "
              f"{df_pilot['st_tmag'].max():.2f}")

    if "pl_orbper" in df_pilot.columns:
        print(f"    Periyot: {df_pilot['pl_orbper'].min():.2f} - "
              f"{df_pilot['pl_orbper'].max():.2f} gun")

    if "pl_rade" in df_pilot.columns:
        print(f"    Rp: {df_pilot['pl_rade'].min():.2f} - "
              f"{df_pilot['pl_rade'].max():.2f} R_earth")

    if "tfopwg_disp" in df_pilot.columns:
        print("\n    Disposition dagilimi:")
        for disp, count in df_pilot["tfopwg_disp"].value_counts().items():
            print(f"      {disp}: {count}")

    print()
    print("=" * 60)
    print(f"  HAZIR - {len(df_pilot)} pilot hedef")
    print("=" * 60)
    print()
    print("Sonraki adim: Tam tarama baslat")
    print("  python scripts/run_full_scan.py --pilot --limit 5 --no-viz")

    return 0


if __name__ == "__main__":
    sys.exit(main())