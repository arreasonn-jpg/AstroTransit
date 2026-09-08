"""
TIC 417860263 — Refined Multi-Sector Validation

Faz 1: S57+S58 transit-by-transit MAP-based timing
Faz 2: Lineer ephemeris refinement
Faz 3: Refined ephemeris ile 6 sektör forced validation
Faz 4: Raporlama
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from dataclasses import dataclass, asdict

import numpy as np
from scipy.optimize import minimize

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

# ─────────────────────────────────────────────
# Sabitler
# ─────────────────────────────────────────────
TIC_ID = "TIC 417860263"
HOST_NAME = "HD 224792"

PERIOD_INIT = 2.8535114704493703
T0_INIT = 2854.378905
DURATION_HOURS = 3.6246
DURATION_DAYS = DURATION_HOURS / 24.0
RP_RS = 0.025096

TIMING_SECTORS = [57, 58]
ALL_SECTORS = [57, 58, 77, 78, 84, 85]

OUT_DIR = Path("outputs_tic417860263_refined_validation")
OUT_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR = OUT_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
FIGURES_DIR = OUT_DIR / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────
# JSON sanitizer
# ─────────────────────────────────────────────
def to_jsonable(obj):
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
        return None if (np.isnan(obj) or np.isinf(obj)) else float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    return obj


# ─────────────────────────────────────────────
# Array yardımcıları
# ─────────────────────────────────────────────
def safe_array(arr) -> np.ndarray:
    if hasattr(arr, "value"):
        arr = arr.value
    if isinstance(arr, np.ma.MaskedArray):
        arr = arr.filled(np.nan)
    return np.array(arr, dtype=np.float64)


def get_detrended_data(sector: int) -> tuple[np.ndarray, np.ndarray, bool]:
    import lightkurve as lk

    sr = lk.search_lightcurve(
        TIC_ID, mission="TESS", author="SPOC",
        exptime=120, sector=sector,
    )
    if sr is None or len(sr) == 0:
        raise ValueError(f"S{sector}: no SPOC 120s data")

    lc = sr.download().remove_nans().remove_outliers(sigma=5.0)

    try:
        from astrotransit.data.tess_client import TESSClient
        from astrotransit.preprocessing.pipeline import TESSPreprocessingPipeline
        from astrotransit.settings import load_settings

        settings = load_settings(project_root / "configs" / "default.toml")
        client = TESSClient(author="SPOC", exptime=120, quality_bitmask="default")
        preproc = TESSPreprocessingPipeline(settings=settings)
        lc_data = client.get_lightcurve(TIC_ID, sector=sector)
        preprocessed = preproc.run(lc_data)

        time = safe_array(preprocessed.detrended.time)
        flux = safe_array(preprocessed.detrended.flux)
        valid = np.isfinite(time) & np.isfinite(flux)
        time, flux = time[valid], flux[valid]

        if len(time) > 100:
            return time, flux, True

    except Exception as e:
        print(f"  S{sector} AT detrend failed: {e}, using lk.flatten")

    lc_flat = lc.flatten(window_length=301).normalize()
    time = safe_array(lc_flat.time)
    flux = safe_array(lc_flat.flux)
    valid = np.isfinite(time) & np.isfinite(flux)
    return time[valid], flux[valid], False


# ─────────────────────────────────────────────
# Transit model (trapezoidal)
# ─────────────────────────────────────────────
def trapezoidal_transit(
    time: np.ndarray,
    t0: float,
    depth: float,
    duration: float,
    ingress_fraction: float = 0.15,
    baseline: float = 1.0,
) -> np.ndarray:
    """Trapezoid transit modeli — box'tan çok daha iyi."""
    model = np.full_like(time, baseline)
    half_dur = duration / 2.0
    ingress_dur = half_dur * ingress_fraction

    dt = np.abs(time - t0)

    # Tam transit (flat bottom)
    flat_mask = dt < (half_dur - ingress_dur)
    model[flat_mask] = baseline - depth

    # Ingress/egress (lineer geçiş)
    ing_mask = (dt >= (half_dur - ingress_dur)) & (dt < half_dur)
    if np.any(ing_mask):
        frac = (half_dur - dt[ing_mask]) / ingress_dur
        frac = np.clip(frac, 0.0, 1.0)
        model[ing_mask] = baseline - depth * frac

    return model


