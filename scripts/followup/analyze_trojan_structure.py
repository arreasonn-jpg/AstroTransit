#!/usr/bin/env python3
"""
Trojan & Co-orbital Structure Analyzer v2

Düzeltme: Detrending sadece transit-dışı noktalar üzerinde yapılır.
Bu sayede spline, transit şeklini öğrenmez ve faz uzayında
sahte sinyal üretmez.
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
from loguru import logger
import lightkurve as lk
from scipy.interpolate import UnivariateSpline

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def download_and_normalize(tic_id: int, sector: int):
    search = lk.search_lightcurve(
        f"TIC {tic_id}", sector=sector, author="SPOC", exptime=120
    )
    if len(search) == 0:
        raise FileNotFoundError(f"TIC {tic_id} S{sector}: LC bulunamadı.")
    lc = search[0].download()
    time = np.array(lc.time.value, dtype=float)
    flux = np.array(getattr(lc.flux, "value", lc.flux), dtype=float)
    quality = np.array(getattr(lc.quality, "value", lc.quality), dtype=int)
    valid = np.isfinite(time) & np.isfinite(flux) & (quality == 0)
    time, flux = time[valid], flux[valid]
    flux = flux / np.nanmedian(flux)
    return time, flux


def mask_transits(time, period, t0, duration_hours, width_factor=1.5):
    """Tüm transit event'leri maskele."""
    phase = ((time - t0) % period)
    phase = np.where(phase > period / 2, phase - period, phase)
    dur_days = (duration_hours / 24.0) * width_factor
    return np.abs(phase) < (dur_days / 2.0)


def detrend_oot_only(time, flux, transit_mask, knot_spacing=0.75):
    """
    Sadece transit-dışı (OOT) noktalar üzerinde spline sığdır.
    Sonra tüm LC'ye uygula.
    """
    oot_time = time[~transit_mask]
    oot_flux = flux[~transit_mask]

    if len(oot_time) < 20:
        return flux

    try:
        spline = UnivariateSpline(
            oot_time, oot_flux, k=3,
            s=len(oot_time) * 0.5,
        )
        trend = spline(time)
        trend = np.where(trend > 0.5, trend, 1.0)
        return flux / trend
    except Exception as exc:
        logger.warning(f"Spline hatası: {exc}")
        return flux


