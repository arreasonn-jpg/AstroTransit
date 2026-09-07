#!/usr/bin/env python3
"""
Architecture Candidate Review Script

Amaç
----
Seçilen bir adayın TESS ışık eğrisini indirir, detrend eder
ve faz uzayında şu bölgeleri tarayarak mimari anomali arar:

1. Primary Transit (phase=0)
2. Immediate Shoulders (phase ±0.03) → halka / debris / outgassing
3. Lagrange/Trojan window (phase ±0.166 ~ L4/L5) → station-keeping / co-orbital
4. Secondary Eclipse / Anti-transit (phase 0.5) → eclipsing binary / background

Özellikler
----------
- Sadece SPOC LC indirir, basit spline ile detrend eder
- Folded light curve üzerinde binned median ile gürültüyü baskılar
- Çıktı olarak JSON rapor + PNG figür verir

Kullanım
--------
    python scripts/followup/review_architecture_candidate.py \
        --tic 357370384 \
        --sector 57 \
        --period 13.4939 \
        --t0 3105.123 \
        --duration-hours 2.5
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    import lightkurve as lk
except ImportError:
    raise ImportError("Lütfen lightkurve paketini yükleyin: pip install lightkurve")

from scipy.interpolate import UnivariateSpline


def download_and_clean_lc(tic_id: int, sector: int):
    search = lk.search_lightcurve(
        f"TIC {tic_id}",
        mission="TESS",
        author="SPOC",
        sector=sector,
        exptime=120,
    )
    if len(search) == 0:
        logger.error(f"TIC {tic_id} S{sector} için SPOC LC bulunamadı.")
        return None

    lc = search[0].download()
    time = np.array(lc.time.value, dtype=float)
    flux = np.array(lc.flux.value, dtype=float)
    flux_err = np.array(lc.flux_err.value, dtype=float)
    quality = np.array(lc.quality.value, dtype=int)

    # Basit temizlik
    valid = np.isfinite(time) & np.isfinite(flux) & (quality == 0)
    time = time[valid]
    flux = flux[valid]
    flux_err = flux_err[valid]

    # Normalize
    med = np.nanmedian(flux)
    flux = flux / med
    flux_err = flux_err / med

    return time, flux, flux_err


def detrend_lightcurve(time: np.ndarray, flux: np.ndarray, knot_spacing_days: float = 1.0):
    """Çok basit spline tabanlı detrending."""
    knots = np.arange(time.min() + knot_spacing_days, time.max(), knot_spacing_days)
    if len(knots) < 2:
        return flux

    # Sığdırma işlemi: aşırı düşük flux değerlerini (transitleri) kısmen dışlamak için ağırlık
    med = np.median(flux)
    std = np.std(flux)
    weights = np.where(flux < (med - 2 * std), 0.1, 1.0)

    spline = UnivariateSpline(time, flux, w=weights, k=3, s=len(time)*0.5)
    trend = spline(time)
    
    detrended = flux / trend
    return detrended


def calculate_window_score(
    phase: np.ndarray,
    flux: np.ndarray,
    target_phase: float,
    window_width: float,
    baseline: float = 1.0,
) -> dict:
    """Belirli bir faz penceresindeki sinyalin gücünü ölçer."""
    # Fazı -0.5 ile +0.5 arasına çek ve hedefe göre hizala
    shifted_phase = ((phase - target_phase + 0.5) % 1.0) - 0.5
    
    in_window = np.abs(shifted_phase) < (window_width / 2.0)
    out_window = ~in_window

    n_pts = int(np.sum(in_window))
    if n_pts < 10:
        return {"n_points": n_pts, "median_depth_ppm": 0.0, "significance": 0.0}

    in_flux = flux[in_window]
    out_flux = flux[out_window]

    in_med = np.median(in_flux)
    out_med = np.median(out_flux) if len(out_flux) > 0 else baseline
    out_std = np.std(out_flux) if len(out_flux) > 0 else 1.0

    depth = out_med - in_med
    depth_ppm = float(depth * 1e6)
    
    # Kaba bir SNR/Significance hesabı
    # sqrt(N) ile istatistiksel güveni artır
    sig = float((depth / max(out_std, 1e-6)) * np.sqrt(n_pts))

    return {
        "n_points": n_pts,
        "median_depth_ppm": round(depth_ppm, 2),
        "significance": round(sig, 2),
    }


def bin_folded_lc(phase: np.ndarray, flux: np.ndarray, bins: int = 150):
    """Görselleştirme için fazı bin'le."""
    bins_arr = np.linspace(-0.5, 0.5, bins + 1)
    bin_centers = 0.5 * (bins_arr[1:] + bins_arr[:-1])
    bin_medians = np.zeros(bins)
    
    for i in range(bins):
        mask = (phase >= bins_arr[i]) & (phase < bins_arr[i+1])
        if np.sum(mask) > 0:
            bin_medians[i] = np.median(flux[mask])
        else:
            bin_medians[i] = np.nan
            
    return bin_centers, bin_medians


