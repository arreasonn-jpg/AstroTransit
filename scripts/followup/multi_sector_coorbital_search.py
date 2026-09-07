#!/usr/bin/env python3
"""
Multi-Sector Co-orbital / Architecture Search

Amaç
----
Birden fazla TESS sektöründe gözlemlenmiş hedefler için:
1. Tüm sektörleri indir (TESSClient.get_all_sectors kullanarak)
2. Her sektörü verilen periyot/epoch ile fold et
3. L4/L5/shoulder pencerelerini her sektörde ayrı ayrı ölç
4. Sektörler arası tutarlılık (cross-sector ASI) hesapla
5. Gerçek mimari yapı vs alias/noise kararı ver

Kullanım
--------
    python scripts/followup/multi_sector_coorbital_search.py \
        --tic 407393440 \
        --period 11.681 \
        --t0 1769.5 \
        --duration-hours 2.5

    # Periyot bilinmiyorsa (yeni hedef):
    python scripts/followup/multi_sector_coorbital_search.py \
        --tic 407430919 \
        --auto-period \
        --duration-hours 2.0
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

import numpy as np
from loguru import logger
from scipy.interpolate import UnivariateSpline

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

from astrotransit.data.tess_client import TESSClient, TESSLightCurveData, TESSNoDataError


# ──────────────────────────────────────────────────────────────
# Detrend
# ──────────────────────────────────────────────────────────────

def detrend_sector(
    time: np.ndarray,
    flux: np.ndarray,
    knot_spacing_days: float = 0.75,
) -> np.ndarray:
    """OOT ağırlıklı spline detrend."""
    if len(time) < 50:
        return flux / np.nanmedian(flux)

    flux_norm = flux / np.nanmedian(flux)
    med = np.nanmedian(flux_norm)
    std = np.nanstd(flux_norm)
    w = np.where(flux_norm < (med - 2.0 * std), 0.05, 1.0)

    try:
        sp = UnivariateSpline(time, flux_norm, w=w, k=3, s=len(time) * 0.5)
        trend = sp(time)
        trend = np.where(trend > 0.3, trend, 1.0)
        return flux_norm / trend
    except Exception as exc:
        logger.warning(f"Spline hatası: {exc}, ham normalize kullanılıyor")
        return flux_norm


# ──────────────────────────────────────────────────────────────
# Fold & window scoring
# ──────────────────────────────────────────────────────────────

def fold(time: np.ndarray, period: float, t0: float) -> np.ndarray:
    return ((time - t0 + 0.5 * period) % period) / period - 0.5


def score_window(
    phase: np.ndarray,
    flux: np.ndarray,
    center: float,
    half_width: float,
    min_pts: int = 5,
) -> dict:
    shifted = ((phase - center + 0.5) % 1.0) - 0.5
    in_w = np.abs(shifted) < half_width
    n_in = int(in_w.sum())

    if n_in < min_pts:
        return {"n": n_in, "depth_ppm": 0.0, "sig": 0.0}

    in_flux = flux[in_w]
    out_flux = flux[~in_w]

    in_flux = in_flux[np.isfinite(in_flux)]
    out_flux = out_flux[np.isfinite(out_flux)]

    if len(in_flux) < min_pts or len(out_flux) < 10:
        return {"n": n_in, "depth_ppm": 0.0, "sig": 0.0}

    baseline = np.nanmedian(out_flux)
    sigma = max(np.nanstd(out_flux), 1e-9)
    depth_ppm = float((baseline - np.nanmedian(in_flux)) * 1e6)
    sig = float(depth_ppm / 1e6 / sigma * np.sqrt(len(in_flux)))

    return {"n": len(in_flux), "depth_ppm": round(depth_ppm, 1), "sig": round(sig, 2)}


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


def bin_lc(phase: np.ndarray, flux: np.ndarray, bins: int = 200):
    edges = np.linspace(-0.5, 0.5, bins + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    medians = np.full(bins, np.nan)
    for i in range(bins):
        m = (phase >= edges[i]) & (phase < edges[i + 1])
        if m.sum() >= 2:
            medians[i] = np.nanmedian(flux[m])
    return centers, medians


# ──────────────────────────────────────────────────────────────
# Cross-sector ASI (Architecture Stability Index)
# ──────────────────────────────────────────────────────────────

def cross_sector_asi(sector_scores: list[dict], window: str) -> float:
    """
    Birden fazla sektördeki belirtilen pencere sinyalinin tutarlılığı.

    0.0 = hiç tutarlı değil
    1.0 = tüm sektörlerde eşit güçte
    """
    sigs = [abs(s[window]["sig"]) for s in sector_scores]
    if not sigs or max(sigs) < 1.0:
        return 0.0

    above_2 = sum(1 for s in sigs if s >= 2.0)
    consistency = above_2 / len(sigs)

    arr = np.array(sigs)
    top = np.percentile(arr, 80)
    med = np.median(arr)
    ratio = float(np.clip(med / max(top, 0.1), 0.0, 1.0))

    return float(np.clip(consistency * 0.6 + ratio * 0.4, 0.0, 1.0))


def cross_sector_verdict(
    l4_asi: float,
    l5_asi: float,
    l4_sigs: list[float],
    l5_sigs: list[float],
    primary_sigs: list[float],
    secondary_sigs: list[float],
    sector_results: list[dict],
    dur_phase: float,
    odd_even: float = 0.0,
) -> tuple[str, str]:
    """
    Cross-sector analiz sonuçlarından mimari karar üretir.
    Genişletilmiş guard'lar: orbital modülasyon ve phase-curve tespiti.
    """
    import numpy as np

    n_sectors = len(l4_sigs)
    primary_ok = sum(1 for s in primary_sigs if s >= 3.0) >= max(1, n_sectors // 2)

    if not primary_ok:
        return "WEAK_PRIMARY", "Primary transit not consistently detected across sectors"

    mean_prim_ppm = np.mean([abs(r["scores"]["primary"]["depth_ppm"]) for r in sector_results])
    mean_sec_ppm = np.mean([abs(r["scores"]["secondary"]["depth_ppm"]) for r in sector_results])
    mean_l4_ppm = np.mean([abs(r["scores"]["L4"]["depth_ppm"]) for r in sector_results])
    mean_l5_ppm = np.mean([abs(r["scores"]["L5"]["depth_ppm"]) for r in sector_results])
    mean_pre_ppm = np.mean([abs(r["scores"]["pre_shoulder"]["depth_ppm"]) for r in sector_results])
    mean_post_ppm = np.mean([abs(r["scores"]["post_shoulder"]["depth_ppm"]) for r in sector_results])

    # Guard 1: Güçlü Orbital Modülasyon / Faz Eğrisi
    modulation_score = 0
    if mean_prim_ppm > 0:
        if mean_sec_ppm > 0.4 * mean_prim_ppm: modulation_score += 1
        if mean_pre_ppm > 0.4 * mean_prim_ppm: modulation_score += 1
        if mean_post_ppm > 0.4 * mean_prim_ppm: modulation_score += 1
        if mean_l4_ppm > 0.3 * mean_prim_ppm: modulation_score += 1
        if mean_l5_ppm > 0.3 * mean_prim_ppm: modulation_score += 1

    if modulation_score >= 3:
        return (
            "LIKELY_ORBITAL_MODULATION_SYSTEM",
            "Broad, symmetric flux variations across all phases → binary phase-curve or reflection, NOT a simple co-orbital planet"
        )

    # Guard 2: Eclipsing Binary
    sec_dominant = (np.mean([abs(s) for s in secondary_sigs]) >= 4.0 and odd_even >= 2.0)
    if sec_dominant:
        return "LIKELY_EB", "Strong repeatable secondary with high odd-even → eclipsing binary"

    # L4 / L5 Değerlendirmesi
    l5_strong = l5_asi >= 0.60 and any(s >= 5.0 for s in l5_sigs)
    l4_strong = l4_asi >= 0.60 and any(s >= 5.0 for s in l4_sigs)

    coorbital_size_guard = True
    if mean_prim_ppm > 0:
        if mean_l4_ppm > 0.8 * mean_prim_ppm or mean_l5_ppm > 0.8 * mean_prim_ppm:
            coorbital_size_guard = False

    if l5_strong and l4_strong:
        if coorbital_size_guard:
            return (
                "SYMMETRIC_COORBITAL_OR_DISK",
                f"Both L4 (ASI={l4_asi:.2f}) and L5 (ASI={l5_asi:.2f}) persistent → disk or symmetric debris structure"
            )
        else:
            return "LIKELY_ORBITAL_MODULATION", "Strong symmetric L4/L5 signals too deep for planetary co-orbitals"

    if l5_strong and not l4_strong and coorbital_size_guard:
        return (
            "POSSIBLE_COORBITAL_L5",
            f"L5 ASI={l5_asi:.2f} ≥ 0.60, persistent across {n_sectors} sectors → co-orbital review priority"
        )

    if l4_strong and not l5_strong and coorbital_size_guard:
        return (
            "POSSIBLE_COORBITAL_L4",
            f"L4 ASI={l4_asi:.2f} ≥ 0.60, persistent across {n_sectors} sectors → co-orbital review priority"
        )

    if l5_asi >= 0.30 or l4_asi >= 0.30:
        return (
            "PARTIAL_OFFPRIMARY_SIGNAL",
            f"L4 ASI={l4_asi:.2f}, L5 ASI={l5_asi:.2f} — partial cross-sector signal, worth follow-up"
        )

    return "NO_ARCHITECTURE_ANOMALY", "No persistent off-primary signal detected across sectors"



# ──────────────────────────────────────────────────────────────
# Basit BLS (periyot bilinmiyorsa)
# ──────────────────────────────────────────────────────────────

def simple_bls(time: np.ndarray, flux: np.ndarray, min_p: float = 0.5, max_p: float = 30.0):
    """Çok basit BLS — sadece en iyi periyodu bulmak için."""
    from astropy.timeseries import BoxLeastSquares

    bls = BoxLeastSquares(time, flux)
    result = bls.autopower(
        duration=[0.05, 0.10, 0.15, 0.20],
        minimum_period=min_p,
        maximum_period=max_p,
        frequency_factor=3.0,
    )
    best_idx = np.argmax(result.power)
    best_period = float(result.period[best_idx])
    best_t0 = float(result.transit_time[best_idx])
    best_depth = float(result.depth[best_idx])
    best_duration = float(result.duration[best_idx])

    logger.info(f"BLS best: period={best_period:.4f}d, t0={best_t0:.4f}, depth={best_depth*1e6:.0f}ppm")
    return best_period, best_t0, best_duration * 24.0


# ──────────────────────────────────────────────────────────────
# Figür
# ──────────────────────────────────────────────────────────────

def make_figure(
    tic_id: int,
    sector_results: list[dict],
    period: float,
    outpath: Path,
):
    n = len(sector_results)
    fig = plt.figure(figsize=(14, 4 * n + 3))
    gs = GridSpec(n + 1, 3, figure=fig, hspace=0.55, wspace=0.35)

    window_keys = ["primary", "secondary", "L4", "L5", "pre_shoulder", "post_shoulder"]
    window_labels = ["Prim", "Sec", "L4", "L5", "Pre-sh", "Post-sh"]

    colors = plt.cm.tab10(np.linspace(0, 0.8, n))

    for ridx, (res, col) in enumerate(zip(sector_results, colors)):
        sec_num = res["sector"]
        bc = np.array(res["bin_centers"])
        bm = np.array(res["bin_medians"])
        sc = res["scores"]
        dur_phase = res["dur_phase"]

        # Full fold panel
        ax0 = fig.add_subplot(gs[ridx, 0])
        valid = np.isfinite(bm)
        ax0.scatter(bc[valid], bm[valid], s=4, color=col, alpha=0.85)
        ax0.axvspan(-0.1667 - 0.015, -0.1667 + 0.015, color="orange", alpha=0.15, label="L4")
        ax0.axvspan(0.1667 - 0.015, 0.1667 + 0.015, color="green", alpha=0.15, label="L5")
        ax0.axhline(1.0, color="k", lw=0.4, ls="--")
        ax0.set_title(f"S{sec_num} full fold", fontsize=8)
        ax0.set_xlim(-0.5, 0.5)
        ax0.grid(True, alpha=0.2)
        ax0.legend(fontsize=6)

        # Transit zoom
        ax1 = fig.add_subplot(gs[ridx, 1])
        zm = np.abs(bc) < 0.12
        if zm.sum() > 0 and np.any(valid[zm]):
            ax1.scatter(bc[zm & valid], bm[zm & valid], s=6, color=col)
        d = sc["primary"]["depth_ppm"]
        s_val = sc["primary"]["sig"]
        ax1.set_title(f"S{sec_num} transit\n{d:.0f}ppm/{s_val:.1f}σ", fontsize=8)
        ax1.set_xlim(-0.12, 0.12)
        ax1.grid(True, alpha=0.2)

        # Significance bars
        ax2 = fig.add_subplot(gs[ridx, 2])
        sigs = [sc[k]["sig"] for k in window_keys]
        bar_colors = ["steelblue" if s > 0 else "salmon" for s in sigs]
        ax2.barh(window_labels, sigs, color=bar_colors, alpha=0.75)
        ax2.axvline(3.0, color="k", ls="--", lw=0.7)
        ax2.axvline(-3.0, color="k", ls="--", lw=0.7)
        ax2.axvline(0, color="k", lw=0.4)
        ax2.set_title(f"S{sec_num} windows", fontsize=8)
        ax2.set_xlabel("σ", fontsize=7)
        ax2.grid(True, alpha=0.2, axis="x")

    # Summary panel
    ax_sum = fig.add_subplot(gs[n, :])
    ax_sum.axis("off")

    l4_sigs = [r["scores"]["L4"]["sig"] for r in sector_results]
    l5_sigs = [r["scores"]["L5"]["sig"] for r in sector_results]
    sector_nums = [r["sector"] for r in sector_results]

    l4_asi = cross_sector_asi(
        [r["scores"] for r in sector_results], "L4"
    )
    l5_asi = cross_sector_asi(
        [r["scores"] for r in sector_results], "L5"
    )

    l4_str = "  ".join(f"S{s}:{v:.1f}σ" for s, v in zip(sector_nums, l4_sigs))
    l5_str = "  ".join(f"S{s}:{v:.1f}σ" for s, v in zip(sector_nums, l5_sigs))

    txt = (
        f"CROSS-SECTOR ARCHITECTURE ANALYSIS — TIC {tic_id}  (P={period:.4f}d)\n"
        f"L4 cross-sector ASI = {l4_asi:.3f}  |  {l4_str}\n"
        f"L5 cross-sector ASI = {l5_asi:.3f}  |  {l5_str}\n"
    )
    ax_sum.text(
        0.02, 0.85, txt,
        transform=ax_sum.transAxes,
        va="top", ha="left", family="monospace", fontsize=9,
        bbox=dict(boxstyle="round,pad=0.4", fc="#f7f7f7", ec="#cccccc"),
    )

    fig.suptitle(f"TIC {tic_id} — Multi-Sector Co-orbital Search", fontsize=12)
    plt.savefig(outpath, dpi=160, bbox_inches="tight")
    plt.close()
    logger.info(f"Figür yazıldı: {outpath}")


# ──────────────────────────────────────────────────────────────
# Ana akış
# ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Multi-sector co-orbital search")
    parser.add_argument("--tic", type=int, required=True)
    parser.add_argument("--period", type=float, default=None)
    parser.add_argument("--t0", type=float, default=None)
    parser.add_argument("--duration-hours", type=float, default=2.0)
    parser.add_argument("--auto-period", action="store_true")
    parser.add_argument("--min-period", type=float, default=1.0)
    parser.add_argument("--max-period", type=float, default=60.0)
    parser.add_argument("--max-sectors", type=int, default=6)
    parser.add_argument("--odd-even", type=float, default=0.0)
    parser.add_argument("--output-dir", type=str, default="outputs_architecture_review")
    args = parser.parse_args()

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    target_id = f"TIC {args.tic}"
    logger.info(f"Multi-sector co-orbital search başlıyor: {target_id}")

    # 1. Tüm sektörleri indir
    client = TESSClient()
    try:
        multi = client.get_all_sectors(target_id)
    except TESSNoDataError as e:
        logger.error(f"Veri bulunamadı: {e}")
        return

    logger.info(f"{multi.n_sectors} sektör bulundu: {multi.sector_numbers}")

    if multi.n_sectors < 2:
        logger.warning("En az 2 sektör gerekli. Bu analiz yapılamaz.")
        return

    # Seçilen sektör sayısını sınırla
    selected = multi.sectors[:args.max_sectors]

    # 2. Periyot belirleme
    if args.auto_period or args.period is None:
        logger.info("Otomatik periyot taraması yapılıyor (tüm sektörler birleşik)...")
        all_time = np.concatenate([s.time for s in selected])
        all_flux = np.concatenate([
            detrend_sector(s.time, s.flux) for s in selected
        ])
        sorter = np.argsort(all_time)
        all_time = all_time[sorter]
        all_flux = all_flux[sorter]

        period, t0, dur_hours_auto = simple_bls(
            all_time, all_flux, args.min_period, args.max_period
        )
        if args.duration_hours == 2.0:
            args.duration_hours = dur_hours_auto
    else:
        period = args.period
        if args.t0 is not None:
            t0 = args.t0
        else:
            # t0 bilinmiyorsa ilk sektörün ortasını kullan
            t0 = float(np.mean(selected[0].time))

    logger.info(f"Kullanılan: period={period:.5f}d, t0={t0:.5f}, dur={args.duration_hours:.3f}h")

    dur_phase = (args.duration_hours / 24.0) / period
    logger.info(f"dur_phase={dur_phase:.4f}")

    if dur_phase > 0.12:
        logger.warning(
            f"dur_phase={dur_phase:.3f} > 0.12 — periyot çok kısa, "
            "L4/L5 pencereleri güvenilmez. İptal ediliyor."
        )
        return

    # 3. Her sektörü fold et ve pencere skorlarını hesapla
    sector_results = []

    for sec_data in selected:
        time_s = sec_data.time
        flux_s = detrend_sector(sec_data.time, sec_data.flux)

        phase_s = fold(time_s, period, t0)
        scores_s = score_all_windows(phase_s, flux_s, dur_phase)
        bc_s, bm_s = bin_lc(phase_s, flux_s)

        sector_results.append({
            "sector": sec_data.sector,
            "n_points": sec_data.n_points_clean,
            "duration_days": sec_data.duration_days,
            "scores": scores_s,
            "bin_centers": bc_s.tolist(),
            "bin_medians": bm_s.tolist(),
            "dur_phase": dur_phase,
        })

        logger.info(
            f"S{sec_data.sector}: "
            f"primary={scores_s['primary']['sig']:.1f}σ  "
            f"L4={scores_s['L4']['sig']:.1f}σ  "
            f"L5={scores_s['L5']['sig']:.1f}σ  "
            f"sec={scores_s['secondary']['sig']:.1f}σ"
        )

    # 4. Cross-sector ASI
    l4_asi = cross_sector_asi([r["scores"] for r in sector_results], "L4")
    l5_asi = cross_sector_asi([r["scores"] for r in sector_results], "L5")

    l4_sigs = [r["scores"]["L4"]["sig"] for r in sector_results]
    l5_sigs = [r["scores"]["L5"]["sig"] for r in sector_results]
    primary_sigs = [r["scores"]["primary"]["sig"] for r in sector_results]
    secondary_sigs = [r["scores"]["secondary"]["sig"] for r in sector_results]

    verdict, reason = cross_sector_verdict(
        l4_asi=l4_asi,
        l5_asi=l5_asi,
        l4_sigs=l4_sigs,
        l5_sigs=l5_sigs,
        primary_sigs=primary_sigs,
        secondary_sigs=secondary_sigs,
        sector_results=sector_results,
        dur_phase=dur_phase,
        odd_even=args.odd_even,
    )

    # 5. Ekran özeti
    sector_nums = [r["sector"] for r in sector_results]
    print()
    print("=" * 80)
    print(f"MULTI-SECTOR CO-ORBITAL SEARCH: TIC {args.tic}")
    print("=" * 80)
    print(f"Period     : {period:.5f} d")
    print(f"T0         : {t0:.5f}")
    print(f"Dur        : {args.duration_hours:.3f} h  (dur_phase={dur_phase:.4f})")
    print(f"Sectors    : {sector_nums}")
    print()
    print(f"{'Sector':>8} {'Primary':>10} {'Secondary':>12} {'L4':>8} {'L5':>8} {'Pre-sh':>8} {'Post-sh':>8}")
    print("-" * 80)
    for res in sector_results:
        sc = res["scores"]
        print(
            f"S{res['sector']:>7} "
            f"{sc['primary']['depth_ppm']:>5.0f}({sc['primary']['sig']:>5.1f}σ) "
            f"{sc['secondary']['depth_ppm']:>5.0f}({sc['secondary']['sig']:>5.1f}σ) "
            f"{sc['L4']['depth_ppm']:>4.0f}({sc['L4']['sig']:>4.1f}σ) "
            f"{sc['L5']['depth_ppm']:>4.0f}({sc['L5']['sig']:>4.1f}σ) "
            f"{sc['pre_shoulder']['depth_ppm']:>4.0f}({sc['pre_shoulder']['sig']:>4.1f}σ) "
            f"{sc['post_shoulder']['depth_ppm']:>4.0f}({sc['post_shoulder']['sig']:>4.1f}σ)"
        )
    print()
    print(f"L4 Cross-Sector ASI : {l4_asi:.3f}")
    print(f"L5 Cross-Sector ASI : {l5_asi:.3f}")
    print(f"Verdict             : {verdict}")
    print(f"Reason              : {reason}")
    print("=" * 80)

    # 6. JSON rapor
    report = {
        "tic": args.tic,
        "target_id": target_id,
        "parameters": {
            "period": period,
            "t0": t0,
            "duration_hours": args.duration_hours,
            "dur_phase": dur_phase,
            "auto_period": args.auto_period,
        },
        "sectors_analyzed": sector_nums,
        "sector_results": [
            {
                "sector": r["sector"],
                "n_points": r["n_points"],
                "scores": r["scores"],
            }
            for r in sector_results
        ],
        "cross_sector": {
            "L4_ASI": l4_asi,
            "L5_ASI": l5_asi,
            "L4_sigs_per_sector": dict(zip(sector_nums, l4_sigs)),
            "L5_sigs_per_sector": dict(zip(sector_nums, l5_sigs)),
        },
        "verdict": verdict,
        "reason": reason,
    }

    json_path = outdir / f"TIC_{args.tic}_multisector_coorbital.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info(f"JSON yazıldı: {json_path}")

    # 7. Figür
    fig_path = outdir / f"TIC_{args.tic}_multisector_coorbital.png"
    make_figure(
        tic_id=args.tic,
        sector_results=sector_results,
        period=period,
        outpath=fig_path,
    )


if __name__ == "__main__":
    main()
