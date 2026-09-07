"""
TIC 417860263 — Forced Ephemeris Multi-Sector Validation

S57'den gelen bilinen ephemeris ile tüm sektörlerde:
  - AstroTransit preprocessing+detrending pipeline'ı kullanarak
  - transit pencerelerini kes
  - faz katla
  - in-transit vs out-of-transit depth ölç
  - sektör bazlı SNR tahmin et
  - odd-even transit depth karşılaştır
  - sonuçları JSON / CSV / MD olarak kaydet
"""

from __future__ import annotations

import json
import csv
import math
import sys
from pathlib import Path
from dataclasses import dataclass, field, asdict

import numpy as np

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

# ─────────────────────────────────────────────
# Sabitler
# ─────────────────────────────────────────────
TIC_ID = "TIC 417860263"
HOST_NAME = "HD 224792"

# S57 MAP+MCMC sonuçlarından gelen ephemeris
PERIOD = 2.8535114704493703       # gün
T0_BTJD = 2854.378905            # BTJD

# Transit parametreleri
RP_RS = 0.025096
DURATION_HOURS = 3.6246
DURATION_DAYS = DURATION_HOURS / 24.0

SECTORS = [57, 58, 77, 78, 84, 85]

OUT_DIR = Path("outputs_tic417860263_forced_ephemeris")
OUT_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR = OUT_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
FIGURES_DIR = OUT_DIR / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────
# JSON sanitizer
# ─────────────────────────────────────────────
def to_jsonable(obj):
    """NumPy / masked array / Path nesnelerini JSON-uyumlu hale getirir."""
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]

    if isinstance(obj, Path):
        return str(obj)

    if obj is np.ma.masked:
        return None

    if isinstance(obj, np.ma.MaskedArray):
        return to_jsonable(obj.filled(np.nan).tolist())

    if isinstance(obj, np.ndarray):
        return to_jsonable(obj.tolist())

    if isinstance(obj, np.integer):
        return int(obj)

    if isinstance(obj, np.floating):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)

    if isinstance(obj, np.bool_):
        return bool(obj)

    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj

    return obj


# ─────────────────────────────────────────────
# Veri yapıları
# ─────────────────────────────────────────────
@dataclass
class SectorValidation:
    sector: int
    success: bool = False
    error: str = ""
    detrending_used: bool = False
    n_points: int = 0
    time_start: float = 0.0
    time_end: float = 0.0
    time_span_days: float = 0.0
    expected_transits: int = 0
    observed_transit_indices: list = field(default_factory=list)
    n_in_transit: int = 0
    n_out_transit: int = 0
    median_in_transit: float = 0.0
    median_out_transit: float = 0.0
    depth_ppm: float = 0.0
    depth_err_ppm: float = 0.0
    out_of_transit_scatter_ppm: float = 0.0
    sector_snr: float = 0.0
    transit_detected: bool = False
    n_odd_transits: int = 0
    n_even_transits: int = 0
    depth_odd_ppm: float = 0.0
    depth_even_ppm: float = 0.0
    odd_even_diff_ppm: float = 0.0
    odd_even_consistent: bool = True


# ─────────────────────────────────────────────
# Yardımcı fonksiyonlar
# ─────────────────────────────────────────────
def phase_fold(time: np.ndarray, period: float, t0: float) -> np.ndarray:
    return ((time - t0) / period) % 1.0


def get_transit_mask(phase: np.ndarray, duration_phase: float) -> np.ndarray:
    half_dur = duration_phase / 2.0
    return (phase < half_dur) | (phase > (1.0 - half_dur))


def get_transit_numbers(
    time: np.ndarray, period: float, t0: float
) -> np.ndarray:
    return np.round((time - t0) / period).astype(int)


def compute_depth(
    flux_in: np.ndarray, flux_out: np.ndarray
) -> tuple[float, float]:
    if len(flux_in) < 3 or len(flux_out) < 10:
        return 0.0, 0.0
    median_out = np.median(flux_out)
    median_in = np.median(flux_in)
    if median_out == 0:
        return 0.0, 0.0
    depth = (median_out - median_in) / median_out * 1e6
    scatter_in = np.std(flux_in) / np.sqrt(len(flux_in)) / median_out * 1e6
    scatter_out = np.std(flux_out) / np.sqrt(len(flux_out)) / median_out * 1e6
    depth_err = np.sqrt(scatter_in**2 + scatter_out**2)
    return depth, depth_err


