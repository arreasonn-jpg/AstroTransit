"""
WASP-19b icin BLS diverse peaks testi.
"""

from pathlib import Path
import sys

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def main():
    from astrotransit.logging_config import setup_logging
    setup_logging(log_level="INFO")

    from astrotransit.settings import get_settings
    from astrotransit.data.tess_client import TESSClient
    from astrotransit.preprocessing.pipeline import TESSPreprocessingPipeline
    from astrotransit.detection.bls_search import BLSSearch
    from astrotransit.detection.thresholds import CascadeThresholds

    print("=" * 70)
    print("  WASP-19b BLS Diverse Peaks Teshis")
    print("=" * 70)

    settings = get_settings()

    client = TESSClient(author="SPOC", exptime=120, use_cache=True)
    print("\n[1] Light curve...")
    lc = client.get_lightcurve("TIC 142090065", sector=19)

    print("[2] On isleme...")
    preproc = TESSPreprocessingPipeline(settings=settings)
    result = preproc.run(lc)
    detrended = result.detrended

    print("[3] BLS arama (diverse peaks aktif)...")
    thresholds = CascadeThresholds.from_settings(settings)

    bls = BLSSearch(thresholds=thresholds.bls, n_peaks=5)
    bls_result = bls.search(detrended)

    print(f"\n[4] BLS'in bulduğu {len(bls_result.all_peaks)} aday:\n")
    print(f"    {'#':>2}  {'P (gun)':>10}  {'Guc':>8}  {'Derinlik (ppm)':>15}  {'Not':<20}")
    print("    " + "─" * 65)

    real_p = 0.78884

    for i, peak in enumerate(bls_result.all_peaks, 1):
        note = ""
        rel_to_real = peak.period / real_p
        if 0.95 < rel_to_real < 1.05:
            note = "GERCEK P"
        elif 1.95 < rel_to_real < 2.05:
            note = "2P harmonik"
        elif 2.95 < rel_to_real < 3.05:
            note = "3P harmonik"
        elif 0.45 < rel_to_real < 0.55:
            note = "P/2 harmonik"

        print(f"    {i:>2}  {peak.period:>10.5f}  {peak.power:>8.2f}  "
              f"{peak.depth * 1e6:>15.0f}  {note:<20}")

    # Ozet
    print()
    if bls_result.best:
        print(f"    En iyi (secilen): P={bls_result.best.period:.5f}d")
        rel = bls_result.best.period / real_p
        if 0.95 < rel < 1.05:
            print("    ✓ Gercek periyot bulundu!")
        elif 1.95 < rel < 2.05:
            print("    ⚠ 2P harmonik bulundu (gercek: 0.78884d)")

    # Onemli soru: gercek periyot listede var mi?
    real_p_found = any(
        0.95 < peak.period / real_p < 1.05
        for peak in bls_result.all_peaks
    )
    print(f"\n    Gercek periyot (0.78884d) listede: {'EVET' if real_p_found else 'HAYIR'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())