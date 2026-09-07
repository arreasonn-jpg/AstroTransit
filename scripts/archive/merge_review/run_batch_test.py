"""
AstroTransit toplu test scripti.

Bilinen 10 hedef üzerinde pipeline'ı çalıştırıp
performans metriklerini raporlar.

Çalıştırma:
    python scripts/run_batch_test.py
    python scripts/run_batch_test.py --quick     # Sadece 3 hedef
    python scripts/run_batch_test.py --targets 5 # İlk 5 hedef
"""

from __future__ import annotations

import sys
import time
import argparse
from pathlib import Path
from dataclasses import dataclass, field

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


# ──────────────────────────────────────
# Test hedefleri (bilinen değerlerle)
# ──────────────────────────────────────

@dataclass
class KnownTarget:
    """Test için bilinen hedef bilgisi."""

    tic_id: str
    name: str
    sector: int
    expected_period: float           # gün — bilinen değer
    expected_rp_rearth: float        # R⊕ — bilinen değer
    is_planet: bool = True           # gerçek gezegen mi
    difficulty: str = "easy"          # easy / medium / hard / control
    note: str = ""


TEST_TARGETS = [
    # === KOLAY - Sicak Jupiterler ===
    KnownTarget("TIC 100100827", "WASP-18b", 2,
                0.9414518, 13.4, difficulty="easy",
                note="P=0.941d, Rp=13.4 R_earth"),
    KnownTarget("TIC 25155310", "WASP-126b", 1,
                3.288776, 10.4, difficulty="easy",
                note="P=3.289d, Rp=10.4 R_earth"),
    KnownTarget("TIC 142090065", "WASP-19b", 19,
                0.788839, 15.4, difficulty="easy",
                note="P=0.789d, Rp=15.4 R_earth"),
    KnownTarget("TIC 183985250", "WASP-77Ab", 2,
                1.360029, 13.0, difficulty="easy",
                note="P=1.360d, Rp=13.0 R_earth"),

    # === ORTA - Cesitli boyutlar ===
    KnownTarget("TIC 38846515", "TOI-125b", 1,
                4.6543, 2.9, difficulty="medium",
                note="P=4.654d, Rp=2.9 R_earth"),
    KnownTarget("TIC 279741379", "WASP-100b", 1,
                2.849382, 15.4, difficulty="medium",
                note="P=2.849d, Rp=15.4 R_earth"),
    KnownTarget("TIC 281541555", "HATS-24b", 1,
                1.348497, 15.6, difficulty="medium",
                note="P=1.348d, Rp=15.6 R_earth"),

    # === ZOR - Kucuk gezegenler ===
    KnownTarget("TIC 29857954", "TOI-402.01", 28,
                4.7562, 3.0, difficulty="hard",
                note="P=4.756d, Rp=3.0 R_earth"),
    KnownTarget("TIC 219338557", "TOI-561b", 1,
                0.4465, 1.42, difficulty="hard",
                note="P=0.447d, Rp=1.4 R_earth"),

]


# ──────────────────────────────────────
# Sonuç sınıfı
# ──────────────────────────────────────

@dataclass
class TargetTestResult:
    """Tek hedefin test sonucu."""

    target: KnownTarget

    # Pipeline sonuçları
    success: bool = False
    detected: bool = False
    confirmed: bool = False

    # Bulunan değerler
    found_period: float = 0.0
    found_rp_rearth: float = 0.0
    found_snr: float = 0.0
    found_sde: float = 0.0
    found_class: str = ""
    found_score: float = 0.0
    found_fpp: float = 1.0

    # Doğruluk
    period_error_pct: float = -1.0
    radius_error_pct: float = -1.0

    # Bilimsel dogrulama (batch test tarafindan yapilir)
    is_scientifically_correct: bool = False
    reality_check_reasons: list = None

    # Meta
    elapsed_sec: float = 0.0
    error: str = ""

    def __post_init__(self):
        if self.reality_check_reasons is None:
            self.reality_check_reasons = []


# ──────────────────────────────────────
# Test motoru
# ──────────────────────────────────────