def compute_odd_even(
    time: np.ndarray,
    flux: np.ndarray,
    transit_mask: np.ndarray,
    period: float,
    t0: float,
) -> tuple[float, float, int, int]:
    transit_nums = get_transit_numbers(time, period, t0)
    in_transit = transit_mask

    odd_mask = in_transit & ((transit_nums % 2) != 0)
    even_mask = in_transit & ((transit_nums % 2) == 0)
    out_mask = ~in_transit

    flux_out = flux[out_mask]
    median_out = np.median(flux_out) if len(flux_out) > 0 else 1.0

    flux_odd = flux[odd_mask]
    flux_even = flux[even_mask]

    n_odd = int(len(flux_odd))
    n_even = int(len(flux_even))

    if n_odd < 3 or n_even < 3 or median_out == 0:
        return 0.0, 0.0, n_odd, n_even

    depth_odd = (median_out - np.median(flux_odd)) / median_out * 1e6
    depth_even = (median_out - np.median(flux_even)) / median_out * 1e6

    return float(depth_odd), float(depth_even), n_odd, n_even


def safe_array(arr) -> np.ndarray:
    """Masked array veya lightkurve column'ı temiz float64 array'e çevirir."""
    if hasattr(arr, "value"):
        arr = arr.value
    if isinstance(arr, np.ma.MaskedArray):
        arr = arr.filled(np.nan)
    arr = np.array(arr, dtype=np.float64)
    return arr


# ─────────────────────────────────────────────
# AstroTransit detrending ile veri al
# ─────────────────────────────────────────────
def get_detrended_data(sector: int) -> tuple[np.ndarray, np.ndarray, bool]:
    """
    AstroTransit pipeline ile detrend edilmiş time, flux döndürür.
    Pipeline çalışmazsa lightkurve flatten fallback kullanır.

    Returns:
        (time, flux, detrending_used)
        detrending_used=True  -> AstroTransit detrending kullanıldı
        detrending_used=False -> lightkurve flatten fallback kullanıldı
    """
    import lightkurve as lk

    # Önce veriyi indir
    sr = lk.search_lightcurve(
        TIC_ID,
        mission="TESS",
        author="SPOC",
        exptime=120,
        sector=sector,
    )

    if sr is None or len(sr) == 0:
        raise ValueError(f"Sector {sector}: no SPOC 120s data found")

    lc = sr.download()
    lc = lc.remove_nans().remove_outliers(sigma=5.0)

    # AstroTransit pipeline ile dene
    try:
        from astrotransit.data.tess_client import TESSClient
        from astrotransit.preprocessing.pipeline import TESSPreprocessingPipeline
        from astrotransit.settings import load_settings

        settings = load_settings(project_root / "configs" / "default.toml")

        # Senin projendeki gerçek signature'a göre:
        client = TESSClient(
            author="SPOC",
            exptime=120,
            quality_bitmask="default",
        )

        preproc = TESSPreprocessingPipeline(settings=settings)

        lc_data = client.get_lightcurve(TIC_ID, sector=sector)
        preprocessed = preproc.run(lc_data)

        print(f"  AstroTransit detrending OK for S{sector}")
        print(f"    detrended.time type: {type(preprocessed.detrended.time)}")
        print(f"    detrended.flux type: {type(preprocessed.detrended.flux)}")

        time = safe_array(preprocessed.detrended.time)
        flux = safe_array(preprocessed.detrended.flux)

        # NaN temizle
        valid = np.isfinite(time) & np.isfinite(flux)
        time = time[valid]
        flux = flux[valid]

        if len(time) > 100:
            return time, flux, True
        else:
            print(
                f"  AstroTransit detrending returned too few points "
                f"for S{sector}: {len(time)}"
            )

    except Exception as e:
        print(f"  AstroTransit detrending failed for S{sector}: {e}")
        print(f"  Falling back to lightkurve flatten...")

    # Fallback: lightkurve flatten
    lc_flat = lc.flatten(window_length=301)
    lc_flat = lc_flat.normalize()

    time = safe_array(lc_flat.time)
    flux = safe_array(lc_flat.flux)

    valid = np.isfinite(time) & np.isfinite(flux)
    time = time[valid]
    flux = flux[valid]

    return time, flux, False