def fit_single_transit_t0(
    time: np.ndarray,
    flux: np.ndarray,
    t0_init: float,
    period: float,
    duration: float,
    rp_rs: float,
    search_range_hours: float = 2.0,
) -> dict:
    """
    Tek bir transit penceresi için t0'ı optimize eder.
    Trapezoidal model + scipy minimize.
    """
    search_range = search_range_hours / 24.0
    window = 2.5 * duration

    # Transit çevresindeki veriyi kes
    mask = np.abs(time - t0_init) < window
    t_local = time[mask]
    f_local = flux[mask]

    if len(t_local) < 15:
        return {"success": False, "error": "insufficient_data",
                "n_points": len(t_local)}

    # Baseline ve depth tahmini
    out_mask = np.abs(t_local - t0_init) > (duration / 2.0)
    in_mask = ~out_mask

    if np.sum(out_mask) < 5 or np.sum(in_mask) < 3:
        return {"success": False, "error": "insufficient_in_out",
                "n_points": len(t_local)}

    baseline = np.median(f_local[out_mask])
    depth_init = max(baseline - np.median(f_local[in_mask]), 1e-6)

    # t0 optimizasyonu
    def neg_loglike(t0_shift):
        t0_try = t0_init + t0_shift
        model = trapezoidal_transit(
            t_local, t0_try, depth_init, duration,
            ingress_fraction=0.15, baseline=baseline,
        )
        residuals = f_local - model
        sigma = np.std(f_local[out_mask])
        if sigma <= 0:
            sigma = 1e-6
        return 0.5 * np.sum((residuals / sigma) ** 2)

    # Coarse grid + fine optimize
    n_grid = 200
    shifts = np.linspace(-search_range, search_range, n_grid)
    chi2_grid = np.array([neg_loglike(s) for s in shifts])
    best_shift = shifts[np.argmin(chi2_grid)]

    # Fine optimization
    try:
        res = minimize(
            neg_loglike,
            x0=best_shift,
            method="Nelder-Mead",
            options={"xatol": 1e-6, "fatol": 1e-6, "maxiter": 2000},
        )
        best_shift = res.x[0]
        best_chi2 = res.fun
    except Exception:
        best_chi2 = neg_loglike(best_shift)

    t0_fit = t0_init + best_shift

    # Depth re-estimate at best t0
    in_fit = np.abs(t_local - t0_fit) < (duration / 2.0)
    out_fit = ~in_fit
    if np.sum(in_fit) >= 3 and np.sum(out_fit) >= 5:
        depth_fit = float(np.median(f_local[out_fit]) - np.median(f_local[in_fit]))
    else:
        depth_fit = float(depth_init)

    # t0 error estimate via curvature
    h = 0.0001  # gün = ~8.6 saniye
    chi2_plus = neg_loglike(best_shift + h)
    chi2_minus = neg_loglike(best_shift - h)
    chi2_center = neg_loglike(best_shift)

    d2chi2 = (chi2_plus - 2 * chi2_center + chi2_minus) / (h ** 2)

    if d2chi2 > 0:
        t0_err = 1.0 / np.sqrt(d2chi2)
    else:
        t0_err = 0.005  # fallback ~7 dakika

    # Sanity check
    t0_err = min(t0_err, 0.05)  # max ~72 dakika
    t0_err = max(t0_err, 0.0001)  # min ~8.6 saniye

    depth_ppm = depth_fit * 1e6 if depth_fit < 0.01 else depth_fit

    return {
        "success": True,
        "t0_fit": float(t0_fit),
        "t0_err": float(t0_err),
        "depth": float(depth_fit),
        "depth_ppm": float(depth_ppm),
        "chi2": float(best_chi2),
        "n_points": int(len(t_local)),
        "n_in_transit": int(np.sum(in_fit)),
        "baseline": float(baseline),
    }


