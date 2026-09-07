"""
AstroTransit ilk çalıştırma testi.

Kullanım:
    python scripts/run_first_test.py            # MAST'tan gerçek veri
    python scripts/run_first_test.py --offline  # Sentetik veri (internet yok)
"""

from __future__ import annotations

import sys
import time
import argparse
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


# ──────────────────────────────────────────────────────────────
# Sentetik test (internet gerekmez)
# ──────────────────────────────────────────────────────────────
def run_synthetic_test() -> bool:
    print("=" * 65)
    print("  AstroTransit — Sentetik Veri Testi (Çevrimdışı)")
    print("=" * 65)

    import numpy as np

    from astrotransit.logging_config import setup_logging
    from astrotransit.settings import get_settings

    setup_logging(log_level="WARNING")
    settings = get_settings()

    # ── 1. Sentetik transit verisi ──
    print("\n[1/4] Sentetik transit verisi oluşturuluyor...")

    TRUE_PERIOD   = 3.5          # gün
    TRUE_T0       = 1.0          # BTJD
    TRUE_DEPTH    = 0.01         # 1% transit
    TRUE_DURATION = 0.10         # gün

    rng = np.random.default_rng(42)
    n_points = 8000
    cadence  = 2.0 / 1440.0     # 2 dakika → gün

    time_arr    = np.arange(n_points, dtype=float) * cadence
    noise       = rng.normal(0, 200e-6, n_points)
    flux_arr    = np.ones(n_points) + noise
    flux_err    = np.full(n_points, 200e-6)

    # Kutu transit enjeksiyonu
    half_dur = TRUE_DURATION / 2.0
    for k in range(-5, int(time_arr[-1] / TRUE_PERIOD) + 5):
        t_c = TRUE_T0 + k * TRUE_PERIOD
        mask = np.abs(time_arr - t_c) < half_dur
        flux_arr[mask] -= TRUE_DEPTH

    print(f"  ✓ {n_points} nokta  |  P={TRUE_PERIOD}d  |  "
          f"derinlik={TRUE_DEPTH * 1e6:.0f}ppm  |  gürültü=200ppm")

    # ── 2. DetrendedLightCurve ──
    from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve

    detrended = DetrendedLightCurve(
        target_id="SYNTHETIC_001",
        sector=99,
        time=time_arr,
        flux=flux_arr,
        flux_err=flux_err,
        trend=np.ones(n_points),
        raw_flux=flux_arr.copy(),
        method="synthetic",
        window_length=0.5,
        break_tolerance=0.5,
    )

    # ── 3. Cascade tespiti ──
    print("\n[2/4] BLS → TLS cascade tespiti...")

    from astrotransit.detection.cascade import CascadeDetector, CascadeStatus

    cascade = CascadeDetector(settings=settings)

    t0 = time.time()
    candidate = cascade.detect(detrended)
    elapsed = time.time() - t0

    print(f"  Durum    : {candidate.status.value}")
    print(f"  Onaylı   : {candidate.confirmed}")
    print(f"  Süre     : {elapsed:.1f}s")

    period_err_pct = None
    if candidate.confirmed or candidate.has_candidate:
        p_found = candidate.period
        period_err_pct = abs(p_found - TRUE_PERIOD) / TRUE_PERIOD * 100
        print(f"  P (bulunan)  : {p_found:.5f} gün")
        print(f"  P (gerçek)   : {TRUE_PERIOD:.5f} gün")
        print(f"  Hata         : %{period_err_pct:.2f}")
        print(f"  Derinlik     : {candidate.depth * 1e6:.0f} ppm")
        print(f"  SNR          : {candidate.snr:.2f}")
        print(f"  SDE          : {candidate.sde:.2f}")

    # ── 4. Kalite değerlendirmesi ──
    print("\n[3/4] Kalite değerlendirmesi...")

    from astrotransit.quality.pipeline import QualityEvaluationPipeline

    quality_result = None
    try:
        qp = QualityEvaluationPipeline(settings=settings)
        quality_result = qp.evaluate(detrended, candidate)
        score = quality_result.score
        print(f"  Skor   : {score.total_score:.0f}/100")
        print(f"  Sınıf  : {score.candidate_class.value}")
        print(f"  FPP    : {quality_result.vetting.false_positive_probability:.3f}")
    except Exception as e:
        print(f"  ⚠ Kalite hatası: {e}")

    # ── 5. Sonuç ──
    print("\n[4/4] Sonuç")
    print("=" * 65)

    if candidate.confirmed:
        print("  ✓ Sentetik transit BAŞARIYLA TESPİT EDİLDİ ve ONAYLANDI")
        if period_err_pct is not None:
            status = "✓ DOĞRU" if period_err_pct < 5 else "⚠ SAPMA"
            print(f"  {status} Periyot hatası: %{period_err_pct:.3f}")
        if quality_result:
            print(f"  Kalite Sınıfı: {quality_result.score.candidate_class.value}")
        print()
        print("  Sistem çalışıyor. Gerçek veri için:")
        print("    python scripts/run_first_test.py")
    elif candidate.has_candidate:
        print(f"  ⚠ Aday bulundu ama cascade onaylamadı: {candidate.status.value}")
        print("  BLS veya TLS eşikleri gevşetilebilir (default.toml).")
    else:
        print("  ✗ Transit tespit edilemedi")
        print(f"  Durum: {candidate.status.value}")

    print("=" * 65)
    return candidate.confirmed or candidate.has_candidate