def score_window(phase, flux, center, half_width, min_pts=5):
    shifted = ((phase - center + 0.5) % 1.0) - 0.5
    in_w = np.abs(shifted) < half_width
    out_w = ~in_w

    n_in = int(in_w.sum())
    if n_in < min_pts:
        return {"n": n_in, "depth_ppm": 0.0, "sig": 0.0}

    in_flux = flux[in_w]
    out_flux = flux[out_w]

    # Sadece sonlu değerleri kullan
    in_flux = in_flux[np.isfinite(in_flux)]
    out_flux = out_flux[np.isfinite(out_flux)]

    if len(in_flux) < min_pts or len(out_flux) < 10:
        return {"n": n_in, "depth_ppm": 0.0, "sig": 0.0}

    baseline = np.nanmedian(out_flux)
    sigma = np.nanstd(out_flux)

    depth_ppm = float((baseline - np.nanmedian(in_flux)) * 1e6)
    sig = float(depth_ppm / 1e6 / max(sigma, 1e-9) * np.sqrt(len(in_flux)))

    return {
        "n": len(in_flux),
        "depth_ppm": round(depth_ppm, 1),
        "sig": round(sig, 2),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tic", type=int, required=True)
    parser.add_argument("--sector", type=int, required=True)
    parser.add_argument("--period", type=float, required=True)
    parser.add_argument("--t0", type=float, required=True)
    parser.add_argument("--duration-hours", type=float, required=True)
    parser.add_argument("--depth", type=float, required=True)
    parser.add_argument(
        "--output-dir", type=str, default="outputs_architecture_review"
    )
    args = parser.parse_args()

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    logger.info(f"TIC {args.tic} S{args.sector}: Trojan yapı analizi başlıyor (v2)")

    # 1. İndir
    time, flux_raw = download_and_normalize(args.tic, args.sector)

    # 2. Transit maskesi — geniş pencere
    transit_mask = mask_transits(
        time, args.period, args.t0, args.duration_hours, width_factor=2.0
    )
    logger.info(
        f"Transit mask: {transit_mask.sum()} nokta ({transit_mask.mean()*100:.1f}% LC)"
    )

    # 3. OOT-only spline detrend
    flux_flat = detrend_oot_only(time, flux_raw, transit_mask, knot_spacing=0.75)

    # 4. Ana transiti NaN ile maskele (residual için)
    transit_mask_tight = mask_transits(
        time, args.period, args.t0, args.duration_hours, width_factor=0.8
    )
    flux_residual = flux_flat.copy()
    flux_residual[transit_mask_tight] = np.nan

    # 5. Faz-fold
    phase = ((time - args.t0 + 0.5 * args.period) % args.period) / args.period - 0.5
    dur_phase = (args.duration_hours / 24.0) / args.period
    window_w = max(dur_phase * 1.5, 0.005)

    # 6. Pencere skorları (residual üzerinde)
    windows = {
        "primary": score_window(phase, flux_residual, 0.000, dur_phase),
        "secondary": score_window(phase, flux_residual, 0.500, dur_phase),
        "L4": score_window(phase, flux_residual, -0.1667, window_w),
        "L5": score_window(phase, flux_residual, 0.1667, window_w),
        "pre_shoulder": score_window(phase, flux_residual, -dur_phase * 1.8, dur_phase),
        "post_shoulder": score_window(phase, flux_residual, dur_phase * 1.8, dur_phase),
    }

    # 7. Sonuçlar
    print()
    print("=" * 60)
    print(f"TIC {args.tic} S{args.sector} — TROJAN/CO-ORBITAL ANALYSIS v2")
    print(f"Primary transit masked (OOT-only detrend)")
    print("=" * 60)
    for name, sc in windows.items():
        print(
            f"{name:<14}: {sc['depth_ppm']:>7.1f} ppm  "
            f"{sc['sig']:>+6.2f} sigma  (n={sc['n']})"
        )

    print()
    l5 = windows["L5"]
    l4 = windows["L4"]
    primary_residual = windows["primary"]

    # Karar
    if primary_residual["sig"] > 3.0:
        print(
            "⚠ PRIMARY RESIDUAL STILL ELEVATED — primary mask may be too narrow."
        )
        print(
            "   Interpret L4/L5 results with caution."
        )
    elif l5["sig"] >= 5.0 and l4["sig"] < 3.0:
        print(
            "★ ASYMMETRIC CO-ORBITAL SIGNAL: Strong L5, weak L4"
        )
        print(
            "   Consistent with mass clump near L5 Lagrange point."
        )
        print(
            "   Station-keeping or trojan cluster hypothesis: SUPPORTED (single-sector)"
        )
    elif l5["sig"] >= 5.0 and l4["sig"] >= 3.0:
        print(
            "★ SYMMETRIC CO-ORBITAL SIGNAL: Both L4 and L5 elevated"
        )
        print(
            "   Consistent with debris/ring structure or multi-clump trojan system."
        )
    elif l4["sig"] >= 5.0 and l5["sig"] < 3.0:
        print(
            "★ ASYMMETRIC CO-ORBITAL SIGNAL: Strong L4, weak L5"
        )
        print(
            "   Consistent with mass clump near L4 Lagrange point."
        )
    else:
        print(
            "✓ NO SIGNIFICANT CO-ORBITAL STRUCTURE after primary removal."
        )
        print(
            "  L4/L5 signals are within noise expectations."
        )

    print("=" * 60)

    # 8. Figür
    fig, axes = plt.subplots(2, 1, figsize=(12, 8))

    # Panel 1: Tam fold
    ax = axes[0]
    good = np.isfinite(flux_residual)
    ax.scatter(phase[good], flux_residual[good], s=1, color="gray", alpha=0.3)

    # Binning
    bin_edges = np.linspace(-0.5, 0.5, 201)
    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
    bin_medians = np.full(len(bin_centers), np.nan)
    for i in range(len(bin_centers)):
        m = (
            good &
            (phase >= bin_edges[i]) &
            (phase < bin_edges[i + 1]) &
            (np.abs(phase) > dur_phase * 0.9)
        )
        if m.sum() >= 3:
            bin_medians[i] = np.median(flux_residual[m])

    valid_b = np.isfinite(bin_medians)
    ax.scatter(bin_centers[valid_b], bin_medians[valid_b], s=10, color="blue")
    ax.axvspan(-0.1667 - window_w, -0.1667 + window_w, color="orange", alpha=0.15, label="L4")
    ax.axvspan(0.1667 - window_w, 0.1667 + window_w, color="green", alpha=0.15, label="L5")
    ax.axhline(1.0, color="k", lw=0.5, ls="--")
    ax.set_title(
        f"TIC {args.tic} S{args.sector} — Residual LC after primary removal\n"
        f"L4={l4['depth_ppm']:.0f}ppm({l4['sig']:.1f}σ)  "
        f"L5={l5['depth_ppm']:.0f}ppm({l5['sig']:.1f}σ)"
    )
    ax.set_xlim(-0.5, 0.5)
    ax.set_xlabel("Phase")
    ax.grid(True, alpha=0.2)
    ax.legend()

    # Panel 2: L4/L5 zoom
    ax = axes[1]
    for label_p, center, color in [("L4", -0.1667, "orange"), ("L5", 0.1667, "green")]:
        near = np.abs(((phase - center + 0.5) % 1.0) - 0.5) < 0.08
        near_good = near & good
        if near_good.sum() > 5:
            p_shifted = ((phase[near_good] - center + 0.5) % 1.0) - 0.5
            ax.scatter(p_shifted, flux_residual[near_good], s=4, color=color, alpha=0.5, label=label_p)
    ax.axhline(1.0, color="k", lw=0.5, ls="--")
    ax.set_title("L4 / L5 zoom (primary removed)")
    ax.set_xlim(-0.08, 0.08)
    ax.set_xlabel("Phase relative to L4/L5 center")
    ax.grid(True, alpha=0.2)
    ax.legend()

    plt.tight_layout()
    fig_path = outdir / f"TIC_{args.tic}_S{args.sector}_trojan_v2.png"
    plt.savefig(fig_path, dpi=160, bbox_inches="tight")
    plt.close()
    logger.info(f"Figür yazıldı: {fig_path}")

    # 9. JSON
    report = {
        "tic": args.tic,
        "sector": args.sector,
        "method": "OOT-only detrend + primary removal v2",
        "parameters": {
            "period": args.period,
            "t0": args.t0,
            "duration_hours": args.duration_hours,
            "depth": args.depth,
        },
        "windows": windows,
    }
    json_path = outdir / f"TIC_{args.tic}_S{args.sector}_trojan_v2.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    logger.info(f"JSON yazıldı: {json_path}")


if __name__ == "__main__":
    main()