# ─────────────────────────────────────────────
# Sektör doğrulama fonksiyonu
# ─────────────────────────────────────────────
def validate_sector(sector: int) -> SectorValidation:
    sv = SectorValidation(sector=sector)

    try:
        time, flux, detrended = get_detrended_data(sector)
        sv.detrending_used = detrended

        if len(time) < 100:
            sv.error = f"Sector {sector}: insufficient data ({len(time)} points)"
            return sv

        sv.n_points = int(len(time))
        sv.time_start = float(time[0])
        sv.time_end = float(time[-1])
        sv.time_span_days = float(time[-1] - time[0])

        # Beklenen transit sayısı
        first_transit = max(0, int(np.ceil((time[0] - T0_BTJD) / PERIOD)))
        last_transit = int(np.floor((time[-1] - T0_BTJD) / PERIOD))
        sv.expected_transits = max(0, last_transit - first_transit + 1)

        # Faz katlama
        phase = phase_fold(time, PERIOD, T0_BTJD)
        duration_phase = DURATION_DAYS / PERIOD
        transit_mask = get_transit_mask(phase, duration_phase)

        flux_in = flux[transit_mask]
        flux_out = flux[~transit_mask]

        sv.n_in_transit = int(len(flux_in))
        sv.n_out_transit = int(len(flux_out))

        if len(flux_out) > 0:
            sv.median_out_transit = float(np.median(flux_out))
            sv.out_of_transit_scatter_ppm = float(np.std(flux_out) * 1e6)
        if len(flux_in) > 0:
            sv.median_in_transit = float(np.median(flux_in))

        # Derinlik
        depth, depth_err = compute_depth(flux_in, flux_out)
        sv.depth_ppm = float(depth)
        sv.depth_err_ppm = float(depth_err)

        # SNR
        if depth_err > 0:
            sv.sector_snr = float(depth / depth_err)

        # Transit detected?
        sv.transit_detected = sv.depth_ppm > 0 and sv.sector_snr > 3.0

        # Odd-even
        depth_odd, depth_even, n_odd, n_even = compute_odd_even(
            time, flux, transit_mask, PERIOD, T0_BTJD
        )
        sv.depth_odd_ppm = float(depth_odd)
        sv.depth_even_ppm = float(depth_even)
        sv.n_odd_transits = int(n_odd)
        sv.n_even_transits = int(n_even)
        sv.odd_even_diff_ppm = float(abs(depth_odd - depth_even))

        # Odd-even consistency (3-sigma)
        if depth_err > 0:
            sv.odd_even_consistent = sv.odd_even_diff_ppm < (3.0 * depth_err)
        else:
            sv.odd_even_consistent = True

        # Transit numaralarını kaydet
        transit_nums = get_transit_numbers(time, PERIOD, T0_BTJD)
        unique_in = np.unique(transit_nums[transit_mask])
        sv.observed_transit_indices = [int(x) for x in unique_in.tolist()]

        sv.success = True

    except Exception as e:
        sv.error = str(e)

    return sv


