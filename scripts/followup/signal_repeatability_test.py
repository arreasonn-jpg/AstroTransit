#!/usr/bin/env python3
"""
Signal Repeatability Test

Fikir: LC'yi zamana göre ikiye bölerek aynı faz sinyalinin
her iki yarıda da var olup olmadığını test eder.

Gerçek bir sinyal (gezegen, trojan, disk) her iki yarıda da
benzer güçte görünmeli. Gürültü veya tek-event artefaktlar
sadece bir yarıda görünür.
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

try:
    import lightkurve as lk
except ImportError:
    raise ImportError("pip install lightkurve")


def download_and_flatten(tic_id: int, sector: int):
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
    try:
        sp = UnivariateSpline(time, flux, k=3, s=len(time) * 0.8)
        flux = flux / sp(time)
    except Exception:
        pass
    return time, flux


def fold(time, period, t0):
    return ((time - t0 + 0.5 * period) % period) / period - 0.5


def scan_phases(phase, flux, dur_phase, steps=500):
    centers = np.linspace(-0.5, 0.5, steps)
    sig_map = np.zeros(steps)
    for i, c in enumerate(centers):
        shifted = ((phase - c + 0.5) % 1.0) - 0.5
        in_w = np.abs(shifted) < (dur_phase / 2.0)
        if in_w.sum() < 5:
            continue
        in_f = flux[in_w]
        out_f = flux[~in_w]
        if len(out_f) < 10:
            continue
        baseline = np.nanmedian(out_f)
        sigma = max(np.nanstd(out_f), 1e-9)
        depth = baseline - np.nanmedian(in_f)
        sig_map[i] = depth / sigma * np.sqrt(len(in_f))
    return centers, sig_map


def get_clean_peaks(centers, sig_map, dur_phase, min_sig=3.0):
    pos = np.where(sig_map > 0, sig_map, 0)
    peaks, _ = find_peaks(pos, height=min_sig, distance=10)
    result = []
    for p in peaks:
        phase_val = centers[p]
        sig_val = sig_map[p]
        if abs(phase_val) > dur_phase * 3.5:
            result.append((phase_val, sig_val))
    return sorted(result, key=lambda x: x[1], reverse=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tic", type=int, required=True)
    parser.add_argument("--sector", type=int, required=True)
    parser.add_argument("--period", type=float, required=True)
    parser.add_argument("--t0", type=float, required=True)
    parser.add_argument("--duration-hours", type=float, required=True)
    parser.add_argument("--output-dir", type=str, default="outputs_architecture_review")
    args = parser.parse_args()

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Repeatability test: TIC {args.tic} S{args.sector}")

    time, flux = download_and_flatten(args.tic, args.sector)
    phase = fold(time, args.period, args.t0)
    dur_phase = (args.duration_hours / 24.0) / args.period

    # LC'yi zamana göre ikiye böl
    t_mid = np.median(time)
    mask_first = time <= t_mid
    mask_second = time > t_mid

    n_first = mask_first.sum()
    n_second = mask_second.sum()
    logger.info(f"First half: {n_first} pts, Second half: {n_second} pts")

    # Her parçada tarama yap
    centers, sig_full = scan_phases(phase, flux, dur_phase)
    centers_f, sig_first = scan_phases(phase[mask_first], flux[mask_first], dur_phase)
    centers_s, sig_second = scan_phases(phase[mask_second], flux[mask_second], dur_phase)

    peaks_full = get_clean_peaks(centers, sig_full, dur_phase)
    peaks_first = get_clean_peaks(centers_f, sig_first, dur_phase)
    peaks_second = get_clean_peaks(centers_s, sig_second, dur_phase)

    # Tutarlılık analizi — her tam-LC tepesi her iki yarıda da var mı?
    def nearest_sig(target_phase, peaks, tolerance=0.015):
        best = 0.0
        for p, s in peaks:
            if abs(p - target_phase) < tolerance:
                best = max(best, s)
        return best

    print()
    print("=" * 70)
    print(f"SIGNAL REPEATABILITY: TIC {args.tic} S{args.sector}")
    print("=" * 70)
    print(f"{'Phase':>8} {'Full':>8} {'First½':>8} {'Second½':>9} {'Verdict':>20}")
    print("-" * 70)

    report_peaks = []
    for phase_val, sig_val in peaks_full[:8]:
        sig_f = nearest_sig(phase_val, peaks_first)
        sig_s = nearest_sig(phase_val, peaks_second)

        # Karar
        both_above_3 = sig_f >= 3.0 and sig_s >= 3.0
        both_above_2 = sig_f >= 2.0 and sig_s >= 2.0
        ratio = min(sig_f, sig_s) / max(sig_f, sig_s, 0.1)

        if both_above_3 and ratio >= 0.40:
            verdict = "REPEATABLE ★"
        elif both_above_2 and ratio >= 0.25:
            verdict = "PARTIALLY REPEATABLE"
        elif sig_f >= 4.0 and sig_s < 2.0:
            verdict = "FIRST HALF ONLY"
        elif sig_s >= 4.0 and sig_f < 2.0:
            verdict = "SECOND HALF ONLY"
        else:
            verdict = "NOT REPEATABLE"

        # Faz etiketi
        p = phase_val
        label = ""
        if abs(abs(p) - 0.166) < 0.02:
            label = "(L4/L5)"
        elif abs(abs(p) - 0.5) < 0.04:
            label = "(Sec)"
        elif abs(abs(p) - 0.25) < 0.03:
            label = "(Quad)"

        print(
            f"{phase_val:>+8.4f} {sig_val:>8.1f} {sig_f:>8.1f} {sig_s:>9.1f} "
            f"{verdict:>20} {label}"
        )

        report_peaks.append({
            "phase": round(float(phase_val), 5),
            "sig_full": round(float(sig_val), 2),
            "sig_first_half": round(float(sig_f), 2),
            "sig_second_half": round(float(sig_s), 2),
            "verdict": verdict,
        })

    # Özet karar
    repeatable = [p for p in report_peaks if "REPEATABLE ★" in p["verdict"]]
    partial = [p for p in report_peaks if "PARTIALLY" in p["verdict"]]

    print()
    print("SUMMARY:")
    lagrange_repeatable = [
        p for p in repeatable
        if 0.13 <= abs(p["phase"]) <= 0.20
    ]
    lagrange_partial = [
        p for p in partial
        if 0.13 <= abs(p["phase"]) <= 0.20
    ]

    if lagrange_repeatable:
        best = max(lagrange_repeatable, key=lambda x: x["sig_full"])
        print(f"  ★★ LAGRANGE-ZONE SIGNAL CONFIRMED REPEATABLE")
        print(f"     Phase: {best['phase']:+.4f}, Full: {best['sig_full']:.1f}σ")
        print(f"     First½: {best['sig_first_half']:.1f}σ, Second½: {best['sig_second_half']:.1f}σ")
        print(f"     COORBITAL REVIEW: STRONGLY SUPPORTED")
    elif lagrange_partial:
        best = max(lagrange_partial, key=lambda x: x["sig_full"])
        print(f"  ○ LAGRANGE-ZONE SIGNAL PARTIALLY REPEATABLE")
        print(f"     Phase: {best['phase']:+.4f}, Full: {best['sig_full']:.1f}σ")
        print(f"     First½: {best['sig_first_half']:.1f}σ, Second½: {best['sig_second_half']:.1f}σ")
        print(f"     COORBITAL REVIEW: WORTH MANUAL INSPECTION")
    else:
        print(f"  ✓ No repeatable Lagrange-zone signal found.")
        print(f"    Off-primary signals are likely noise or single-event artifacts.")

    print("=" * 70)

    # Figür
    fig, axes = plt.subplots(3, 1, figsize=(14, 12), sharex=True)

    for ax, sig, label, color in zip(
        axes,
        [sig_full, sig_first, sig_second],
        ["Full LC", f"First Half (n={n_first})", f"Second Half (n={n_second})"],
        ["blue", "green", "orange"],
    ):
        ax.plot(centers, sig, color=color, lw=1.2, label=label)
        ax.axvline(0, color="black", ls="--", lw=0.8)
        ax.axvline(-0.166, color="orange", ls=":", lw=1.0, label="L4")
        ax.axvline(0.166, color="green", ls=":", lw=1.0, label="L5")
        ax.axhline(3.0, color="gray", ls=":", lw=0.7)
        ax.axhline(5.0, color="red", ls=":", lw=0.7)
        ax.set_ylabel("Sigma")
        ax.set_title(label)
        ax.grid(True, alpha=0.2)
        ax.legend(fontsize=7, loc="upper right")
        ax.set_xlim(-0.5, 0.5)

    axes[-1].set_xlabel("Phase")
    fig.suptitle(
        f"Repeatability Test: TIC {args.tic} S{args.sector} (P={args.period:.4f}d)",
        fontsize=12,
    )
    plt.tight_layout()

    fig_path = outdir / f"TIC_{args.tic}_S{args.sector}_repeatability.png"
    plt.savefig(fig_path, dpi=160, bbox_inches="tight")
    plt.close()
    logger.info(f"Figür yazıldı: {fig_path}")

    json_path = outdir / f"TIC_{args.tic}_S{args.sector}_repeatability.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump({
            "tic": args.tic,
            "sector": args.sector,
            "period": args.period,
            "t0": args.t0,
            "duration_hours": args.duration_hours,
            "dur_phase": dur_phase,
            "n_first": int(n_first),
            "n_second": int(n_second),
            "peaks": report_peaks,
        }, f, indent=2)
    logger.info(f"JSON yazıldı: {json_path}")


if __name__ == "__main__":
    main()