def test_single_target(
    target: KnownTarget,
    orchestrator,
    verbose: bool = True,
) -> TargetTestResult:
    """Tek bir hedefi test eder."""

    result = TargetTestResult(target=target)
    t_start = time.time()

    if verbose:
        print(f"\n{'─' * 68}")
        print(f"  Test: {target.name}  ({target.tic_id})")
        print(f"  Zorluk: {target.difficulty}  |  {target.note}")
        print(f"  Beklenen: P={target.expected_period:.4f}d, "
              f"Rp={target.expected_rp_rearth:.2f} R⊕")
        print(f"{'─' * 68}")

    try:
        target_result = orchestrator.run_single(
            target.tic_id,
            sectors=[target.sector],
        )

        result.success = target_result.success

        if target_result.sector_results:
            sr = target_result.sector_results[0]

            result.detected = sr.has_candidate
            result.confirmed = sr.candidate_confirmed

            if sr.candidate is not None:
                result.found_period = sr.candidate.period
                result.found_snr = sr.candidate.snr
                result.found_sde = sr.candidate.sde

                # Periyot hatası
                if target.expected_period > 0 and result.found_period > 0:
                    # Harmonik toleransı: 0.5x, 1x, 2x kontrolü
                    best_err = float('inf')
                    for factor in [0.5, 1.0, 2.0]:
                        expected = target.expected_period * factor
                        err_pct = abs(result.found_period - expected) / expected * 100
                        if err_pct < best_err:
                            best_err = err_pct
                    result.period_error_pct = best_err

            # Kalite skoru
            if sr.quality is not None:
                result.found_class = sr.quality.score.candidate_class.value
                result.found_score = sr.quality.score.total_score
                result.found_fpp = sr.quality.vetting.false_positive_probability

            # Fit sonucu (yarıçap için)
            if sr.fit_result is not None and sr.fit_result.success:
                if hasattr(sr.fit_result, 'derived') and sr.fit_result.derived:
                    result.found_rp_rearth = sr.fit_result.derived.planet_radius_rearth

                    if target.expected_rp_rearth > 0 and result.found_rp_rearth > 0:
                        result.radius_error_pct = abs(
                            result.found_rp_rearth - target.expected_rp_rearth
                        ) / target.expected_rp_rearth * 100

    except Exception as e:
        result.success = False
        result.error = str(e)[:100]
        if verbose:
            print(f"  ✗ HATA: {e}")

    result.elapsed_sec = time.time() - t_start

    # === REALITY CHECK - Bilimsel Dogrulama ===
    # Pipeline "basarili" dese bile beklenen degerlerle uyumlu mu?
    reasons = []

    if not result.confirmed:
        reasons.append("cascade onaylanmadi")

    if result.period_error_pct > 5.0:
        reasons.append(f"P hatasi %{result.period_error_pct:.1f} > %5")
    elif result.period_error_pct < 0:
        reasons.append("P hatasi olculemedi")

    if result.radius_error_pct > 30.0 and result.radius_error_pct >= 0:
        reasons.append(f"Rp hatasi %{result.radius_error_pct:.1f} > %30")

    result.reality_check_reasons = reasons
    result.is_scientifically_correct = len(reasons) == 0

    # Özet çıktı
    if verbose:
        print()
        # Bilimsel dogruluk
        if result.is_scientifically_correct:
            sci_status = "BILIMSEL: DOGRU"
        else:
            sci_reasons = ", ".join(result.reality_check_reasons)
            sci_status = f"BILIMSEL: HATALI ({sci_reasons})"

        if result.confirmed:
            print(f"  ✓ ONAYLANDI  |  Sınıf {result.found_class}  |  "
                  f"Skor {result.found_score:.0f}/100")
            print(f"    {sci_status}")
            print(f"    P bulunan: {result.found_period:.5f}d  "
                  f"(hata: %{result.period_error_pct:.2f})")
            if result.found_rp_rearth > 0:
                print(f"    Rp bulunan: {result.found_rp_rearth:.2f} R⊕  "
                      f"(hata: %{result.radius_error_pct:.1f})")
        elif result.detected:
            print(f"  ⚠ Aday bulundu ama cascade onaylamadı")
            print(f"    P: {result.found_period:.5f}d")
        else:
            print(f"  ✗ Transit tespit edilemedi")

        print(f"    Süre: {result.elapsed_sec:.1f}s")

    return result


# ──────────────────────────────────────
# Rapor
# ──────────────────────────────────────