# ─────────────────────────────────────────────
# Faz katlama görseli
# ─────────────────────────────────────────────
def plot_phase_fold(sector: int):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        time, flux, detrended = get_detrended_data(sector)

        phase = phase_fold(time, PERIOD, T0_BTJD)
        # Transit merkezini 0'da göster
        phase = np.where(phase > 0.5, phase - 1.0, phase)

        duration_phase = DURATION_DAYS / PERIOD

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.scatter(phase, flux, s=1, alpha=0.3, color="gray", label="data")

        # Binned
        n_bins = 100
        bin_edges = np.linspace(-0.5, 0.5, n_bins + 1)
        bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
        bin_means = np.full(n_bins, np.nan)
        for i in range(n_bins):
            mask = (phase >= bin_edges[i]) & (phase < bin_edges[i + 1])
            if np.sum(mask) > 3:
                bin_means[i] = np.median(flux[mask])

        ax.plot(bin_centers, bin_means, "r-", lw=1.5, label="binned median")

        # Transit penceresi
        ax.axvline(
            -duration_phase / 2, color="blue", ls="--", alpha=0.5,
            label="transit window",
        )
        ax.axvline(duration_phase / 2, color="blue", ls="--", alpha=0.5)

        detrend_label = "AstroTransit" if detrended else "lightkurve flatten"
        ax.set_xlabel("Phase")
        ax.set_ylabel("Normalized Flux")
        ax.set_title(
            f"TIC 417860263 — Sector {sector} — "
            f"Forced Ephemeris Phase Fold\n"
            f"P={PERIOD:.6f} d, T0={T0_BTJD:.6f} BTJD "
            f"[detrend: {detrend_label}]"
        )
        ax.legend(loc="lower right", fontsize=8)
        ax.set_xlim(-0.15, 0.15)

        fig_path = (
            FIGURES_DIR / f"TIC_417860263_S{sector:02d}_forced_phasefold.png"
        )
        fig.savefig(fig_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  Figure: {fig_path}")

    except Exception as e:
        print(f"  Figure failed for S{sector}: {e}")


# ─────────────────────────────────────────────
# Ana fonksiyon
# ─────────────────────────────────────────────
def main():
    print("=" * 72)
    print("TIC 417860263 — Forced Ephemeris Multi-Sector Validation")
    print("=" * 72)
    print(f"Period     : {PERIOD:.7f} d")
    print(f"T0 (BTJD)  : {T0_BTJD:.6f}")
    print(f"Duration   : {DURATION_HOURS:.4f} hrs ({DURATION_DAYS:.6f} d)")
    print(f"Rp/Rs      : {RP_RS:.6f}")
    print(f"Sectors    : {SECTORS}")
    print("=" * 72)

    results = []

    for sector in SECTORS:
        print(f"\n── Sector {sector} ──")
        sv = validate_sector(sector)
        results.append(sv)

        if sv.success:
            det = "YES" if sv.transit_detected else "no"
            oe = "consistent" if sv.odd_even_consistent else "MISMATCH"
            dt = "AstroTransit" if sv.detrending_used else "lk.flatten"
            print(
                f"  detrend={dt}, "
                f"points={sv.n_points}, "
                f"span={sv.time_span_days:.1f}d, "
                f"expected_transits={sv.expected_transits}"
            )
            print(
                f"  in_transit={sv.n_in_transit}, "
                f"out_transit={sv.n_out_transit}"
            )
            print(
                f"  depth={sv.depth_ppm:.1f} ± {sv.depth_err_ppm:.1f} ppm, "
                f"SNR={sv.sector_snr:.2f}, "
                f"detected={det}"
            )
            print(
                f"  odd_depth={sv.depth_odd_ppm:.1f}, "
                f"even_depth={sv.depth_even_ppm:.1f}, "
                f"diff={sv.odd_even_diff_ppm:.1f} ppm, "
                f"{oe}"
            )

            # Faz görseli üret
            plot_phase_fold(sector)

        else:
            print(f"  FAILED: {sv.error}")

    # ─── Özet hesapla ───
    detected_sectors = [r for r in results if r.success and r.transit_detected]
    all_success = [r for r in results if r.success]

    weighted_depth = 0.0
    weight_sum = 0.0
    for r in all_success:
        if r.depth_err_ppm > 0:
            w = 1.0 / (r.depth_err_ppm ** 2)
            weighted_depth += r.depth_ppm * w
            weight_sum += w

    combined_depth = weighted_depth / weight_sum if weight_sum > 0 else 0.0
    combined_err = 1.0 / np.sqrt(weight_sum) if weight_sum > 0 else 0.0
    combined_snr = combined_depth / combined_err if combined_err > 0 else 0.0

    total_in_transit = sum(r.n_in_transit for r in all_success)
    total_expected = sum(r.expected_transits for r in all_success)

    all_odd_even_consistent = all(
        r.odd_even_consistent for r in all_success
    )

    summary = {
        "target": TIC_ID,
        "host_name": HOST_NAME,
        "ephemeris": {
            "period_days": PERIOD,
            "t0_btjd": T0_BTJD,
            "duration_hours": DURATION_HOURS,
            "rp_rs": RP_RS,
            "source": "S57 MAP+MCMC",
        },
        "sectors_tested": SECTORS,
        "sectors_successful": len(all_success),
        "sectors_with_detection": len(detected_sectors),
        "detected_sector_list": [r.sector for r in detected_sectors],
        "combined_analysis": {
            "total_expected_transits": total_expected,
            "total_in_transit_points": total_in_transit,
            "weighted_mean_depth_ppm": round(float(combined_depth), 2),
            "weighted_mean_depth_err_ppm": round(float(combined_err), 2),
            "combined_snr": round(float(combined_snr), 2),
            "all_odd_even_consistent": all_odd_even_consistent,
        },
        "per_sector": [asdict(r) for r in results],
    }

    # ─── Dosya kaydet ───
    json_path = REPORTS_DIR / "TIC_417860263_forced_ephemeris_validation.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(to_jsonable(summary), f, indent=2, ensure_ascii=False)

    csv_path = REPORTS_DIR / "TIC_417860263_forced_ephemeris_validation.csv"
    fieldnames = [
        "sector", "success", "detrending_used", "n_points", "time_span_days",
        "expected_transits", "n_in_transit", "n_out_transit",
        "depth_ppm", "depth_err_ppm", "sector_snr", "transit_detected",
        "depth_odd_ppm", "depth_even_ppm", "odd_even_diff_ppm",
        "odd_even_consistent", "error",
    ]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            d = asdict(r)
            row = {k: d.get(k, "") for k in fieldnames}
            writer.writerow(row)

    md_path = REPORTS_DIR / "TIC_417860263_forced_ephemeris_validation.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TIC 417860263 — Forced Ephemeris Validation\n\n")
        f.write("## Ephemeris\n")
        f.write(f"- **Period**: {PERIOD:.7f} d\n")
        f.write(f"- **T0**: {T0_BTJD:.6f} BTJD\n")
        f.write(f"- **Duration**: {DURATION_HOURS:.4f} hrs\n")
        f.write(f"- **Rp/Rs**: {RP_RS:.6f}\n")
        f.write(f"- **Source**: S57 MAP+MCMC\n\n")

        f.write("## Combined Analysis\n")
        f.write(f"- **Sectors tested**: {len(SECTORS)}\n")
        f.write(f"- **Sectors successful**: {len(all_success)}\n")
        f.write(
            f"- **Sectors with detection (SNR>3)**: "
            f"{len(detected_sectors)}\n"
        )
        f.write(
            f"- **Detected in**: "
            f"{[r.sector for r in detected_sectors]}\n"
        )
        f.write(f"- **Total expected transits**: {total_expected}\n")
        f.write(f"- **Total in-transit points**: {total_in_transit}\n")
        f.write(
            f"- **Weighted mean depth**: "
            f"{combined_depth:.1f} ± {combined_err:.1f} ppm\n"
        )
        f.write(f"- **Combined SNR**: {combined_snr:.2f}\n")
        f.write(
            f"- **All odd-even consistent**: "
            f"{all_odd_even_consistent}\n\n"
        )

        f.write("## Per-Sector Results\n\n")
        f.write(
            "| Sector | OK | Detrend | Points | Span (d) | Expected "
            "| In-transit | Depth (ppm) | Err (ppm) | SNR | Detected "
            "| Odd (ppm) | Even (ppm) | Diff (ppm) | OE OK |\n"
        )
        f.write(
            "|---:|:---:|:---:|---:|---:|---:|---:|---:|---:|---:|"
            ":---:|---:|---:|---:|:---:|\n"
        )
        for r in results:
            if r.success:
                dt = "AT" if r.detrending_used else "lk"
                f.write(
                    f"| {r.sector} "
                    f"| ✓ "
                    f"| {dt} "
                    f"| {r.n_points} "
                    f"| {r.time_span_days:.1f} "
                    f"| {r.expected_transits} "
                    f"| {r.n_in_transit} "
                    f"| {r.depth_ppm:.1f} "
                    f"| {r.depth_err_ppm:.1f} "
                    f"| {r.sector_snr:.2f} "
                    f"| {'✓' if r.transit_detected else '✗'} "
                    f"| {r.depth_odd_ppm:.1f} "
                    f"| {r.depth_even_ppm:.1f} "
                    f"| {r.odd_even_diff_ppm:.1f} "
                    f"| {'✓' if r.odd_even_consistent else '✗'} |\n"
                )
            else:
                f.write(
                    f"| {r.sector} | ✗ | — | — | — | — | — "
                    f"| — | — | — | — | — | — | — | — |\n"
                )

        f.write("\n## Interpretation\n")
        if len(detected_sectors) >= 4:
            f.write(
                "- **Strong multi-sector support**: transit signal "
                f"recovered in {len(detected_sectors)} of "
                f"{len(SECTORS)} sectors.\n"
            )
        elif len(detected_sectors) >= 2:
            f.write(
                "- **Partial multi-sector support**: transit signal "
                f"recovered in {len(detected_sectors)} of "
                f"{len(SECTORS)} sectors.\n"
            )
        elif len(detected_sectors) == 1:
            f.write(
                "- **Single-sector detection only**: signal detected "
                "in only 1 sector.\n"
            )
        else:
            f.write(
                "- **No multi-sector recovery**: signal not detected "
                "in any sector with forced ephemeris.\n"
            )

        if all_odd_even_consistent:
            f.write(
                "- **Odd-even consistency**: all sectors show "
                "consistent odd/even transit depths.\n"
            )
        else:
            inconsistent = [
                r.sector for r in all_success
                if not r.odd_even_consistent
            ]
            f.write(
                f"- **Odd-even WARNING**: sectors {inconsistent} "
                "show inconsistent odd/even depths. "
                "Further investigation needed.\n"
            )

        if combined_snr > 10:
            f.write(
                f"- **Combined SNR = {combined_snr:.1f}**: "
                "strong combined detection.\n"
            )
        elif combined_snr > 5:
            f.write(
                f"- **Combined SNR = {combined_snr:.1f}**: "
                "moderate combined detection.\n"
            )
        else:
            f.write(
                f"- **Combined SNR = {combined_snr:.1f}**: "
                "weak combined detection.\n"
            )

        f.write("\n## Cautions\n")
        non_detrended = [
            r.sector for r in all_success if not r.detrending_used
        ]
        if non_detrended:
            f.write(
                f"- Sectors {non_detrended} used lightkurve flatten "
                "instead of AstroTransit detrending.\n"
            )
        f.write(
            "- Depth measurements are median-based and may differ "
            "from formal transit model fits.\n"
        )
        f.write(
            "- Odd-even test uses simple median depth comparison; "
            "formal EB diagnostic requires full model fitting.\n"
        )

    # ─── Konsol özeti ───
    print("\n" + "=" * 72)
    print("FORCED EPHEMERIS VALIDATION ÖZET")
    print("=" * 72)
    print(f"Sectors tested          : {len(SECTORS)}")
    print(f"Sectors successful      : {len(all_success)}")
    print(f"Sectors with detection  : {len(detected_sectors)}")
    print(f"Detected in             : {[r.sector for r in detected_sectors]}")
    print(f"Total expected transits : {total_expected}")
    print(f"Total in-transit points : {total_in_transit}")
    print(
        f"Weighted mean depth     : "
        f"{combined_depth:.1f} ± {combined_err:.1f} ppm"
    )
    print(f"Combined SNR            : {combined_snr:.2f}")
    print(f"All odd-even consistent : {all_odd_even_consistent}")

    non_detrended = [r.sector for r in all_success if not r.detrending_used]
    if non_detrended:
        print(f"⚠ lk.flatten fallback   : {non_detrended}")

    print("=" * 72)
    print(f"Saved: {json_path}")
    print(f"Saved: {csv_path}")
    print(f"Saved: {md_path}")
    print(f"Figures: {FIGURES_DIR}")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())