#!/usr/bin/env python3
"""
Re-centered Architecture Multi-Period Comparison

Önceki compare_architecture_periods.py'nin kritik sorunu:
Tüm periyotlar için aynı t0 kullanıldı.
Bu, farklı periyotlarda transit'in yanlış faza oturmasına
ve sahte L4/L5 sinyallerine yol açıyordu.

Bu script her periyot için:
1. LC'yi o periyotla fold eder
2. Faz 0 civarında gerçek transit minimumunu bulur
3. t0_eff'i buna göre düzeltir
4. Sonra L4/L5/shoulder pencerelerini skorlar

Sonuç:
Farklı periyotlar arasında gerçekten karşılaştırılabilir
bir mimari sinyal analizi.

Kullanım:
    python scripts/followup/recentered_architecture_compare.py \
        --tic 357370384 \
        --sector 57 \
        --period 13.4939 \
        --t0 2853.379 \
        --duration-hours 1.15 \
        --tls-period 13.4939 \
        --bls-period 28.7321
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from loguru import logger
from scipy.interpolate import UnivariateSpline
from scipy.signal import find_peaks

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

try:
    import lightkurve as lk
except ImportError:
    raise ImportError("pip install lightkurve")


# ─────────────────────────────────────────────────────────────
# LC yardımcıları
# ─────────────────────────────────────────────────────────────

def download_lc(tic_id: int, sector: int):
    search = lk.search_lightcurve(
        f"TIC {tic_id}", mission="TESS",
        author="SPOC", sector=sector, exptime=120,
    )
    if len(search) == 0:
        raise FileNotFoundError(f"TIC {tic_id} S{sector}: LC bulunamadı.")
    lc = search[0].download()
    time = np.array(lc.time.value, dtype=float)
    flux = np.array(lc.flux.value, dtype=float)
    quality = np.array(lc.quality.value, dtype=int)
    valid = np.isfinite(time) & np.isfinite(flux) & (quality == 0)
    time, flux = time[valid], flux[valid]
    med = np.nanmedian(flux)
    return time, flux / med


def detrend(
    time: np.ndarray,
    flux: np.ndarray,
    knot_days: float = 0.75,
) -> np.ndarray:
    knots = np.arange(time.min() + knot_days, time.max(), knot_days)
    if len(knots) < 4:
        return flux
    med = np.median(flux)
    std = np.std(flux)
    w = np.where(flux < (med - 2.0 * std), 0.05, 1.0)
    try:
        sp = UnivariateSpline(time, flux, w=w, k=3, s=len(time) * 0.4)
        trend = sp(time)
        trend = np.where(trend > 0, trend, 1.0)
        return flux / trend
    except Exception:
        return flux


# ─────────────────────────────────────────────────────────────
# t0 re-centering
# ─────────────────────────────────────────────────────────────

def find_transit_minimum_phase(
    time: np.ndarray,
    flux: np.ndarray,
    period: float,
    t0_guess: float,
    search_phase_half_width: float = 0.15,
    duration_hours: float = 2.0,
) -> float:
    """
    Verilen t0_guess civarında, period ile fold edilmiş LC'de
    gerçek transit minimumunu bulur.

    Returns
    -------
    t0_eff: float
        Düzeltilmiş epoch (BTJD). transit minimumu bu zamana hizalanmış.
    """
    phase_raw = ((time - t0_guess) % period)
    phase_centered = np.where(phase_raw > period / 2.0, phase_raw - period, phase_raw)
    phase_frac = phase_centered / period

    search_mask = np.abs(phase_frac) < search_phase_half_width
    if search_mask.sum() < 10:
        logger.debug("Re-center: Yetersiz nokta, orijinal t0 korunuyor.")
        return float(t0_guess)

    flux_in_window = flux[search_mask]
    time_in_window = time[search_mask]
    phase_in_window = phase_frac[search_mask]

    bins = np.linspace(-search_phase_half_width, search_phase_half_width, 60)
    bin_medians = np.zeros(len(bins) - 1)
    bin_phases = 0.5 * (bins[:-1] + bins[1:])

    for i in range(len(bins) - 1):
        m = (phase_in_window >= bins[i]) & (phase_in_window < bins[i + 1])
        if m.sum() >= 2:
            bin_medians[i] = np.median(flux_in_window[m])
        else:
            bin_medians[i] = np.nan

    finite = np.isfinite(bin_medians)
    if finite.sum() < 5:
        return float(t0_guess)

    smoothed = bin_medians.copy()
    for i in range(1, len(smoothed) - 1):
        if np.isfinite(smoothed[i]):
            neighbors = [smoothed[i - 1], smoothed[i], smoothed[i + 1]]
            valid_n = [x for x in neighbors if np.isfinite(x)]
            smoothed[i] = np.mean(valid_n)

    min_idx = np.nanargmin(smoothed)
    min_phase = bin_phases[min_idx]

    t0_eff = t0_guess + min_phase * period

    logger.debug(
        f"Re-center: period={period:.4f}d, "
        f"original_t0={t0_guess:.5f}, "
        f"phase_shift={min_phase:.4f}, "
        f"t0_eff={t0_eff:.5f}"
    )

    return float(t0_eff)


# ─────────────────────────────────────────────────────────────
# Fold & bin
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

    in_flux = flux[in_w]
    out_flux = flux[out_w]
    baseline = np.nanmedian(out_flux) if len(out_flux) > 5 else 1.0
    sigma_out = max(np.nanstd(out_flux), 1e-9) if len(out_flux) > 5 else 1e-9

    depth_ppm = float((baseline - np.nanmedian(in_flux)) * 1e6)
    sig = float(depth_ppm / 1e6 / sigma_out * np.sqrt(n_in))

    return {
        "n": n_in,
        "depth_ppm": round(depth_ppm, 1),
        "sig": round(sig, 2),
    }


def score_all_windows(
    phase: np.ndarray,
    flux: np.ndarray,
    dur_phase: float,
) -> dict:
    w = max(dur_phase * 1.5, 0.005)
    return {
        "primary": score_window(phase, flux, 0.000, dur_phase),
        "secondary": score_window(phase, flux, 0.500, dur_phase),
        "L4": score_window(phase, flux, -0.1667, w),
        "L5": score_window(phase, flux, 0.1667, w),
        "pre_shoulder": score_window(phase, flux, -dur_phase * 1.8, dur_phase),
        "post_shoulder": score_window(phase, flux, dur_phase * 1.8, dur_phase),
    }


# ─────────────────────────────────────────────────────────────
# Architecture Stability Index
# ─────────────────────────────────────────────────────────────

def architecture_stability(results: dict) -> dict:
    def consistency(sigs):
        if len(sigs) < 2:
            return 0.0
        arr = np.array([abs(s) for s in sigs])
        if arr.max() < 1.5:
            return 0.0
        med = np.median(arr)
        top = np.percentile(arr, 80)
        return float(np.clip(med / max(top, 0.1), 0.0, 1.0))

    l4_sigs = [r["scores"]["L4"]["sig"] for r in results.values()]
    l5_sigs = [r["scores"]["L5"]["sig"] for r in results.values()]

    l4_asi = consistency(l4_sigs)
    l5_asi = consistency(l5_sigs)

    best_l4 = max(results, key=lambda x: abs(results[x]["scores"]["L4"]["sig"]))
    best_l5 = max(results, key=lambda x: abs(results[x]["scores"]["L5"]["sig"]))

    interpretation = []

    # L5 değerlendirmesi
    if l5_asi >= 0.60:
        interpretation.append(
            "L5 PERSISTENT across re-centered folds → strong evidence for real off-primary structure."
        )
    elif l5_asi >= 0.30:
        interpretation.append(
            "L5 PARTIALLY consistent → warrants manual inspection but alias not ruled out."
        )
    else:
        interpretation.append(
            "L5 INCONSISTENT across folds → likely period alias or noise."
        )

    # L4 değerlendirmesi
    if l4_asi >= 0.60:
        interpretation.append(
            "L4 PERSISTENT across re-centered folds → real leading structure possible."
        )
    elif l4_asi >= 0.30:
        interpretation.append(
            "L4 PARTIALLY consistent → moderate interest."
        )
    else:
        interpretation.append(
            "L4 INCONSISTENT → likely alias or noise."
        )

    # Co-orbital karar
    adopted = results.get("adopted", {})
    if not adopted:
        adopted = next(iter(results.values()))

    prim = adopted["scores"]["primary"]
    l5 = adopted["scores"]["L5"]
    l4 = adopted["scores"]["L4"]
    secondary = adopted["scores"]["secondary"]

    coorbital_flag = "NO"

    l5_is_deep = abs(l5["sig"]) >= 4.0
    l5_reasonable_size = (
        abs(l5["depth_ppm"]) < abs(prim["depth_ppm"]) * 1.8
        and abs(l5["depth_ppm"]) > 50
    ) if prim["depth_ppm"] != 0 else False
    secondary_not_dominant = abs(secondary["sig"]) < abs(l5["sig"]) * 0.85

    if l5_is_deep and l5_asi >= 0.30 and l5_reasonable_size and secondary_not_dominant:
        coorbital_flag = "POSSIBLE_COORBITAL"
        interpretation.append(
            "Co-orbital/Trojan structure POSSIBLE: L5 depth is significant, partially consistent across "
            "re-centered folds, and secondary eclipse is not the dominant off-primary feature."
        )
    elif l5_is_deep and l5_asi < 0.25:
        coorbital_flag = "ALIAS_LIKELY"
        interpretation.append(
            "L5 deep in adopted fold but collapses in other folds → period alias is the likely cause."
        )
    elif abs(secondary["sig"]) > abs(l5["sig"]) + 2.0:
        coorbital_flag = "EB_SECONDARY_DOMINANT"
        interpretation.append(
            "Secondary eclipse dominates over L5 → eclipsing binary scenario more likely."
        )

    # Shoulder yorumu
    pre_sh = adopted["scores"]["pre_shoulder"]
    post_sh = adopted["scores"]["post_shoulder"]
    if abs(pre_sh["sig"]) >= 4.0 or abs(post_sh["sig"]) >= 4.0:
        interpretation.append(
            f"Significant transit shoulders detected: pre={pre_sh['sig']:.1f}σ, "
            f"post={post_sh['sig']:.1f}σ → extended emission, rings, or broad transit possible."
        )

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
    fig = plt.figure(figsize=(16, 4.5 * n + 4))
    gs = GridSpec(n + 1, 3, figure=fig, hspace=0.60, wspace=0.35)

    pal = {
        "adopted": "#1f77b4",
        "tls": "#2ca02c",
        "bls": "#ff7f0e",
        "half_period": "#9467bd",
        "double_period": "#d62728",
    }

    window_labels = ["Prim", "Sec", "L4", "L5", "Pre-sh", "Post-sh"]
    window_keys = ["primary", "secondary", "L4", "L5", "pre_shoulder", "post_shoulder"]

    for ridx, (label, result) in enumerate(fold_results.items()):
        bc = result["bin_centers"]
        bm = result["bin_medians"]
        sc = result["scores"]
        col = pal.get(label, "gray")
        t0_eff = result["t0_eff"]

        # Full fold
        ax0 = fig.add_subplot(gs[ridx, 0])
        valid_b = np.isfinite(bm)
        ax0.scatter(bc[valid_b], bm[valid_b], s=4, color=col, alpha=0.85)
        ax0.axvspan(-0.1667 - 0.015, -0.1667 + 0.015, color="#ff7f0e", alpha=0.18, label="L4")
        ax0.axvspan(0.1667 - 0.015, 0.1667 + 0.015, color="#2ca02c", alpha=0.18, label="L5")
        ax0.axvspan(0.46, 0.50, color="red", alpha=0.10)
        ax0.axvspan(-0.50, -0.46, color="red", alpha=0.10)
        ax0.axhline(1.0, color="k", lw=0.4, ls="--")
        ax0.set_title(
            f"{label}  P={result['period']:.4f}d\n"
            f"t0_eff={t0_eff:.5f}",
            fontsize=7.5,
        )
        ax0.set_xlim(-0.5, 0.5)
        lo = np.nanpercentile(bm[valid_b], 0.5) if valid_b.sum() > 0 else 0.995
        hi = np.nanpercentile(bm[valid_b], 99.5) if valid_b.sum() > 0 else 1.005
        ax0.set_ylim(lo, hi)
        ax0.set_xlabel("Phase", fontsize=7)
        ax0.grid(True, alpha=0.20)
        ax0.legend(fontsize=6, loc="upper right")

        # Zoom ±0.10
        ax1 = fig.add_subplot(gs[ridx, 1])
        zm = np.abs(bc) < 0.10
        if zm.sum() > 0 and np.any(np.isfinite(bm[zm])):
            ax1.scatter(bc[zm], bm[zm], s=7, color=col)
        ax1.axvspan(-0.015, 0.015, color=col, alpha=0.12)
        d = sc["primary"]["depth_ppm"]
        s = sc["primary"]["sig"]
        ax1.set_title(f"Transit zoom\n{d:.0f} ppm / {s:.1f}σ", fontsize=7.5)
        ax1.set_xlim(-0.10, 0.10)
        ax1.set_xlabel("Phase", fontsize=7)
        ax1.grid(True, alpha=0.20)

        # Bar chart
        ax2 = fig.add_subplot(gs[ridx, 2])
        sigs = [sc[k]["sig"] for k in window_keys]
        colors_b = ["#1f77b4" if s > 0 else "#d62728" for s in sigs]
        bars = ax2.barh(window_labels, sigs, color=colors_b, alpha=0.75)
        for bar, sig in zip(bars, sigs):
            ax2.text(
                sig + (0.15 if sig >= 0 else -0.15),
                bar.get_y() + bar.get_height() / 2,
                f"{sig:.1f}",
                va="center",
                ha="left" if sig >= 0 else "right",
                fontsize=6,
            )
        ax2.axvline(3.0, color="k", ls="--", lw=0.8)
        ax2.axvline(-3.0, color="k", ls="--", lw=0.8)
        ax2.axvline(0, color="k", lw=0.5)
        ax2.set_title(f"Window significance\n{label}", fontsize=7.5)
        ax2.set_xlabel("σ", fontsize=7)
        ax2.grid(True, alpha=0.20, axis="x")

    # Stability panel
    ax_stab = fig.add_subplot(gs[n, :])
    ax_stab.axis("off")
    txt = (
        f"RE-CENTERED ARCHITECTURE STABILITY INDEX\n"
        f"L4 ASI = {stability['L4_ASI']:.3f}   "
        f"L5 ASI = {stability['L5_ASI']:.3f}\n"
        f"Best L4 fold : {stability['best_L4_fold']}   "
        f"Best L5 fold : {stability['best_L5_fold']}\n"
        f"Co-orbital flag : {stability['coorbital_flag']}\n\n"
        + "\n".join(f"→ {line}" for line in stability["interpretation"])
    )
    ax_stab.text(
        0.02, 0.95, txt,
        transform=ax_stab.transAxes,
        va="top", ha="left",
        family="monospace", fontsize=8.5,
        bbox=dict(boxstyle="round,pad=0.4", fc="#f7f7f7", ec="#cccccc"),
    )
    fig.suptitle(
        f"TIC {tic_id} S{sector} — Re-centered Architecture Multi-Period Review",
        fontsize=12, y=0.99,
    )

    plt.savefig(outpath, dpi=160, bbox_inches="tight")
    plt.close()
    logger.info(f"Figür yazıldı: {outpath}")


# ─────────────────────────────────────────────────────────────
# Ana akış
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Re-centered architecture comparison")
    parser.add_argument("--tic", type=int, required=True)
    parser.add_argument("--sector", type=int, required=True)
    parser.add_argument("--period", type=float, required=True)
    parser.add_argument("--t0", type=float, required=True)
    parser.add_argument("--duration-hours", type=float, required=True)
    parser.add_argument("--tls-period", type=float, default=None)
    parser.add_argument("--bls-period", type=float, default=None)
    parser.add_argument("--output-dir", type=str, default="outputs_architecture_review")
    parser.add_argument(
        "--no-recenter",
        action="store_true",
        help="Epoch re-centering'i devre dışı bırak (debug için)",
    )
    args = parser.parse_args()

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Re-centered multi-period review: TIC {args.tic} S{args.sector}")

    time, flux_raw = download_lc(args.tic, args.sector)
    flux = detrend(time, flux_raw)

    periods_to_test: dict[str, float] = {"adopted": args.period}
    if args.tls_period and abs(args.tls_period - args.period) > 0.001:
        periods_to_test["tls"] = args.tls_period
    if args.bls_period and abs(args.bls_period - args.period) > 0.001:
        periods_to_test["bls"] = args.bls_period
    periods_to_test["half_period"] = args.period / 2.0
    periods_to_test["double_period"] = args.period * 2.0

    fold_results: dict[str, dict] = {}

    for label, period in periods_to_test.items():
        if period <= 0:
            continue

        if args.no_recenter or label == "adopted":
            t0_eff = args.t0
        else:
            t0_eff = find_transit_minimum_phase(
                time=time,
                flux=flux,
                period=period,
                t0_guess=args.t0,
                search_phase_half_width=0.20,
                duration_hours=args.duration_hours,
            )

        phase = fold(time, period, t0_eff)
        dur_phase = (args.duration_hours / 24.0) / period
        bc, bm, cnt = bin_lc(phase, flux)
        scores = score_all_windows(phase, flux, dur_phase)

        fold_results[label] = {
            "period": period,
            "t0_eff": t0_eff,
            "phase_shift": t0_eff - args.t0,
            "bin_centers": bc,
            "bin_medians": bm,
            "bin_counts": cnt,
            "scores": scores,
        }

        logger.info(
            f"{label}: period={period:.4f}d, t0_eff={t0_eff:.5f}, "
            f"primary={scores['primary']['depth_ppm']:.0f}ppm/{scores['primary']['sig']:.1f}σ, "
            f"L5={scores['L5']['depth_ppm']:.0f}ppm/{scores['L5']['sig']:.1f}σ"
        )

    stability = architecture_stability(fold_results)

    # ── Ekran özeti ──
    print()
    print("=" * 100)
    print(f"TIC {args.tic} S{args.sector} — RE-CENTERED ARCHITECTURE COMPARISON")
    print("=" * 100)
    print(
        f"{'Fold':<16} {'Period':>8} {'t0-shift(min)':>13} "
        f"{'Primary':>12} {'Sec':>10} {'L4':>10} {'L5':>10} {'Pre-sh':>10} {'Post-sh':>10}"
    )
    print("-" * 100)

    for label, res in fold_results.items():
        sc = res["scores"]
        shift_min = (res["t0_eff"] - args.t0) * 24 * 60
        print(
            f"{label:<16} {res['period']:>8.4f} {shift_min:>13.2f} "
            f"{sc['primary']['depth_ppm']:>6.0f}({sc['primary']['sig']:>5.1f}σ) "
            f"{sc['secondary']['depth_ppm']:>4.0f}({sc['secondary']['sig']:>5.1f}σ) "
            f"{sc['L4']['depth_ppm']:>4.0f}({sc['L4']['sig']:>5.1f}σ) "
            f"{sc['L5']['depth_ppm']:>4.0f}({sc['L5']['sig']:>5.1f}σ) "
            f"{sc['pre_shoulder']['depth_ppm']:>4.0f}({sc['pre_shoulder']['sig']:>5.1f}σ) "
            f"{sc['post_shoulder']['depth_ppm']:>4.0f}({sc['post_shoulder']['sig']:>5.1f}σ)"
        )

    print()
    print(f"L4 Stability (ASI)     : {stability['L4_ASI']:.3f}")
    print(f"L5 Stability (ASI)     : {stability['L5_ASI']:.3f}")
    print(f"Co-orbital flag        : {stability['coorbital_flag']}")
    for line in stability["interpretation"]:
        print(f"  → {line}")
    print("=" * 100)

    # ── JSON rapor ──
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
                "t0_eff": res["t0_eff"],
                "phase_shift_days": res["t0_eff"] - args.t0,
                "scores": res["scores"],
            }
            for label, res in fold_results.items()
        },
        "stability": {k: v for k, v in stability.items() if k != "interpretation"},
        "interpretation": stability["interpretation"],
        "coorbital_flag": stability["coorbital_flag"],
    }

    json_path = outdir / f"TIC_{args.tic}_S{args.sector}_recentered.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info(f"JSON yazıldı: {json_path}")

    # ── Figür ──
    fig_path = outdir / f"TIC_{args.tic}_S{args.sector}_recentered.png"
    make_figure(
        tic_id=args.tic,
        sector=args.sector,
        fold_results=fold_results,
        stability=stability,
        outpath=fig_path,
    )


if __name__ == "__main__":
    main()