# ─────────────────────────────────────────────
# Lineer ephemeris fit
# ─────────────────────────────────────────────
def fit_linear_ephemeris(epochs, t_centers, t_errors):
    epochs = np.array(epochs, dtype=np.float64)
    t_centers = np.array(t_centers, dtype=np.float64)
    t_errors = np.array(t_errors, dtype=np.float64)

    t_errors = np.maximum(t_errors, 0.0001)
    w = 1.0 / (t_errors ** 2)
    w_sum = np.sum(w)

    n_mean = np.sum(w * epochs) / w_sum
    t_mean = np.sum(w * t_centers) / w_sum

    Snn = np.sum(w * (epochs - n_mean) ** 2)
    Snt = np.sum(w * (epochs - n_mean) * (t_centers - t_mean))

    P = Snt / Snn
    T0 = t_mean - P * n_mean

    t_calc = T0 + P * epochs
    residuals = t_centers - t_calc
    residuals_min = residuals * 24.0 * 60.0

    chi2 = np.sum(w * residuals ** 2)
    n_dof = max(len(epochs) - 2, 1)
    s2 = max(chi2 / n_dof, 1.0)
    P_err = np.sqrt(s2 / Snn)
    T0_err = np.sqrt(s2 * (1.0 / w_sum + n_mean**2 / Snn))

    return {
        "T0": float(T0), "T0_err": float(T0_err),
        "P": float(P), "P_err": float(P_err),
        "chi2": float(chi2), "n_dof": int(n_dof),
        "reduced_chi2": float(chi2 / n_dof),
        "residuals_minutes": [float(x) for x in residuals_min],
        "rms_residual_minutes": float(np.std(residuals_min)),
    }


# ─────────────────────────────────────────────
# Forced ephemeris validation
# ─────────────────────────────────────────────
@dataclass
class SectorValidation:
    sector: int
    success: bool = False
    error: str = ""
    detrending_used: bool = False
    n_points: int = 0
    time_span_days: float = 0.0
    expected_transits: int = 0
    n_in_transit: int = 0
    n_out_transit: int = 0
    depth_ppm: float = 0.0
    depth_err_ppm: float = 0.0
    sector_snr: float = 0.0
    transit_detected: bool = False
    depth_odd_ppm: float = 0.0
    depth_even_ppm: float = 0.0
    odd_even_diff_ppm: float = 0.0
    odd_even_consistent: bool = True


def phase_fold(time, period, t0):
    return ((time - t0) / period) % 1.0


def validate_sector_forced(
    sector: int, period: float, t0: float
) -> SectorValidation:
    sv = SectorValidation(sector=sector)

    try:
        time, flux, detrended = get_detrended_data(sector)
        sv.detrending_used = detrended
        sv.n_points = int(len(time))
        sv.time_span_days = float(time[-1] - time[0])

        first_ep = max(0, int(np.ceil((time[0] - t0) / period)))
        last_ep = int(np.floor((time[-1] - t0) / period))
        sv.expected_transits = max(0, last_ep - first_ep + 1)

        phase = phase_fold(time, period, t0)
        dur_phase = DURATION_DAYS / period
        half_dur = dur_phase / 2.0
        transit_mask = (phase < half_dur) | (phase > (1.0 - half_dur))

        flux_in = flux[transit_mask]
        flux_out = flux[~transit_mask]
        sv.n_in_transit = int(len(flux_in))
        sv.n_out_transit = int(len(flux_out))

        if len(flux_in) < 3 or len(flux_out) < 10:
            sv.error = "insufficient points"
            return sv

        median_out = np.median(flux_out)
        median_in = np.median(flux_in)
        if median_out == 0:
            sv.error = "zero baseline"
            return sv

        depth = (median_out - median_in) / median_out * 1e6
        scatter_in = np.std(flux_in) / np.sqrt(len(flux_in)) / median_out * 1e6
        scatter_out = np.std(flux_out) / np.sqrt(len(flux_out)) / median_out * 1e6
        depth_err = np.sqrt(scatter_in**2 + scatter_out**2)

        sv.depth_ppm = float(depth)
        sv.depth_err_ppm = float(depth_err)
        sv.sector_snr = float(depth / depth_err) if depth_err > 0 else 0.0
        sv.transit_detected = depth > 0 and sv.sector_snr > 3.0

        # Odd-even
        transit_nums = np.round((time - t0) / period).astype(int)
        odd_mask = transit_mask & ((transit_nums % 2) != 0)
        even_mask = transit_mask & ((transit_nums % 2) == 0)

        f_odd = flux[odd_mask]
        f_even = flux[even_mask]

        if len(f_odd) >= 3 and len(f_even) >= 3:
            d_odd = (median_out - np.median(f_odd)) / median_out * 1e6
            d_even = (median_out - np.median(f_even)) / median_out * 1e6
            sv.depth_odd_ppm = float(d_odd)
            sv.depth_even_ppm = float(d_even)
            sv.odd_even_diff_ppm = float(abs(d_odd - d_even))
            sv.odd_even_consistent = sv.odd_even_diff_ppm < (3.0 * depth_err) if depth_err > 0 else True

        sv.success = True

    except Exception as e:
        sv.error = str(e)

    return sv