def plot_architecture(
    tic_id: int,
    sector: int,
    phase: np.ndarray,
    flux: np.ndarray,
    bin_phase: np.ndarray,
    bin_flux: np.ndarray,
    scores: dict,
    outpath: Path,
):
    fig, axes = plt.subplots(3, 1, figsize=(12, 14), gridspec_kw={'height_ratios': [2, 1, 1]})
    
    # 1. Tam faz
    ax = axes[0]
    ax.scatter(phase, flux, s=1, color="gray", alpha=0.3, label="Unbinned")
    ax.scatter(bin_phase, bin_flux, s=20, color="blue", label="Binned")
    
    # Trojan pencerelerini çiz (±1/6)
    ax.axvspan(-0.166 - 0.02, -0.166 + 0.02, color="orange", alpha=0.1, label="L4/Trojan Window")
    ax.axvspan(0.166 - 0.02, 0.166 + 0.02, color="green", alpha=0.1, label="L5/Trojan Window")
    
    # Secondary penceresi
    ax.axvspan(-0.5, -0.48, color="red", alpha=0.1, label="Secondary/EB")
    ax.axvspan(0.48, 0.5, color="red", alpha=0.1)

    ax.set_title(f"TIC {tic_id} S{sector} - Full Phase Folded")
    ax.set_xlim(-0.5, 0.5)
    ax.set_ylim(np.nanpercentile(flux, 0.1), np.nanpercentile(flux, 99.9))
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize=8)

    # 2. Ana transit zoom + Shoulders
    ax = axes[1]
    mask = np.abs(phase) < 0.1
    ax.scatter(phase[mask], flux[mask], s=2, color="gray", alpha=0.5)
    
    b_mask = np.abs(bin_phase) < 0.1
    ax.scatter(bin_phase[b_mask], bin_flux[b_mask], s=30, color="blue")
    
    # Shoulder bölgeleri
    ax.axvspan(-0.06, -0.02, color="purple", alpha=0.1, label="Pre-Shoulder")
    ax.axvspan(0.02, 0.06, color="cyan", alpha=0.1, label="Post-Shoulder")
    
    ax.set_title("Transit Zoom & Shoulder Windows")
    ax.set_xlim(-0.1, 0.1)
    ax.set_ylim(np.nanpercentile(flux[mask], 0.1), np.nanpercentile(flux[mask], 99.9))
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize=8)

    # 3. Text Panel / Score özeti
    ax = axes[2]
    ax.axis("off")
    
    text = (
        f"ARCHITECTURE SCORES\n"
        f"-------------------\n"
        f"L4 (Pre-Trojan)   : {scores['L4']['significance']:>5.1f} sig  ({scores['L4']['median_depth_ppm']:>5.0f} ppm)\n"
        f"L5 (Post-Trojan)  : {scores['L5']['significance']:>5.1f} sig  ({scores['L5']['median_depth_ppm']:>5.0f} ppm)\n"
        f"Pre-Shoulder      : {scores['pre_shoulder']['significance']:>5.1f} sig  ({scores['pre_shoulder']['median_depth_ppm']:>5.0f} ppm)\n"
        f"Post-Shoulder     : {scores['post_shoulder']['significance']:>5.1f} sig  ({scores['post_shoulder']['median_depth_ppm']:>5.0f} ppm)\n"
        f"Secondary Eclipse : {scores['secondary']['significance']:>5.1f} sig  ({scores['secondary']['median_depth_ppm']:>5.0f} ppm)\n"
    )
    
    ax.text(0.1, 0.5, text, family="monospace", va="center", fontsize=12)

    plt.tight_layout()
    plt.savefig(outpath, dpi=200, bbox_inches="tight")
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="Architecture Candidate Review")
    parser.add_argument("--tic", type=int, required=True)
    parser.add_argument("--sector", type=int, required=True)
    parser.add_argument("--period", type=float, required=True)
    parser.add_argument("--t0", type=float, required=True)
    parser.add_argument("--duration-hours", type=float, required=True)
    parser.add_argument("--output-dir", type=str, default="outputs_architecture_review")
    args = parser.parse_args()

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Review başlıyor: TIC {args.tic} S{args.sector}")
    
    # 1. İndir
    res = download_and_clean_lc(args.tic, args.sector)
    if res is None:
        return
    time, flux_raw, _ = res
    
    # 2. Detrend
    flux = detrend_lightcurve(time, flux_raw)
    
    # 3. Phase fold
    phase = ((time - args.t0 + 0.5 * args.period) % args.period) / args.period - 0.5
    
    # 4. Binning
    bin_phase, bin_flux = bin_folded_lc(phase, flux, bins=200)

    # 5. Pencereleri tarama
    # Transit fraction kabaca = (duration_hours / 24) / period
    dur_phase = (args.duration_hours / 24.0) / args.period
    
    # L4 / L5 kabaca ±1/6 faz (~±60 derece). Pencere genişliği transit süresi kadar olsun
    window_w = dur_phase * 1.5

    scores = {
        "primary": calculate_window_score(phase, flux, 0.0, dur_phase),
        "secondary": calculate_window_score(phase, flux, 0.5, dur_phase),
        "L4": calculate_window_score(phase, flux, -0.166, window_w),
        "L5": calculate_window_score(phase, flux, 0.166, window_w),
        "pre_shoulder": calculate_window_score(phase, flux, -dur_phase*1.5, dur_phase),
        "post_shoulder": calculate_window_score(phase, flux, dur_phase*1.5, dur_phase),
    }

    # 6. Rapor yaz
    report = {
        "tic": args.tic,
        "sector": args.sector,
        "parameters_used": {
            "period": args.period,
            "t0": args.t0,
            "duration_hours": args.duration_hours,
        },
        "scores": scores
    }
    
    json_path = outdir / f"TIC_{args.tic}_S{args.sector}_arch_review.json"
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)
        
    logger.info(f"JSON yazıldı: {json_path}")

    # 7. Çiz
    fig_path = outdir / f"TIC_{args.tic}_S{args.sector}_arch_review.png"
    plot_architecture(
        tic_id=args.tic,
        sector=args.sector,
        phase=phase,
        flux=flux,
        bin_phase=bin_phase,
        bin_flux=bin_flux,
        scores=scores,
        outpath=fig_path,
    )
    
    logger.info(f"Figür yazıldı: {fig_path}")

    print("\n--- ÖZET ---")
    print(f"Primary depth  : {scores['primary']['median_depth_ppm']:.0f} ppm  ({scores['primary']['significance']:.1f} sig)")
    print(f"Secondary depth: {scores['secondary']['median_depth_ppm']:.0f} ppm  ({scores['secondary']['significance']:.1f} sig)")
    print(f"L4 (Trojan)    : {scores['L4']['median_depth_ppm']:.0f} ppm  ({scores['L4']['significance']:.1f} sig)")
    print(f"L5 (Trojan)    : {scores['L5']['median_depth_ppm']:.0f} ppm  ({scores['L5']['significance']:.1f} sig)")

if __name__ == "__main__":
    main()
