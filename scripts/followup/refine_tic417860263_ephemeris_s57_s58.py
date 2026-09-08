"""
TIC 417860263 — S57+S58 Ephemeris Refinement

S57 ve S58 verilerini kullanarak:
  - her iki sektördeki bireysel transit merkezlerini ölç
  - lineer ephemeris fit yap (T0 + n*P)
  - refined period ve t0 üret
  - residuals (O-C) raporla
  - sonuçları JSON / MD olarak kaydet
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

# ─────────────────────────────────────────────
# Sabitler (mevcut en iyi ephemeris)
# ─────────────────────────────────────────────
TIC_ID = "TIC 417860263"
HOST_NAME = "HD 224792"

# S57 MAP+MCMC değerleri (başlangıç tahmini)
PERIOD_INIT = 2.8535114704493703
T0_INIT = 2854.378905

DURATION_HOURS = 3.6246
DURATION_DAYS = DURATION_HOURS / 24.0
RP_RS = 0.025096

REFINE_SECTORS = [57, 58]

OUT_DIR = Path("outputs_tic417860263_ephemeris_refine")
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
# Yardımcı fonksiyonlar
# ─────────────────────────────────────────────
def safe_array(arr) -> np.ndarray:
    if hasattr(arr, "value"):
        arr = arr.value
    if isinstance(arr, np.ma.MaskedArray):
        arr = arr.filled(np.nan)
    arr = np.array(arr, dtype=np.float64)
    return arr


def get_detrended_data(sector: int) -> tuple[np.ndarray, np.ndarray]:
    """AstroTransit detrending ile veri al."""
    import lightkurve as lk

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
        time = time[valid]
        flux = flux[valid]

        if len(time) > 100:
            print(f"  S{sector}: AstroTransit detrending OK ({len(time)} points)")
            return time, flux

    except Exception as e:
        print(f"  S{sector}: AstroTransit detrending failed: {e}")
        print(f"  S{sector}: Falling back to lightkurve flatten...")

    # Fallback
    sr = lk.search_lightcurve(
        TIC_ID, mission="TESS", author="SPOC", exptime=120, sector=sector,
    )
    if sr is None or len(sr) == 0:
        raise ValueError(f"S{sector}: no SPOC 120s data found")

    lc = sr.download().remove_nans().remove_outliers(sigma=5.0)
    lc_flat = lc.flatten(window_length=301).normalize()

    time = safe_array(lc_flat.time)
    flux = safe_array(lc_flat.flux)
    valid = np.isfinite(time) & np.isfinite(flux)

    return time[valid], flux[valid]


def simple_transit_model(
    time: np.ndarray,
    t_center: float,
    depth: float,
    duration: float,
    baseline: float = 1.0,
) -> np.ndarray:
    """Basit box transit modeli."""
    model = np.full_like(time, baseline)
    half_dur = duration / 2.0
    in_transit = np.abs(time - t_center) < half_dur
    model[in_transit] = baseline - depth
    return model


def fit_transit_center(
    time: np.ndarray,
    flux: np.ndarray,
    t_center_init: float,
    depth_init: float,
    duration: float,
    search_range_hours: float = 3.0,
) -> tuple[float, float, float]:
    """
    Brute-force + fine grid ile transit merkezini bulur.

    Returns:
        (best_t_center, best_depth, best_chi2)
    """
    search_range = search_range_hours / 24.0
    half_dur = duration / 2.0

    # Coarse search: ±search_range, 1 dakika adım
    n_coarse = int(2 * search_range * 24 * 60) + 1
    t_trials = np.linspace(
        t_center_init - search_range,
        t_center_init + search_range,
        n_coarse,
    )

    # Her trial için transit penceresi içindeki veriyi kullanarak depth ve chi2 hesapla
    best_t = t_center_init
    best_chi2 = np.inf
    best_depth = depth_init

    _baseline = np.median(flux)

    for t_try in t_trials:
        in_mask = np.abs(time - t_try) < half_dur
        out_mask = ~in_mask

        if np.sum(in_mask) < 5 or np.sum(out_mask) < 20:
            continue

        median_in = np.median(flux[in_mask])
        median_out = np.median(flux[out_mask])
        depth_try = median_out - median_in

        if depth_try <= 0:
            continue

        model = simple_transit_model(time, t_try, depth_try, duration, median_out)
        residuals = flux - model
        chi2 = np.sum(residuals**2)

        if chi2 < best_chi2:
            best_chi2 = chi2
            best_t = t_try
            best_depth = depth_try

    # Fine search: best ± 5 dakika, 6 saniyelik adım
    fine_range = 5.0 / (24.0 * 60.0)
    n_fine = 100
    t_fine = np.linspace(best_t - fine_range, best_t + fine_range, n_fine)

    for t_try in t_fine:
        in_mask = np.abs(time - t_try) < half_dur
        out_mask = ~in_mask

        if np.sum(in_mask) < 5 or np.sum(out_mask) < 20:
            continue

        median_in = np.median(flux[in_mask])
        median_out = np.median(flux[out_mask])
        depth_try = median_out - median_in

        if depth_try <= 0:
            continue

        model = simple_transit_model(time, t_try, depth_try, duration, median_out)
        residuals = flux - model
        chi2 = np.sum(residuals**2)

        if chi2 < best_chi2:
            best_chi2 = chi2
            best_t = t_try
            best_depth = depth_try

    return best_t, best_depth, best_chi2


def estimate_t_center_error(
    time: np.ndarray,
    flux: np.ndarray,
    t_center: float,
    depth: float,
    duration: float,
    n_bootstrap: int = 200,
) -> float:
    """Bootstrap ile transit merkezi belirsizliğini tahmin et."""
    half_dur = duration / 2.0
    window = np.abs(time - t_center) < (2.0 * half_dur)

    time_w = time[window]
    flux_w = flux[window]

    if len(time_w) < 10:
        return 0.001  # fallback

    rng = np.random.default_rng(42)
    centers = []

    for _ in range(n_bootstrap):
        idx = rng.integers(0, len(time_w), size=len(time_w))
        t_boot = time_w[idx]
        f_boot = flux_w[idx]

        sort_idx = np.argsort(t_boot)
        t_boot = t_boot[sort_idx]
        f_boot = f_boot[sort_idx]

        try:
            tc, _, _ = fit_transit_center(
                t_boot, f_boot, t_center, depth, duration,
                search_range_hours=1.0,
            )
            centers.append(tc)
        except Exception:
            pass

    if len(centers) < 10:
        return 0.001  # fallback

    return float(np.std(centers))


# ─────────────────────────────────────────────
# Lineer ephemeris fit
# ─────────────────────────────────────────────
def fit_linear_ephemeris(
    epochs: np.ndarray,
    t_centers: np.ndarray,
    t_errors: np.ndarray,
) -> dict:
    """
    Weighted linear least squares: T(n) = T0 + n * P

    Returns:
        {T0, T0_err, P, P_err, chi2, residuals_minutes}
    """
    # Ağırlıklar
    w = 1.0 / (t_errors ** 2)
    w_sum = np.sum(w)

    # Weighted means
    n_mean = np.sum(w * epochs) / w_sum
    t_mean = np.sum(w * t_centers) / w_sum

    # Weighted regression
    Snn = np.sum(w * (epochs - n_mean) ** 2)
    Snt = np.sum(w * (epochs - n_mean) * (t_centers - t_mean))

    P = Snt / Snn
    T0 = t_mean - P * n_mean

    # Residuals
    t_calc = T0 + P * epochs
    residuals = t_centers - t_calc
    residuals_min = residuals * 24.0 * 60.0  # dakika

    # Parameter errors
    chi2 = np.sum(w * residuals ** 2)
    n_dof = len(epochs) - 2

    if n_dof > 0:
        # reduced chi2 scale factor eğer gerekliyse
        s2 = chi2 / n_dof if chi2 / n_dof > 1.0 else 1.0
        P_err = np.sqrt(s2 / Snn)
        T0_err = np.sqrt(s2 * (1.0 / w_sum + n_mean**2 / Snn))
    else:
        P_err = 0.0
        T0_err = 0.0

    return {
        "T0": float(T0),
        "T0_err": float(T0_err),
        "P": float(P),
        "P_err": float(P_err),
        "chi2": float(chi2),
        "n_dof": int(n_dof),
        "reduced_chi2": float(chi2 / n_dof) if n_dof > 0 else 0.0,
        "residuals_minutes": [float(x) for x in residuals_min],
        "rms_residual_minutes": float(np.std(residuals_min)),
    }


# ─────────────────────────────────────────────
# O-C görseli
# ─────────────────────────────────────────────
def plot_oc_diagram(
    epochs: np.ndarray,
    residuals_min: list[float],
    t_errors_min: list[float],
    refined: dict,
):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(10, 5))

        ax.errorbar(
            epochs, residuals_min, yerr=t_errors_min,
            fmt="o", color="steelblue", ecolor="gray",
            capsize=3, markersize=6, label="O-C",
        )

        ax.axhline(0, color="red", ls="--", alpha=0.5)

        ax.set_xlabel("Epoch (transit number)")
        ax.set_ylabel("O - C (minutes)")
        ax.set_title(
            f"TIC 417860263 — O-C Diagram (S57+S58)\n"
            f"Refined P = {refined['P']:.8f} ± {refined['P_err']:.8f} d, "
            f"T0 = {refined['T0']:.6f} ± {refined['T0_err']:.6f} BTJD"
        )
        ax.legend()

        rms = refined["rms_residual_minutes"]
        ax.text(
            0.02, 0.95,
            f"RMS = {rms:.2f} min\nReduced χ² = {refined['reduced_chi2']:.2f}",
            transform=ax.transAxes, fontsize=10,
            verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
        )

        fig_path = FIGURES_DIR / "TIC_417860263_OC_diagram_S57_S58.png"
        fig.savefig(fig_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  Figure: {fig_path}")

    except Exception as e:
        print(f"  O-C figure failed: {e}")


# ─────────────────────────────────────────────
# Ana fonksiyon
# ─────────────────────────────────────────────
def main():
    print("=" * 72)
    print("TIC 417860263 — Ephemeris Refinement (S57+S58)")
    print("=" * 72)
    print(f"Initial Period  : {PERIOD_INIT:.10f} d")
    print(f"Initial T0      : {T0_INIT:.6f} BTJD")
    print(f"Duration        : {DURATION_HOURS:.4f} hrs")
    print(f"Sectors         : {REFINE_SECTORS}")
    print("=" * 72)

    all_transit_measurements = []

    for sector in REFINE_SECTORS:
        print(f"\n── Loading Sector {sector} ──")
        time, flux = get_detrended_data(sector)

        # Bu sektördeki beklenen transit merkezlerini hesapla
        first_epoch = int(np.ceil((time[0] - T0_INIT) / PERIOD_INIT))
        last_epoch = int(np.floor((time[-1] - T0_INIT) / PERIOD_INIT))

        print(f"  Epochs in sector: {first_epoch} to {last_epoch}")

        depth_init = RP_RS ** 2  # yaklaşık

        for epoch in range(first_epoch, last_epoch + 1):
            expected_tc = T0_INIT + epoch * PERIOD_INIT

            # Bu transit, veri penceresinde mi?
            if expected_tc < time[0] + DURATION_DAYS or \
               expected_tc > time[-1] - DURATION_DAYS:
                continue

            # Transit penceresi civarındaki veriyi kes
            window = 3.0 * DURATION_DAYS
            mask = np.abs(time - expected_tc) < window
            if np.sum(mask) < 20:
                continue

            t_local = time[mask]
            f_local = flux[mask]

            try:
                tc_fit, depth_fit, chi2_fit = fit_transit_center(
                    t_local, f_local, expected_tc, depth_init,
                    DURATION_DAYS, search_range_hours=2.0,
                )

                # Çok kötü fit'leri filtrele
                if depth_fit <= 0:
                    print(f"    Epoch {epoch}: negative depth, skipping")
                    continue

                # Bootstrap error
                tc_err = estimate_t_center_error(
                    t_local, f_local, tc_fit, depth_fit,
                    DURATION_DAYS, n_bootstrap=150,
                )

                depth_ppm = depth_fit * 1e6 if depth_fit < 0.01 else depth_fit

                print(
                    f"    Epoch {epoch}: "
                    f"Tc = {tc_fit:.6f} ± {tc_err:.6f} d, "
                    f"depth ~ {depth_ppm:.1f} ppm"
                )

                all_transit_measurements.append({
                    "sector": sector,
                    "epoch": epoch,
                    "t_center": tc_fit,
                    "t_center_err": tc_err,
                    "depth": depth_fit,
                    "chi2": chi2_fit,
                })

            except Exception as e:
                print(f"    Epoch {epoch}: fit failed: {e}")

    # ─── Lineer ephemeris fit ───
    if len(all_transit_measurements) < 3:
        print("\nYetersiz transit ölçümü — ephemeris refine edilemiyor.")
        return 1

    epochs = np.array([m["epoch"] for m in all_transit_measurements])
    t_centers = np.array([m["t_center"] for m in all_transit_measurements])
    t_errors = np.array([m["t_center_err"] for m in all_transit_measurements])

    # Çok küçük hatalara alt sınır koy
    t_errors = np.maximum(t_errors, 0.0001)

    print("\n── Lineer Ephemeris Fit ──")
    print(f"  Toplam transit ölçümü: {len(all_transit_measurements)}")

    refined = fit_linear_ephemeris(epochs, t_centers, t_errors)

    print(f"\n  Refined T0     : {refined['T0']:.8f} ± {refined['T0_err']:.8f} BTJD")
    print(f"  Refined Period : {refined['P']:.10f} ± {refined['P_err']:.10f} d")
    print(f"  Reduced χ²     : {refined['reduced_chi2']:.2f}")
    print(f"  RMS residual   : {refined['rms_residual_minutes']:.2f} min")

    # Period değişimi
    delta_p = refined["P"] - PERIOD_INIT
    delta_p_sec = delta_p * 86400.0
    print(f"\n  ΔP = {delta_p_sec:+.4f} s ({delta_p:+.10f} d)")
    print(f"  T0 shift = {(refined['T0'] - T0_INIT) * 24 * 60:+.4f} min")

    # ─── O-C görseli ───
    t_errors_min = [e * 24.0 * 60.0 for e in t_errors]
    plot_oc_diagram(epochs, refined["residuals_minutes"], t_errors_min, refined)

    # ─── Rapor oluştur ───
    report = {
        "target": TIC_ID,
        "host_name": HOST_NAME,
        "sectors_used": REFINE_SECTORS,
        "initial_ephemeris": {
            "T0": T0_INIT,
            "P": PERIOD_INIT,
            "source": "S57 MAP+MCMC",
        },
        "refined_ephemeris": {
            "T0": refined["T0"],
            "T0_err": refined["T0_err"],
            "P": refined["P"],
            "P_err": refined["P_err"],
            "delta_P_seconds": delta_p_sec,
            "reduced_chi2": refined["reduced_chi2"],
            "rms_residual_minutes": refined["rms_residual_minutes"],
            "n_transits_used": len(all_transit_measurements),
        },
        "transit_measurements": all_transit_measurements,
        "oc_residuals_minutes": refined["residuals_minutes"],
    }

    json_path = REPORTS_DIR / "TIC_417860263_ephemeris_refinement.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(to_jsonable(report), f, indent=2, ensure_ascii=False)

    md_path = REPORTS_DIR / "TIC_417860263_ephemeris_refinement.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TIC 417860263 — Ephemeris Refinement (S57+S58)\n\n")

        f.write("## Initial Ephemeris\n")
        f.write(f"- **T0**: {T0_INIT:.6f} BTJD\n")
        f.write(f"- **Period**: {PERIOD_INIT:.10f} d\n")
        f.write("- **Source**: S57 MAP+MCMC\n\n")

        f.write("## Refined Ephemeris\n")
        f.write(f"- **T0**: {refined['T0']:.8f} ± {refined['T0_err']:.8f} BTJD\n")
        f.write(f"- **Period**: {refined['P']:.10f} ± {refined['P_err']:.10f} d\n")
        f.write(f"- **ΔP**: {delta_p_sec:+.4f} seconds\n")
        f.write(f"- **Reduced χ²**: {refined['reduced_chi2']:.2f}\n")
        f.write(f"- **RMS residual**: {refined['rms_residual_minutes']:.2f} min\n")
        f.write(f"- **Transits used**: {len(all_transit_measurements)}\n\n")

        f.write("## Transit Measurements\n\n")
        f.write(
            "| Sector | Epoch | Tc (BTJD) | Tc_err (d) | "
            "O-C (min) |\n"
        )
        f.write(
            "|---:|---:|---:|---:|---:|\n"
        )
        for i, m in enumerate(all_transit_measurements):
            oc_min = refined["residuals_minutes"][i]
            f.write(
                f"| {m['sector']} "
                f"| {m['epoch']} "
                f"| {m['t_center']:.6f} "
                f"| {m['t_center_err']:.6f} "
                f"| {oc_min:+.2f} |\n"
            )

        f.write("\n## Interpretation\n")
        if refined["rms_residual_minutes"] < 5.0:
            f.write(
                f"- RMS residual ({refined['rms_residual_minutes']:.2f} min) "
                "is consistent with a well-determined ephemeris.\n"
            )
        else:
            f.write(
                f"- RMS residual ({refined['rms_residual_minutes']:.2f} min) "
                "is somewhat large; deeper transit timing analysis "
                "may be needed.\n"
            )

        if abs(delta_p_sec) < 1.0:
            f.write(
                f"- Period shift ({delta_p_sec:+.4f} s) is very small; "
                "initial ephemeris was already well constrained.\n"
            )
        elif abs(delta_p_sec) < 10.0:
            f.write(
                f"- Period shift ({delta_p_sec:+.4f} s) is modest; "
                "refinement should improve late-sector predictions.\n"
            )
        else:
            f.write(
                f"- Period shift ({delta_p_sec:+.4f} s) is significant; "
                "the initial single-sector period may have been "
                "insufficiently precise.\n"
            )

        f.write(
            "\n## Next Step\n"
            "- Re-run forced-ephemeris validation on all 6 sectors "
            "using the refined T0 and Period.\n"
            "- Pay special attention to Sectors 84–85 which were "
            "negative with the initial ephemeris.\n"
        )

    print(f"\nSaved: {json_path}")
    print(f"Saved: {md_path}")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())