# ─────────────────────────────────────────────
# Görseller
# ─────────────────────────────────────────────
def plot_oc(epochs, residuals_min, t_errors_min, refined):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.errorbar(epochs, residuals_min, yerr=t_errors_min,
                     fmt="o", color="steelblue", ecolor="gray",
                     capsize=3, markersize=6)
        ax.axhline(0, color="red", ls="--", alpha=0.5)
        ax.set_xlabel("Epoch")
        ax.set_ylabel("O - C (minutes)")
        ax.set_title(
            f"TIC 417860263 — O-C Diagram\n"
            f"P = {refined['P']:.8f} ± {refined['P_err']:.8f} d"
        )
        rms = refined["rms_residual_minutes"]
        ax.text(0.02, 0.95,
                f"RMS = {rms:.2f} min\nχ²_red = {refined['reduced_chi2']:.2f}",
                transform=ax.transAxes, fontsize=10,
                va="top", bbox=dict(boxstyle="round", fc="wheat", alpha=0.5))

        path = FIGURES_DIR / "OC_diagram.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  Figure: {path}")
    except Exception as e:
        print(f"  O-C plot failed: {e}")


def plot_phase_fold(sector, period, t0):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        time, flux, det = get_detrended_data(sector)
        phase = phase_fold(time, period, t0)
        phase = np.where(phase > 0.5, phase - 1.0, phase)

        dur_phase = DURATION_DAYS / period

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.scatter(phase, flux, s=1, alpha=0.3, color="gray")

        n_bins = 100
        edges = np.linspace(-0.5, 0.5, n_bins + 1)
        centers = 0.5 * (edges[:-1] + edges[1:])
        binned = np.full(n_bins, np.nan)
        for i in range(n_bins):
            m = (phase >= edges[i]) & (phase < edges[i+1])
            if np.sum(m) > 3:
                binned[i] = np.median(flux[m])
        ax.plot(centers, binned, "r-", lw=1.5)
        ax.axvline(-dur_phase/2, color="blue", ls="--", alpha=0.5)
        ax.axvline(dur_phase/2, color="blue", ls="--", alpha=0.5)
        ax.set_xlim(-0.15, 0.15)
        dt = "AT" if det else "lk"
        ax.set_title(f"S{sector} — P={period:.7f} d [{dt}]")
        ax.set_xlabel("Phase")
        ax.set_ylabel("Flux")

        path = FIGURES_DIR / f"phasefold_S{sector:02d}.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  Figure: {path}")
    except Exception as e:
        print(f"  Phase fold S{sector} failed: {e}")


