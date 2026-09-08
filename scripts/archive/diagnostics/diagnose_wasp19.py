"""
WASP-19b icin dealiasing durumunu detayli teshis et.
"""

from pathlib import Path
import sys

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def main():
    from astrotransit.logging_config import setup_logging
    setup_logging(log_level="DEBUG")

    from astrotransit.settings import get_settings
    from astrotransit.data.tess_client import TESSClient
    from astrotransit.preprocessing.pipeline import TESSPreprocessingPipeline
    from astrotransit.detection.bls_search import BLSSearch
    from astrotransit.detection.tls_search import TLSSearch
    from astrotransit.detection.thresholds import CascadeThresholds

    print("=" * 70)
    print("  WASP-19b Dealiasing Teshis")
    print("=" * 70)

    settings = get_settings()

    # Light curve indir
    client = TESSClient(author="SPOC", exptime=120, use_cache=True)
    print("\n[1] Light curve indiriliyor...")
    lc = client.get_lightcurve("TIC 142090065", sector=19)

    # Ön işleme
    print("[2] On isleme...")
    preproc = TESSPreprocessingPipeline(settings=settings)
    result = preproc.run(lc)
    detrended = result.detrended
    print(f"    {detrended.n_points} nokta, gurultu {detrended.noise_ppm:.0f} ppm")

    # BLS ara
    print("[3] BLS arama...")
    thresholds = CascadeThresholds.from_settings(settings)
    bls = BLSSearch(thresholds=thresholds.bls)
    bls_result = bls.search(detrended)

    if bls_result.best is None:
        print("    BLS aday bulamadi!")
        return 1

    print(f"    BLS bulunan: P={bls_result.best.period:.4f}d")

    # TLS multimode
    print("[4] TLS multimode...")
    tls = TLSSearch(thresholds=thresholds.tls)
    tls_result, adjusted_peak = tls.validate_multimode(
        detrended,
        bls_result.best,
        stellar_radius=1.31,
        stellar_mass=0.97,
    )

    if tls_result is None:
        print("    TLS sonuc yok!")
        return 1

    print("\n[5] Multimode sonuc:")
    print(f"    Bulunan P: {tls_result.period:.5f}d")
    print("    Gercek P:  0.78884d")
    print(f"    SDE: {tls_result.sde:.2f}")
    print(f"    Duration: {tls_result.duration:.4f}d")
    print(f"    dp_ratio: {tls_result.duration/tls_result.period:.4f}")

    # ManuALly dealiasing test
    print("\n[6] DEALIASING TESTI (manuel):")
    dealiased = tls._dealias_period(
        tls_result, detrended, 1.31, 0.97
    )

    if dealiased is None:
        print("    Dealiasing HICBIR sey donmedi (return None)")
        print("    Sebep detayi loglarda")
    else:
        print(f"    Dealiasing SONUC: P={dealiased.period:.5f}d, SDE={dealiased.sde:.2f}")

        real_p = 0.78884
        err_pct = abs(dealiased.period - real_p) / real_p * 100
        print(f"    Gercek P ile hata: %{err_pct:.2f}")

        if err_pct < 5:
            print("    ✓ DEALIASING BASARILI!")
        else:
            print("    ✗ Dealiasing yanlis yone gitti")

    return 0


if __name__ == "__main__":
    sys.exit(main())