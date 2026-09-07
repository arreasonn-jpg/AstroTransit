"""
AstroTransit görsel üretim testi.

Mevcut bir analiz sonucundan tüm görselleri üretir:
    - Ham + detrended light curve karşılaştırması
    - BLS + TLS periodogram
    - Faz katlanmış transit + model
    - Residual histogram
    - Transit zamanlama O-C
    - Kalite skoru kartı
    - Çok panelli özet görsel

Çalıştırma:
    python scripts/generate_visuals.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def main():
    from astrotransit.logging_config import setup_logging
    from astrotransit.settings import get_settings
    from astrotransit.data.tess_client import TESSClient
    from astrotransit.data.catalog_client import CatalogClient
    from astrotransit.preprocessing.pipeline import TESSPreprocessingPipeline
    from astrotransit.detection.cascade import CascadeDetector
    from astrotransit.modeling.fitter import ModelingOrchestrator
    from astrotransit.quality.pipeline import QualityEvaluationPipeline
    from astrotransit.visualization.report_generator import (
        VisualizationReportGenerator,
    )

    setup_logging(log_level="INFO")

    print("=" * 68)
    print("  AstroTransit — Görsel Üretim Testi")
    print("  Hedef: WASP-18b  (TIC 100100827, Sektör 2)")
    print("=" * 68)

    settings = get_settings()

    TARGET = "TIC 100100827"
    SECTOR = 2

    t_start = time.time()

    # ── 1. Yıldız özellikleri ──
    print("\n[1/6] Yıldız özellikleri...")
    cat = CatalogClient()
    stellar = cat.get_stellar_properties(TARGET)

    if stellar.is_valid():
        print(f"  ✓ Teff={stellar.teff:.0f}K  R={stellar.radius:.2f}Rs  "
              f"M={stellar.mass:.2f}Ms")
    else:
        print("  ⚠ Yıldız parametreleri eksik, varsayılan kullanılıyor.")

    stellar_radius = stellar.radius if stellar.is_valid() else 1.3
    stellar_mass = stellar.mass if stellar.is_valid() else 1.3
    stellar_teff = stellar.teff if stellar.teff > 0 else 6400.0

    # ── 2. Light curve ──
    print("\n[2/6] Light curve indiriliyor (cache'ten alınacak)...")
    client = TESSClient(
        author=settings.tess.author,
        exptime=settings.tess.exptime,
        use_cache=settings.tess.use_cache,
    )
    lc_data = client.get_lightcurve(TARGET, sector=SECTOR)
    print(f"  ✓ {lc_data.n_points_clean} nokta")

    # ── 3. Ön işleme ──
    print("\n[3/6] Ön işleme...")
    preproc = TESSPreprocessingPipeline(settings=settings)
    preprocessed = preproc.run(lc_data)
    detrended = preprocessed.detrended
    normalized = preprocessed.normalized
    print(f"  ✓ Detrend tamamlandı — gürültü: {detrended.noise_ppm:.0f} ppm")

    # ── 4. Transit tespit ──
    print("\n[4/6] Cascade tespiti...")
    cascade = CascadeDetector(
        settings=settings,
        stellar_radius=stellar_radius,
        stellar_mass=stellar_mass,
    )
    candidate = cascade.detect(detrended)
    print(f"  ✓ Durum: {candidate.status.value}  |  "
          f"P={candidate.period:.4f}d  |  SNR={candidate.snr:.1f}")

    # ── 5. MAP fit ──
    print("\n[5/6] MAP fit...")
    modeling = ModelingOrchestrator(
        settings=settings,
        stellar_radius=stellar_radius,
        stellar_mass=stellar_mass,
        stellar_teff=stellar_teff,
        force_map=True,
    )
    fit_result = modeling.fit(detrended, candidate)

    if fit_result.success:
        print(f"  ✓ Rp={fit_result.derived.planet_radius_rearth:.2f} R⊕  "
              f"|  Teq={fit_result.derived.equilibrium_temperature_k:.0f}K")
    else:
        print("  ⚠ MAP fit başarısız (cascade değerleri kullanılacak)")

    # ── Kalite ──
    quality_pipe = QualityEvaluationPipeline(settings=settings)
    quality_result = quality_pipe.evaluate(detrended, candidate, fit_result)
    score = quality_result.score
    print(f"  ✓ Sınıf: {score.candidate_class.value}  |  "
          f"Skor: {score.total_score:.0f}/100")

    # ── 6. GÖRSELLER ──
    print("\n[6/6] Görseller üretiliyor...")

    viz_gen = VisualizationReportGenerator(settings=settings)

    t_viz = time.time()

    viz_report = viz_gen.generate(
        detrended=detrended,
        normalized=normalized,
        candidate=candidate,
        bls_result=candidate.bls_result,
        tls_result=candidate.tls_result,
        score=score,
        vetting=quality_result.vetting,
        fit_result=fit_result,
        stellar_props=stellar,
    )

    viz_elapsed = time.time() - t_viz

    # ── Rapor ──
    print(f"\n  Görsel üretim süresi: {viz_elapsed:.1f}s")
    print()
    print("  Üretilen grafikler:")

    figures = {
        "Özet Panel":         viz_report.summary_panel,
        "Light Curve":        viz_report.lightcurve,
        "Periodogram":        viz_report.periodogram,
        "Faz Katlanmış":      viz_report.folded,
        "Residual":           viz_report.residuals,
        "Timing O-C":         viz_report.timing,
        "Skor Kartı":         viz_report.scorecard,
    }

    n_ok = 0
    n_fail = 0

    for name, path in figures.items():
        if path is not None and Path(path).exists():
            size_kb = Path(path).stat().st_size / 1024
            print(f"    ✓ {name:20s} — {Path(path).name} ({size_kb:.0f} KB)")
            n_ok += 1
        else:
            print(f"    ✗ {name:20s} — üretilmedi")
            n_fail += 1

    # ── Toplam ──
    total_elapsed = time.time() - t_start
    print()
    print("=" * 68)
    print(f"  Toplam süre: {total_elapsed:.1f}s")
    print(f"  Görsel: {n_ok} başarılı, {n_fail} başarısız")

    figures_dir = project_root / settings.general.output_dir / "figures"
    if figures_dir.exists():
        all_pngs = list(figures_dir.glob("*.png"))
        total_size = sum(f.stat().st_size for f in all_pngs) / 1024
        print(f"  Dizin: {figures_dir}")
        print(f"  Toplam: {len(all_pngs)} dosya ({total_size:.0f} KB)")

    print()
    print("  Görselleri açmak için:")
    print(f"    explorer {figures_dir}")
    print()
    print("  Dashboard'da görüntülemek için:")
    print("    streamlit run dashboard/app.py")
    print("=" * 68)

    return n_ok > 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)