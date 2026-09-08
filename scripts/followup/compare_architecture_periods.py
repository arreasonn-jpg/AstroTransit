#!/usr/bin/env python3
"""
Architecture Period Comparison Script

Amaç
----
Bir adayı birden fazla periyotla phase-fold ederek
L4/L5/shoulder sinyallerinin hangi fold'da güçlü,
hangisinde kaybolduğunu ölçer.

Bu analiz şu soruyu yanıtlar:
"Bu L5/L4 sinyali gerçek bir mimari yapı mı,
 yoksa yanlış fold/alias mı?"

Mantık:
    Gerçek mimari yapı → birden fazla fold'da anlamlı sinyal
    Alias artefaktı    → sadece bir fold'da anlamlı

Kullanım
--------
    python scripts/followup/compare_architecture_periods.py \
        --tic 357370384 \
        --sector 57 \
        --period 13.4939 \
        --tls-period 13.4939 \
        --bls-period 6.747 \
        --t0 2853.379 \
        --duration-hours 1.15
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from loguru import logger

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

try:
    import lightkurve as lk
except ImportError:
    raise ImportError("pip install lightkurve")

from scipy.interpolate import UnivariateSpline


# ─────────────────────────────────────────────────────────────
# LC yardımcıları
# ─────────────────────────────────────────────────────────────

def download_lc(tic_id: int, sector: int):
    search = lk.search_lightcurve(
        f"TIC {tic_id}", mission="TESS",
        author="SPOC", sector=sector, exptime=120,
    )
    if len(search) == 0:
        raise FileNotFoundError(f"TIC {tic_id} S{sector}: SPOC LC bulunamadı.")
    lc = search[0].download()
    time = np.array(lc.time.value, dtype=float)
    flux = np.array(getattr(lc.flux, "value", lc.flux), dtype=float)
    quality = np.array(getattr(lc.quality, "value", lc.quality), dtype=int)
    valid = np.isfinite(time) & np.isfinite(flux) & (quality == 0)
    time, flux = time[valid], flux[valid]
    med = np.nanmedian(flux)
    return time, flux / med


def detrend(time: np.ndarray, flux: np.ndarray, knot_days: float = 0.75) -> np.ndarray:
    knots = np.arange(time.min() + knot_days, time.max(), knot_days)
    if len(knots) < 4:
        return flux
    med = np.median(flux)
    std = np.std(flux)
    w = np.where(flux < (med - 2 * std), 0.05, 1.0)
    try:
        sp = UnivariateSpline(time, flux, w=w, k=3, s=len(time) * 0.4)
        trend = sp(time)
        trend = np.where(trend > 0, trend, 1.0)
        return flux / trend
    except Exception:
        return flux


# ─────────────────────────────────────────────────────────────
# Fold / bin
# ─────────────────────────────────────────────────────────────

def fold(time: np.ndarray, period: float, t0: float) -> np.ndarray:
    return ((time - t0 + 0.5 * period) % period) / period - 0.5


def bin_lc(phase: np.ndarray, flux: np.ndarray, bins: int = 250):
    edges = np.linspace(-0.5, 0.5, bins + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    medians = np.full(bins, np.nan)
    counts = np.zeros(bins, dtype=int)
    for i in range(bins):
        m = (phase >= edges[i]) & (phase < edges[i + 1])
        if m.sum() >= 2:
            medians[i] = np.median(flux[m])
            counts[i] = m.sum()
    return centers, medians, counts


# ─────────────────────────────────────────────────────────────
# Window scorer
# ─────────────────────────────────────────────────────────────

def score_window(
    phase: np.ndarray,
    flux: np.ndarray,
    center: float,
    half_width: float,
    min_pts: int = 8,
) -> dict:
    shifted = ((phase - center + 0.5) % 1.0) - 0.5
    in_w = np.abs(shifted) < half_width
    out_w = ~in_w

    n_in = int(in_w.sum())
    if n_in < min_pts:
        return {"n": n_in, "depth_ppm": 0.0, "sig": 0.0}

    out_flux = flux[out_w]
    in_flux = flux[in_w]
    baseline = np.nanmedian(out_flux) if len(out_flux) > 5 else 1.0
    sigma_out = np.nanstd(out_flux) if len(out_flux) > 5 else 1e-5

    depth_ppm = float((baseline - np.nanmedian(in_flux)) * 1e6)
    sig = float((depth_ppm / 1e6) / max(sigma_out, 1e-9) * np.sqrt(n_in))

    return {"n": n_in, "depth_ppm": round(depth_ppm, 1), "sig": round(sig, 2)}


def score_all_windows(
    phase: np.ndarray,
    flux: np.ndarray,
    dur_phase: float,
) -> dict:
    w = max(dur_phase * 1.5, 0.005)
    return {
        "primary":       score_window(phase, flux,  0.000, dur_phase),
        "secondary":     score_window(phase, flux,  0.500, dur_phase),
        "L4":            score_window(phase, flux, -0.1667, w),
        "L5":            score_window(phase, flux,  0.1667, w),
        "pre_shoulder":  score_window(phase, flux, -dur_phase * 1.8, dur_phase),
        "post_shoulder": score_window(phase, flux,  dur_phase * 1.8, dur_phase),
        "leading_L4":    score_window(phase, flux, -0.25, w),
        "trailing_L5":   score_window(phase, flux,  0.25, w),
    }


# ─────────────────────────────────────────────────────────────
# Architecture stability index
# ─────────────────────────────────────────────────────────────

def architecture_stability(results: dict) -> dict:
    """
    Farklı fold'larda L4/L5 sinyal tutarlılığını ölçer.

    Yüksek ASI → sinyal birden fazla fold'da güçlü → gerçek mimari
    Düşük  ASI → sinyal sadece bir fold'da var → alias ihtimali yüksek
    """
    l4_sigs = []
    l5_sigs = []

    for label, r in results.items():
        sc = r["scores"]
        l4_sigs.append(abs(sc["L4"]["sig"]))
        l5_sigs.append(abs(sc["L5"]["sig"]))

    def consistency(sigs):
        if len(sigs) < 2:
            return 0.0
        arr = np.array(sigs)
        if arr.max() < 1.5:
            return 0.0
        # Tutarlılık = alt sinyallerin üst sinyale oranı
        top = np.percentile(arr, 80)
        med = np.median(arr)
        return float(np.clip(med / max(top, 0.1), 0.0, 1.0))

    l4_asi = consistency(l4_sigs)
    l5_asi = consistency(l5_sigs)

    # En güçlü sinyalleri bul
    best_l4 = max(results, key=lambda x: abs(results[x]["scores"]["L4"]["sig"]))
    best_l5 = max(results, key=lambda x: abs(results[x]["scores"]["L5"]["sig"]))

    interpretation = []

    if l5_asi >= 0.6:
        interpretation.append("L5 persistent across folds → likely real feature")
    elif l5_asi >= 0.3:
        interpretation.append("L5 partially consistent → worth manual inspection")
    else:
        interpretation.append("L5 appears in only one fold → possible alias")

    if l4_asi >= 0.6:
        interpretation.append("L4 persistent across folds → likely real feature")
    elif l4_asi >= 0.3:
        interpretation.append("L4 partially consistent → worth manual inspection")
    else:
        interpretation.append("L4 appears in only one fold → possible alias")

    # Co-orbital mimarisi mümkün mü?
    primary_adopted = results.get("adopted", {}).get("scores", {}).get("primary", {})
    l5_adopted = results.get("adopted", {}).get("scores", {}).get("L5", {})

    coorbital_flag = "NO"
    if (
        abs(l5_adopted.get("sig", 0.0)) >= 4.0
        and l5_asi >= 0.3
        and abs(primary_adopted.get("depth_ppm", 0.0)) > 0
        and abs(l5_adopted.get("depth_ppm", 0.0)) < abs(primary_adopted.get("depth_ppm", 0.0)) * 1.5
    ):
        coorbital_flag = "POSSIBLE_COORBITAL"
        interpretation.append("Co-orbital/Trojan structure POSSIBLE: deep L5 in adopted fold, partially consistent")
    elif abs(l5_adopted.get("sig", 0.0)) >= 7.0 and l5_asi < 0.2:
        coorbital_flag = "ALIAS_LIKELY"
        interpretation.append("L5 depth high but inconsistent → probable period alias")

    return {
        "L4_ASI": round(l4_asi, 3),
        "L5_ASI": round(l5_asi, 3),
        "best_L4_fold": best_l4,
        "best_L5_fold": best_l5,
        "coorbital_flag": coorbital_flag,
        "interpretation": interpretation,
    }


# ─────────────────────────────────────────────────────────────
# Figür
# ─────────────────────────────────────────────────────────────

def make_figure(
    tic_id: int,
    sector: int,
    fold_results: dict,
    stability: dict,
    outpath: Path,
):
    n = len(fold_results)
    fig = plt.figure(figsize=(15, 4 * n + 3))
    gs = GridSpec(n + 1, 3, figure=fig, hspace=0.55, wspace=0.3)

    colors = {
        "adopted": "blue",
        "tls": "green",
        "bls": "orange",
        "half_period": "purple",
        "double_period": "red",
    }

    for row_idx, (label, result) in enumerate(fold_results.items()):
        bc = result["bin_centers"]
        bm = result["bin_medians"]
        sc = result["scores"]
        color = colors.get(label, "gray")

        # Full fold
        ax0 = fig.add_subplot(gs[row_idx, 0])
        ax0.scatter(bc, bm, s=4, color=color, alpha=0.8)
        ax0.axvspan(-0.1667 - 0.02, -0.1667 + 0.02, color="orange", alpha=0.15)
        ax0.axvspan(0.1667 - 0.02,  0.1667 + 0.02,  color="green",  alpha=0.15)
        ax0.axvspan(-0.5, -0.47, color="red", alpha=0.1)
        ax0.axvspan( 0.47,  0.5, color="red", alpha=0.1)
        ax0.set_title(f"{label} full fold\n(P={result['period']:.4f}d)", fontsize=8)
        ax0.set_xlim(-0.5, 0.5)
        ax0.set_xlabel("Phase")
        ax0.grid(True, alpha=0.2)

        # Zoom primary
        ax1 = fig.add_subplot(gs[row_idx, 1])
        zoom_m = np.abs(bc) < 0.12
        ax1.scatter(bc[zoom_m], bm[zoom_m], s=6, color=color)
        ax1.axvspan(-0.02, 0.02, color=color, alpha=0.1)
        d = sc["primary"]["depth_ppm"]
        s = sc["primary"]["sig"]
        ax1.set_title(f"Primary: {d:.0f} ppm  ({s:.1f} sig)", fontsize=8)
        ax1.set_xlim(-0.12, 0.12)
        ax1.grid(True, alpha=0.2)

        # Score bar
        ax2 = fig.add_subplot(gs[row_idx, 2])
        windows = ["primary", "secondary", "L4", "L5", "pre_shoulder", "post_shoulder"]
        labels_w = ["Prim", "Sec", "L4", "L5", "Pre-sh", "Post-sh"]
        sigs = [sc[w]["sig"] for w in windows]
        bar_colors = ["blue" if s > 0 else "red" for s in sigs]
        ax2.barh(labels_w, sigs, color=bar_colors, alpha=0.7)
        ax2.axvline(3.0, color="k", linestyle="--", lw=0.8)
        ax2.axvline(-3.0, color="k", linestyle="--", lw=0.8)
        ax2.axvline(0, color="k", lw=0.5)
        ax2.set_title(f"Significance per window\n(label={label})", fontsize=8)
        ax2.set_xlabel("sigma")
        ax2.grid(True, alpha=0.2)

    # Stability panel
    ax_stab = fig.add_subplot(gs[n, :])
    ax_stab.axis("off")
    stab_text = (
        f"ARCHITECTURE STABILITY INDEX\n"
        f"L4 ASI: {stability['L4_ASI']:.3f}  |  L5 ASI: {stability['L5_ASI']:.3f}\n"
        f"Best L4 fold: {stability['best_L4_fold']}  |  Best L5 fold: {stability['best_L5_fold']}\n"
        f"Co-orbital flag: {stability['coorbital_flag']}\n\n"
        + "\n".join(stability["interpretation"])
    )
    ax_stab.text(
        0.05, 0.5, stab_text,
        transform=ax_stab.transAxes,
        va="center", ha="left",
        family="monospace", fontsize=9,
    )
    ax_stab.set_title(f"TIC {tic_id} S{sector} — Architecture Multi-Period Review", fontsize=11)

    plt.savefig(outpath, dpi=160, bbox_inches="tight")
    plt.close()
    logger.info(f"Figür yazıldı: {outpath}")


# ─────────────────────────────────────────────────────────────
# Ana akış
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Architecture multi-period comparison")
    parser.add_argument("--tic", type=int, required=True)
    parser.add_argument("--sector", type=int, required=True)
    parser.add_argument("--period", type=float, required=True, help="Adopted period (days)")
    parser.add_argument("--t0", type=float, required=True, help="Epoch t0 (BTJD)")
    parser.add_argument("--duration-hours", type=float, required=True)
    parser.add_argument("--tls-period", type=float, default=None)
    parser.add_argument("--bls-period", type=float, default=None)
    parser.add_argument("--output-dir", type=str, default="outputs_architecture_review")
    args = parser.parse_args()

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Multi-period review başlıyor: TIC {args.tic} S{args.sector}")

    time, flux_raw = download_lc(args.tic, args.sector)
    flux = detrend(time, flux_raw)

    # Test edilecek periyotları topla
    periods_to_test: dict[str, float] = {"adopted": args.period}
    if args.tls_period and abs(args.tls_period - args.period) > 0.001:
        periods_to_test["tls"] = args.tls_period
    if args.bls_period and abs(args.bls_period - args.period) > 0.001:
        periods_to_test["bls"] = args.bls_period
    periods_to_test["half_period"] = args.period / 2.0
    periods_to_test["double_period"] = args.period * 2.0

    fold_results = {}
    _dur_phase_adopted = (args.duration_hours / 24.0) / args.period

    for label, period in periods_to_test.items():
        if period <= 0:
            continue
        phase = fold(time, period, args.t0)
        dur_phase = (args.duration_hours / 24.0) / period
        bc, bm, cnt = bin_lc(phase, flux)
        scores = score_all_windows(phase, flux, dur_phase)
        fold_results[label] = {
            "period": period,
            "bin_centers": bc,
            "bin_medians": bm,
            "bin_counts": cnt,
            "scores": scores,
        }

    stability = architecture_stability(fold_results)

    # Özet ekran
    print()
    print("=" * 90)
    print(f"TIC {args.tic} S{args.sector} — ARCHITECTURE MULTI-PERIOD COMPARISON")
    print("=" * 90)

    _headers = ["Fold", "Period(d)", "Primary", "Secondary", "L4", "L5", "Pre-sh", "Post-sh"]
    print(f"{'Fold':<16} {'Period':>8} {'Primary':>10} {'Sec':>8} {'L4':>8} {'L5':>8} {'Pre-sh':>8} {'Post-sh':>8}")
    print("-" * 90)

    for label, res in fold_results.items():
        sc = res["scores"]
        row = (
            f"{label:<16} "
            f"{res['period']:>8.4f} "
            f"{sc['primary']['depth_ppm']:>6.0f}({sc['primary']['sig']:>4.1f}σ) "
            f"{sc['secondary']['depth_ppm']:>4.0f}({sc['secondary']['sig']:>4.1f}σ) "
            f"{sc['L4']['depth_ppm']:>4.0f}({sc['L4']['sig']:>4.1f}σ) "
            f"{sc['L5']['depth_ppm']:>4.0f}({sc['L5']['sig']:>4.1f}σ) "
            f"{sc['pre_shoulder']['depth_ppm']:>4.0f}({sc['pre_shoulder']['sig']:>4.1f}σ) "
            f"{sc['post_shoulder']['depth_ppm']:>4.0f}({sc['post_shoulder']['sig']:>4.1f}σ)"
        )
        print(row)

    print()
    print(f"L4 Stability (ASI) : {stability['L4_ASI']:.3f}")
    print(f"L5 Stability (ASI) : {stability['L5_ASI']:.3f}")
    print(f"Co-orbital flag    : {stability['coorbital_flag']}")
    for line in stability["interpretation"]:
        print(f"  → {line}")

    print("=" * 90)

    # JSON rapor
    report = {
        "tic": args.tic,
        "sector": args.sector,
        "parameters": {
            "period": args.period,
            "t0": args.t0,
            "duration_hours": args.duration_hours,
        },
        "folds": {
            label: {
                "period": res["period"],
                "scores": res["scores"],
            }
            for label, res in fold_results.items()
        },
        "stability": {
            k: v for k, v in stability.items()
            if k != "interpretation"
        },
        "interpretation": stability["interpretation"],
    }

    json_path = outdir / f"TIC_{args.tic}_S{args.sector}_multiperiod.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info(f"JSON yazıldı: {json_path}")

    # Figür
    # bin_centers/bin_medians JSON serileştirilmiyor, ama figür için hâlâ bellekteyiz
    fig_path = outdir / f"TIC_{args.tic}_S{args.sector}_multiperiod.png"
    make_figure(
        tic_id=args.tic,
        sector=args.sector,
        fold_results=fold_results,
        stability=stability,
        outpath=fig_path,
    )


if __name__ == "__main__":
    main()