# ─────────────────────────────────────────────
# Ana fonksiyon
# ─────────────────────────────────────────────
def main():
    print("=" * 72)
    print("TIC 417860263 — Refined Multi-Sector Validation")
    print("=" * 72)

    # ═══════════════════════════════════════════
    # FAZ 1: Transit-by-transit timing
    # ═══════════════════════════════════════════
    print("\n" + "─" * 40)
    print("FAZ 1: Transit-by-transit MAP timing")
    print("─" * 40)

    all_measurements = []

    for sector in TIMING_SECTORS:
        print(f"\n── S{sector} ──")
        time, flux, det = get_detrended_data(sector)
        dt_label = "AT" if det else "lk"
        print(f"  Detrend: {dt_label}, points: {len(time)}")

        first_ep = int(np.ceil((time[0] - T0_INIT) / PERIOD_INIT))
        last_ep = int(np.floor((time[-1] - T0_INIT) / PERIOD_INIT))

        for epoch in range(first_ep, last_ep + 1):
            expected_tc = T0_INIT + epoch * PERIOD_INIT

            if expected_tc < time[0] + DURATION_DAYS or \
               expected_tc > time[-1] - DURATION_DAYS:
                continue

            result = fit_single_transit_t0(
                time, flux, expected_tc, PERIOD_INIT,
                DURATION_DAYS, RP_RS, search_range_hours=2.0,
            )

            if result["success"] and result["depth"] > 0:
                print(
                    f"    Epoch {epoch:3d}: "
                    f"Tc={result['t0_fit']:.6f} ± {result['t0_err']:.6f} d, "
                    f"depth={result['depth_ppm']:.0f} ppm, "
                    f"n={result['n_points']}"
                )
                all_measurements.append({
                    "sector": sector,
                    "epoch": epoch,
                    **result,
                })
            else:
                reason = result.get("error", "negative depth")
                print(f"    Epoch {epoch:3d}: skipped ({reason})")

    print(f"\n  Total transit measurements: {len(all_measurements)}")

    if len(all_measurements) < 4:
        print("HATA: Yetersiz transit — durduruluyor.")
        return 1

    # ═══════════════════════════════════════════
    # FAZ 2: Ephemeris refinement
    # ═══════════════════════════════════════════
    print("\n" + "─" * 40)
    print("FAZ 2: Lineer Ephemeris Refinement")
    print("─" * 40)

    # Outlier rejection: iterative 3-sigma clip
    epochs_all = [m["epoch"] for m in all_measurements]
    tc_all = [m["t0_fit"] for m in all_measurements]
    err_all = [m["t0_err"] for m in all_measurements]

    for iteration in range(3):
        eph = fit_linear_ephemeris(epochs_all, tc_all, err_all)
        resid = np.array(eph["residuals_minutes"])
        rms = np.std(resid)

        keep = np.abs(resid) < 3.0 * rms
        n_before = len(epochs_all)

        epochs_all = [e for e, k in zip(epochs_all, keep) if k]
        tc_all = [t for t, k in zip(tc_all, keep) if k]
        err_all = [r for r, k in zip(err_all, keep) if k]

        n_clipped = n_before - len(epochs_all)
        print(f"  Iteration {iteration+1}: {n_clipped} outliers clipped, {len(epochs_all)} remaining")

        if n_clipped == 0:
            break

    refined = fit_linear_ephemeris(epochs_all, tc_all, err_all)

    delta_p_sec = (refined["P"] - PERIOD_INIT) * 86400.0

    print(f"\n  Refined T0     : {refined['T0']:.8f} ± {refined['T0_err']:.8f} BTJD")
    print(f"  Refined Period : {refined['P']:.10f} ± {refined['P_err']:.10f} d")
    print(f"  ΔP             : {delta_p_sec:+.4f} s")
    print(f"  Reduced χ²     : {refined['reduced_chi2']:.2f}")
    print(f"  RMS residual   : {refined['rms_residual_minutes']:.2f} min")
    print(f"  Transits used  : {len(epochs_all)}")

    # O-C plot
    t_errors_min = [e * 24 * 60 for e in err_all]
    plot_oc(np.array(epochs_all), refined["residuals_minutes"], t_errors_min, refined)

    # ═══════════════════════════════════════════
    # FAZ 3: Refined ephemeris ile 6-sector validation
    # ═══════════════════════════════════════════
    print("\n" + "─" * 40)
    print("FAZ 3: Refined Ephemeris Forced Validation (6 sectors)")
    print("─" * 40)

    P_ref = refined["P"]
    T0_ref = refined["T0"]

    sector_results = []

    for sector in ALL_SECTORS:
        print(f"\n── S{sector} ──")
        sv = validate_sector_forced(sector, P_ref, T0_ref)
        sector_results.append(sv)

        if sv.success:
            det_label = "AT" if sv.detrending_used else "lk"
            det_flag = "YES" if sv.transit_detected else "no"
            oe_flag = "✓" if sv.odd_even_consistent else "✗"
            print(
                f"  [{det_label}] depth={sv.depth_ppm:.1f}±{sv.depth_err_ppm:.1f} ppm, "
                f"SNR={sv.sector_snr:.2f}, detected={det_flag}, OE={oe_flag}"
            )
        else:
            print(f"  FAILED: {sv.error}")

        # Phase fold
        plot_phase_fold(sector, P_ref, T0_ref)

    # ═══════════════════════════════════════════
    # FAZ 4: Raporlama
    # ═══════════════════════════════════════════
    print("\n" + "─" * 40)
    print("FAZ 4: Raporlama")
    print("─" * 40)

    detected = [s for s in sector_results if s.success and s.transit_detected]
    all_ok = [s for s in sector_results if s.success]

    # Combined depth
    wd, ws = 0.0, 0.0
    for s in all_ok:
        if s.depth_err_ppm > 0:
            w = 1.0 / (s.depth_err_ppm ** 2)
            wd += s.depth_ppm * w
            ws += w
    comb_depth = wd / ws if ws > 0 else 0.0
    comb_err = 1.0 / np.sqrt(ws) if ws > 0 else 0.0
    comb_snr = comb_depth / comb_err if comb_err > 0 else 0.0

    all_oe_ok = all(s.odd_even_consistent for s in all_ok)

    report = {
        "target": TIC_ID,
        "host_name": HOST_NAME,
        "initial_ephemeris": {"T0": T0_INIT, "P": PERIOD_INIT},
        "refined_ephemeris": {
            "T0": refined["T0"], "T0_err": refined["T0_err"],
            "P": refined["P"], "P_err": refined["P_err"],
            "delta_P_seconds": delta_p_sec,
            "reduced_chi2": refined["reduced_chi2"],
            "rms_residual_minutes": refined["rms_residual_minutes"],
            "n_transits_used": len(epochs_all),
            "n_transits_clipped": len(all_measurements) - len(epochs_all),
        },
        "forced_validation": {
            "sectors_tested": ALL_SECTORS,
            "sectors_detected": [s.sector for s in detected],
            "combined_depth_ppm": round(float(comb_depth), 2),
            "combined_depth_err_ppm": round(float(comb_err), 2),
            "combined_snr": round(float(comb_snr), 2),
            "all_odd_even_consistent": all_oe_ok,
        },
        "per_sector": [asdict(s) for s in sector_results],
        "transit_measurements": all_measurements,
    }

    # JSON
    jp = REPORTS_DIR / "TIC_417860263_refined_validation.json"
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(to_jsonable(report), f, indent=2, ensure_ascii=False)

    # MD
    mp = REPORTS_DIR / "TIC_417860263_refined_validation.md"
    with open(mp, "w", encoding="utf-8") as f:
        f.write("# TIC 417860263 — Refined Multi-Sector Validation\n\n")

        f.write("## Ephemeris Refinement (S57+S58)\n")
        f.write(f"- **Initial T0**: {T0_INIT:.6f} BTJD\n")
        f.write(f"- **Initial P**: {PERIOD_INIT:.10f} d\n")
        f.write(f"- **Refined T0**: {refined['T0']:.8f} ± {refined['T0_err']:.8f} BTJD\n")
        f.write(f"- **Refined P**: {refined['P']:.10f} ± {refined['P_err']:.10f} d\n")
        f.write(f"- **ΔP**: {delta_p_sec:+.4f} seconds\n")
        f.write(f"- **Reduced χ²**: {refined['reduced_chi2']:.2f}\n")
        f.write(f"- **RMS residual**: {refined['rms_residual_minutes']:.2f} min\n")
        f.write(f"- **Transits used**: {len(epochs_all)} (clipped: {len(all_measurements)-len(epochs_all)})\n\n")

        f.write("## Forced Validation with Refined Ephemeris\n\n")
        f.write(f"- **Sectors tested**: {len(ALL_SECTORS)}\n")
        f.write(f"- **Sectors with detection**: {len(detected)}\n")
        f.write(f"- **Detected in**: {[s.sector for s in detected]}\n")
        f.write(f"- **Combined depth**: {comb_depth:.1f} ± {comb_err:.1f} ppm\n")
        f.write(f"- **Combined SNR**: {comb_snr:.2f}\n")
        f.write(f"- **All odd-even consistent**: {all_oe_ok}\n\n")

        f.write("### Per-Sector\n\n")
        f.write("| Sector | Detrend | Depth (ppm) | Err | SNR | Detected | Odd | Even | Diff | OE |\n")
        f.write("|---:|:---:|---:|---:|---:|:---:|---:|---:|---:|:---:|\n")
        for s in sector_results:
            if s.success:
                dt = "AT" if s.detrending_used else "lk"
                f.write(
                    f"| {s.sector} | {dt} | {s.depth_ppm:.1f} | {s.depth_err_ppm:.1f} "
                    f"| {s.sector_snr:.2f} | {'✓' if s.transit_detected else '✗'} "
                    f"| {s.depth_odd_ppm:.1f} | {s.depth_even_ppm:.1f} "
                    f"| {s.odd_even_diff_ppm:.1f} | {'✓' if s.odd_even_consistent else '✗'} |\n"
                )
            else:
                f.write(f"| {s.sector} | — | — | — | — | ✗ | — | — | — | — |\n")

        f.write("\n## Interpretation\n")
        if len(detected) >= 4:
            f.write(f"- **Strong multi-sector support**: {len(detected)}/{len(ALL_SECTORS)} sectors.\n")
        elif len(detected) >= 2:
            f.write(f"- **Partial multi-sector support**: {len(detected)}/{len(ALL_SECTORS)} sectors.\n")
        else:
            f.write(f"- **Weak/single-sector support**: {len(detected)}/{len(ALL_SECTORS)} sectors.\n")

        if all_oe_ok:
            f.write("- **Odd-even consistent**: no eclipsing binary signature.\n")
        else:
            bad = [s.sector for s in all_ok if not s.odd_even_consistent]
            f.write(f"- **Odd-even warning**: sectors {bad}.\n")

        if comb_snr > 10:
            f.write(f"- **Combined SNR = {comb_snr:.1f}**: strong.\n")
        elif comb_snr > 5:
            f.write(f"- **Combined SNR = {comb_snr:.1f}**: moderate.\n")
        else:
            f.write(f"- **Combined SNR = {comb_snr:.1f}**: weak.\n")

    print(f"\nSaved: {jp}")
    print(f"Saved: {mp}")

    # Konsol özeti
    print("\n" + "=" * 72)
    print("FINAL ÖZET")
    print("=" * 72)
    print(f"Refined P  : {refined['P']:.10f} ± {refined['P_err']:.10f} d")
    print(f"Refined T0 : {refined['T0']:.8f} ± {refined['T0_err']:.8f}")
    print(f"ΔP         : {delta_p_sec:+.4f} s")
    print(f"RMS O-C    : {refined['rms_residual_minutes']:.2f} min")
    print(f"Detected   : {[s.sector for s in detected]}")
    print(f"Comb depth : {comb_depth:.1f} ± {comb_err:.1f} ppm")
    print(f"Comb SNR   : {comb_snr:.2f}")
    print(f"OE all ok  : {all_oe_ok}")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())