# ──────────────────────────────────────────────────────────────
# Gerçek TESS testi (internet gerekir)
# ──────────────────────────────────────────────────────────────
def run_real_test() -> bool:
    print("=" * 65)
    print("  AstroTransit — Gerçek TESS Verisi Testi")
    print("  Hedef: WASP-18b  (TIC 100100827, Sektör 2)")
    print("=" * 65)

    from astrotransit.logging_config import setup_logging
    from astrotransit.settings import get_settings

    setup_logging(log_level="INFO")
    settings = get_settings()

    TARGET = "TIC 100100827"
    SECTOR = 2

    t_start = time.time()

    # ── 1. Yıldız özellikleri ──
    print("\n[1/7] Yıldız özellikleri sorgulanıyor...")
    try:
        from astrotransit.data.catalog_client import CatalogClient
        cat = CatalogClient()
        stellar = cat.get_stellar_properties(TARGET)
        if stellar.is_valid():
            print(f"  ✓ Teff={stellar.teff:.0f}K  R={stellar.radius:.2f}Rs  "
                  f"M={stellar.mass:.2f}Ms  Tmag={stellar.tmag:.2f}")
        else:
            print("  ⚠ Yıldız parametreleri eksik, varsayılan kullanılacak.")
            stellar = None
    except Exception as e:
        print(f"  ⚠ Katalog hatası: {e}")
        stellar = None

    stellar_radius = stellar.radius if stellar and stellar.is_valid() else 1.3
    stellar_mass   = stellar.mass   if stellar and stellar.is_valid() else 1.3
    stellar_teff   = stellar.teff   if stellar and stellar.teff > 0   else 6400.0

    # ── 2. Light curve indirme ──
    print(f"\n[2/7] TESS light curve indiriliyor (Sektör {SECTOR})...")
    try:
        from astrotransit.data.tess_client import TESSClient, TESSNoDataError
        client = TESSClient(
            author=settings.tess.author,
            exptime=settings.tess.exptime,
            use_cache=settings.tess.use_cache,
        )
        lc_data = client.get_lightcurve(TARGET, sector=SECTOR)
        print(f"  ✓ {lc_data.n_points_clean} nokta  |  "
              f"sektör {lc_data.sector}  |  "
              f"tamlık %{lc_data.completeness * 100:.1f}")
    except TESSNoDataError as e:
        print(f"  ✗ Veri bulunamadı: {e}")
        print("  → Çevrimdışı test için: python scripts/run_first_test.py --offline")
        return False
    except Exception as e:
        print(f"  ✗ İndirme hatası: {e}")
        print("  → İnternet bağlantısını kontrol edin.")
        return False

    # ── 3. Ön işleme ──
    print("\n[3/7] Ön işleme (normalize → temizle → detrend)...")
    try:
        from astrotransit.preprocessing.pipeline import TESSPreprocessingPipeline
        preproc = TESSPreprocessingPipeline(settings=settings)
        preprocessed = preproc.run(lc_data)
        detrended = preprocessed.detrended
        print(f"  ✓ {detrended.n_points} nokta  |  "
              f"gürültü {detrended.noise_ppm:.0f} ppm  |  "
              f"yöntem: {detrended.method}")
    except Exception as e:
        print(f"  ✗ Ön işleme hatası: {e}")
        return False

    # ── 4. Transit tespiti ──
    print("\n[4/7] BLS → TLS cascade tespiti...")
    try:
        from astrotransit.detection.cascade import CascadeDetector
        cascade = CascadeDetector(
            settings=settings,
            stellar_radius=stellar_radius,
            stellar_mass=stellar_mass,
        )
        candidate = cascade.detect(detrended)
        print(f"  Durum  : {candidate.status.value}")
        print(f"  Onaylı : {candidate.confirmed}")
        if candidate.has_candidate:
            print(f"  P      : {candidate.period:.5f} gün")
            print(f"  Derinlik: {candidate.depth * 1e6:.0f} ppm")
            print(f"  SNR    : {candidate.snr:.2f}")
            print(f"  SDE    : {candidate.sde:.2f}")
    except Exception as e:
        print(f"  ✗ Tespit hatası: {e}")
        return False

    # ── 5. MAP fit ──
    fit_result = None
    if candidate.confirmed:
        print("\n[5/7] MAP fit yapılıyor...")
        try:
            from astrotransit.modeling.fitter import ModelingOrchestrator
            modeling = ModelingOrchestrator(
                settings=settings,
                stellar_radius=stellar_radius,
                stellar_mass=stellar_mass,
                stellar_teff=stellar_teff,
                force_map=True,
            )
            fit_result = modeling.fit(detrended, candidate)
            if fit_result.success:
                d = fit_result.derived
                print(f"  ✓ MAP fit başarılı")
                print(f"    P     = {fit_result.period:.6f} gün")
                print(f"    Rp/Rs = {fit_result.rp_rs:.5f}")
                print(f"    Rp    = {d.planet_radius_rearth:.2f} R⊕  "
                      f"/ {d.planet_radius_rjup:.3f} Rj")
                print(f"    a     = {d.semi_major_axis_au:.4f} AU")
                print(f"    Teq   = {d.equilibrium_temperature_k:.0f} K")
                print(f"    b     = {fit_result.impact_parameter:.3f}")
                print(f"    i     = {fit_result.inclination:.2f}°")
            else:
                print("  ⚠ MAP fit başarısız, devam ediliyor.")
        except Exception as e:
            print(f"  ⚠ MAP fit hatası: {e}")
    else:
        print("\n[5/7] Transit adayı yok, MAP fit atlanıyor.")

    # ── 6. Kalite ──
    quality_result = None
    print("\n[6/7] Kalite değerlendirmesi...")
    try:
        from astrotransit.quality.pipeline import QualityEvaluationPipeline
        qp = QualityEvaluationPipeline(settings=settings)
        quality_result = qp.evaluate(detrended, candidate, fit_result)
        score = quality_result.score
        vet   = quality_result.vetting
        print(f"  ✓ Skor    : {score.total_score:.0f}/100")
        print(f"    Sınıf   : {score.candidate_class.value}")
        print(f"    FPP     : {vet.false_positive_probability:.3f}")
        print(f"    Anomali : {score.is_anomalous}")
        print(f"    Vetting : ✓{vet.n_pass}  ⚠{vet.n_warn}  ✗{vet.n_fail}")
    except Exception as e:
        print(f"  ⚠ Kalite hatası: {e}")

    # ── 7. Çıktılar ──
    print("\n[7/7] Çıktılar yazılıyor...")
    try:
        from astrotransit.outputs.writers import OutputManager
        out = OutputManager(settings=settings)
        if quality_result is not None:
            record = out.write(
                candidate=candidate,
                quality_result=quality_result,
                fit_result=fit_result,
                stellar_props=stellar,
            )
            print(f"  ✓ Kaydedildi — sınıf: {record.candidate_class}  "
                  f"skor: {record.total_score:.0f}")
        out.close()

        # Çıktı listesi
        out_dir = project_root / settings.general.output_dir
        for sub in ["parquet", "json"]:
            d = out_dir / sub
            if d.exists():
                files = list(d.iterdir())
                if files:
                    print(f"    {sub}/: {len(files)} dosya")
    except Exception as e:
        print(f"  ⚠ Çıktı hatası: {e}")

    # ── Sonuç ──
    elapsed = time.time() - t_start
    print()
    print("=" * 65)
    print(f"  Toplam süre: {elapsed:.1f}s")
    print()

    if candidate.confirmed:
        print(f"  ✓ {TARGET} — Transit ONAYLANDI")
        if fit_result and fit_result.success:
            print(f"    P  = {fit_result.period:.5f} gün")
            print(f"    Rp = {fit_result.derived.planet_radius_rearth:.2f} R⊕")
        if quality_result:
            print(f"    Sınıf: {quality_result.score.candidate_class.value}  "
                  f"(skor: {quality_result.score.total_score:.0f}/100)")
    elif candidate.has_candidate:
        print(f"  ⚠ Aday bulundu ancak cascade tam onaylamadı.")
        print(f"  Durum: {candidate.status.value}")
    else:
        print(f"  – Transit tespit edilemedi ({TARGET} sektör {SECTOR})")

    print()
    print("  Dashboard için: streamlit run dashboard/app.py")
    print("=" * 65)

    return True


# ──────────────────────────────────────────────────────────────
# Giriş noktası
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AstroTransit ilk test")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Çevrimdışı mod — sentetik veri kullanır (internet gerekmez)",
    )
    args = parser.parse_args()

    if args.offline:
        success = run_synthetic_test()
    else:
        success = run_real_test()

    sys.exit(0 if success else 1)