def print_summary_report(results: list[TargetTestResult]) -> dict:
    """Toplu test özet raporunu yazdırır."""

    print("\n" + "=" * 90)
    print(f"  {'TOPLU TEST ÖZET RAPORU':^86}")
    print("=" * 90)

    # ── Tablo ──
    print(f"\n{'#':>2}  {'Hedef':<20} {'Zorluk':<8} {'Beklenen P':>10} "
          f"{'Bulunan P':>10} {'Hata %':>8} {'Sınıf':<6} {'Skor':>5} {'Durum':<12}")
    print("─" * 90)

    n_success = 0
    n_confirmed = 0
    n_class_a = 0
    n_class_b = 0
    n_scientifically_correct = 0
    total_period_err = []
    total_radius_err = []

    for i, r in enumerate(results, 1):
        # Durum
        if r.confirmed:
            status = "✓ ONAYLI"
            n_confirmed += 1
        elif r.detected:
            status = "⚠ ADAY"
        elif r.success:
            status = "– TESPİT YOK"
        else:
            status = "✗ HATA"

        if r.success:
            n_success += 1

        if r.found_class == "A":
            n_class_a += 1
        elif r.found_class == "B":
            n_class_b += 1

        if r.is_scientifically_correct:
            n_scientifically_correct += 1

        if r.period_error_pct >= 0:
            total_period_err.append(r.period_error_pct)
        if r.radius_error_pct >= 0:
            total_radius_err.append(r.radius_error_pct)

        err_str = f"%{r.period_error_pct:.2f}" if r.period_error_pct >= 0 else "—"

        print(f"{i:>2}  {r.target.name:<20} {r.target.difficulty:<8} "
              f"{r.target.expected_period:>10.4f} {r.found_period:>10.4f} "
              f"{err_str:>8} {r.found_class:<6} {r.found_score:>5.0f} {status:<12}")

    # ── İstatistikler ──
    print("─" * 90)

    total = len(results)

    print(f"\n  {'Toplam hedef':<30} : {total}")
    print(f"  {'Pipeline başarısı':<30} : {n_success}/{total}  "
          f"({100 * n_success / total:.0f}%)")
    print(f"  {'Onaylı transit tespiti':<30} : {n_confirmed}/{total}  "
          f"({100 * n_confirmed / total:.0f}%)")
    print(f"  {'Sınıf A':<30} : {n_class_a}")
    print(f"  {'Sınıf B':<30} : {n_class_b}")
    print(f"  {'BILIMSEL DOGRU':<30} : {n_scientifically_correct}/{total} "
          f"({100 * n_scientifically_correct / total:.0f}%)")

    # Ortalama hatalar
    if total_period_err:
        import numpy as np
        mean_err = np.mean(total_period_err)
        median_err = np.median(total_period_err)
        print(f"\n  {'Periyot hatası ortalama':<30} : %{mean_err:.3f}")
        print(f"  {'Periyot hatası medyan':<30} : %{median_err:.3f}")

    if total_radius_err:
        import numpy as np
        mean_r = np.mean(total_radius_err)
        median_r = np.median(total_radius_err)
        print(f"  {'Yarıçap hatası ortalama':<30} : %{mean_r:.1f}")
        print(f"  {'Yarıçap hatası medyan':<30} : %{median_r:.1f}")

    # Toplam süre
    total_time = sum(r.elapsed_sec for r in results)
    avg_time = total_time / total if total > 0 else 0
    print(f"\n  {'Toplam süre':<30} : {total_time:.0f}s "
          f"({total_time / 60:.1f} dk)")
    print(f"  {'Ortalama süre / hedef':<30} : {avg_time:.1f}s")

    # ── Zorluk bazlı analiz ──
    print("\n  " + "─" * 60)
    print("  Zorluk bazlı başarı oranı:")

    from collections import defaultdict
    by_difficulty = defaultdict(list)
    for r in results:
        by_difficulty[r.target.difficulty].append(r)

    for diff in ["easy", "medium", "hard"]:
        if diff in by_difficulty:
            group = by_difficulty[diff]
            n_conf = sum(1 for r in group if r.confirmed)
            pct = 100 * n_conf / len(group) if group else 0
            print(f"    {diff:<8} : {n_conf}/{len(group)}  ({pct:.0f}%)")

    print()
    print("=" * 90)

    return {
        "total": total,
        "success": n_success,
        "confirmed": n_confirmed,
        "class_a": n_class_a,
        "class_b": n_class_b,
        "total_time_sec": total_time,
    }


# ──────────────────────────────────────
# Ana giriş
# ──────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AstroTransit toplu test")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Sadece 3 hedefi test et (hızlı test)",
    )
    parser.add_argument(
        "--targets",
        type=int,
        default=None,
        help="İlk N hedefi test et",
    )
    parser.add_argument(
        "--no-viz",
        action="store_true",
        help="Görselleştirmeyi atla (hızlanır)",
    )
    args = parser.parse_args()

    from astrotransit.pipelines.orchestrator import AstroTransitOrchestrator
    from astrotransit.logging_config import setup_logging

    # Log seviyesini WARNING yap (uzun batch için)
    setup_logging(log_level="WARNING")

    # Hedef listesi
    if args.quick:
        targets = TEST_TARGETS[:3]
    elif args.targets:
        targets = TEST_TARGETS[:args.targets]
    else:
        targets = TEST_TARGETS

    print("=" * 90)
    print(f"  {'AstroTransit — Toplu Test':^86}")
    print("=" * 90)
    print(f"  Hedef sayısı : {len(targets)}")
    print(f"  Görsel       : {'kapalı' if args.no_viz else 'açık'}")
    print(f"  Modelleme    : MAP only (hızlı)")
    print("=" * 90)

    t_batch_start = time.time()

    results = []

    with AstroTransitOrchestrator(
        force_map=True,
        skip_visualization=args.no_viz,
        skip_catalog=False,
        log_level="WARNING",
    ) as orch:

        for i, target in enumerate(targets, 1):
            print(f"\n\n[{i}/{len(targets)}]", end="")
            result = test_single_target(target, orch, verbose=True)
            results.append(result)

    batch_elapsed = time.time() - t_batch_start

    # ── Özet rapor ──
    stats = print_summary_report(results)

    print(f"\n  Toplam batch süresi: {batch_elapsed:.0f}s ({batch_elapsed / 60:.1f} dk)")
    print()
    print("  Sonuçları incelemek için:")
    print("    python -c \"import pandas as pd; "
          "df=pd.read_parquet('outputs/parquet/astrotransit_candidates.parquet'); "
          "print(df[['source_id','period','planet_radius_rearth','candidate_class','total_score']].to_string())\"")
    print()
    print("  Dashboard için:")
    print("    streamlit run dashboard/app.py")
    print()

    return 0 if stats["confirmed"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())