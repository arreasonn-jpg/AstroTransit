#!/usr/bin/env python3
"""
Phase Space Power Map Generator

Amaç:
Sadece L4/L5 gibi önceden belirlenmiş fazlara bakmak yerine,
faz uzayının tamamını (0.0 - 1.0) tarayarak transit-benzeri sinyallerin
gücünü sürekli bir fonksiyon olarak hesaplamak.

Çıktı:
- Faz vs SNR grafiği
- En güçlü 3 ikincil sinyalin (off-primary) fazı ve gücü
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger
import lightkurve as lk
from scipy.interpolate import UnivariateSpline
from scipy.signal import find_peaks

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def download_and_normalize(tic_id: int, sector: int):
    search = lk.search_lightcurve(f"TIC {tic_id}", sector=sector, author="SPOC", exptime=120)
    if len(search) == 0:
        raise FileNotFoundError(f"TIC {tic_id} S{sector}: LC bulunamadı.")
    lc = search[0].download()
    time = np.array(lc.time.value, dtype=float)
    flux = np.array(lc.flux.value, dtype=float)
    quality = np.array(lc.quality.value, dtype=int)
    valid = np.isfinite(time) & np.isfinite(flux) & (quality == 0)
    time, flux = time[valid], flux[valid]
    
    # Basit Detrending (Sadece uzun vadeli trendleri al)
    med = np.nanmedian(flux)
    flux = flux / med
    knots = np.arange(time.min(), time.max(), 1.0)
    if len(knots) >= 4:
        spline = UnivariateSpline(time, flux, k=3, s=len(time)*0.8)
        flux = flux / spline(time)
        
    return time, flux

def scan_phase_space(phase: np.ndarray, flux: np.ndarray, window_width: float, steps: int = 500):
    """0.0 ile 1.0 arasındaki faz uzayını tarar."""
    scan_phases = np.linspace(-0.5, 0.5, steps)
    sig_map = np.zeros(steps)
    depth_map = np.zeros(steps)
    
    for i, p_center in enumerate(scan_phases):
        shifted_phase = ((phase - p_center + 0.5) % 1.0) - 0.5
        in_w = np.abs(shifted_phase) < (window_width / 2.0)
        
        if np.sum(in_w) < 5:
            continue
            
        in_flux = flux[in_w]
        out_flux = flux[~in_w]
        
        baseline = np.nanmedian(out_flux) if len(out_flux) > 10 else 1.0
        out_std = np.nanstd(out_flux) if len(out_flux) > 10 else 1e-5
        
        depth = baseline - np.nanmedian(in_flux)
        sig = (depth / max(out_std, 1e-9)) * np.sqrt(len(in_flux))
        
        depth_map[i] = depth * 1e6
        sig_map[i] = sig
        
    return scan_phases, depth_map, sig_map

def find_anomalous_peaks(scan_phases, sig_map, primary_phase_width):
    """
    Ana transit hariç, faz uzayındaki en güçlü tepe noktalarını bulur.

    Üç bölge tanımlanır:
        Zone A: Transit kontamine bölge — |phase| < dur * 3.0
        Zone B: Temiz off-transit bölge — dur*3.0 < |phase| < 0.40
        Zone C: Secondary / anti-transit — |phase| > 0.40

    Sadece Zone B ve C ayrı bölge olarak etiketlenir.
    Zone A sinyalleri "transit-overlapping" olarak işaretlenir.
    """
    sig_positive = np.where(sig_map > 0, sig_map, 0)
    peaks, _ = find_peaks(sig_positive, height=3.0, distance=15)

    peak_phases = scan_phases[peaks]
    peak_sigs = sig_map[peaks]

    valid_peaks = []
    for p, s in zip(peak_phases, peak_sigs):
        abs_p = np.abs(p)
        if abs_p <= primary_phase_width * 3.0:
            zone = "A_TRANSIT_ZONE"
        elif abs_p <= 0.40:
            zone = "B_CLEAN_OFFPRIMARY"
        else:
            zone = "C_SECONDARY_ZONE"
        valid_peaks.append((p, s, zone))

    valid_peaks.sort(key=lambda x: x[1], reverse=True)
    return valid_peaks

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tic", type=int, required=True)
    parser.add_argument("--sector", type=int, required=True)
    parser.add_argument("--period", type=float, required=True)
    parser.add_argument("--t0", type=float, required=True)
    parser.add_argument("--duration-hours", type=float, required=True)
    args = parser.parse_args()

    outdir = Path("outputs_architecture_review")
    outdir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Kör Faz Taraması başlıyor: TIC {args.tic} S{args.sector}")
    time, flux = download_and_normalize(args.tic, args.sector)
    
    # Phase fold
    phase = ((time - args.t0 + 0.5 * args.period) % args.period) / args.period - 0.5
    dur_phase = (args.duration_hours / 24.0) / args.period
    
    # Taramayı yap
    scan_phases, depth_map, sig_map = scan_phase_space(phase, flux, dur_phase, steps=1000)
    
    # Tepe noktalarını bul
    peaks = find_anomalous_peaks(scan_phases, sig_map, dur_phase)

    print("\n" + "="*60)
    print(f"PHASE SPACE POWER MAP: TIC {args.tic} S{args.sector}")
    print("="*60)
    print(f"Primary Transit Phase: 0.0 (Width: {dur_phase:.3f})")
    clean_peaks = [(p, s, z) for p, s, z in peaks if z != "A_TRANSIT_ZONE"]
    transit_overlap = [(p, s, z) for p, s, z in peaks if z == "A_TRANSIT_ZONE"]

    def phase_label(p):
        if abs(abs(p) - 0.5) < 0.05: return "(Secondary)"
        if abs(p - 0.166) < 0.05: return "(L5)"
        if abs(p + 0.166) < 0.05: return "(L4)"
        if abs(abs(p) - 0.25) < 0.04: return "(Quadrature)"
        return ""

    print(f"\nZone B+C: Off-primary independent signals:")
    if clean_peaks:
        for i, (p, s, z) in enumerate(clean_peaks[:5]):
            lbl = phase_label(p)
            print(f"  {i+1}. Phase: {p:+.4f}  |  {s:.1f} sigma  [{z}] {lbl}")
    else:
        print("  None above 3 sigma threshold.")

    print(f"\nZone A: Transit-overlapping signals (may be shoulder/ingress/egress):")
    if transit_overlap:
        for i, (p, s, z) in enumerate(transit_overlap[:3]):
            lbl = phase_label(p)
            print(f"  {i+1}. Phase: {p:+.4f}  |  {s:.1f} sigma  [{z}] {lbl}")
    else:
        print("  None.")

    # Mimari karar
    b_peaks = [(p, s) for p, s, z in peaks if z == "B_CLEAN_OFFPRIMARY"]
    c_peaks = [(p, s) for p, s, z in peaks if z == "C_SECONDARY_ZONE"]

    print("\nARCHITECTURE DECISION:")
    if any(s >= 6.0 for _, s in b_peaks):
        print("  ★ STRONG OFF-PRIMARY SIGNAL IN CLEAN ZONE B")
        lagrange = [(p, s) for p, s in b_peaks if 0.13 < abs(p) < 0.20]
        if lagrange:
            best = max(lagrange, key=lambda x: x[1])
            print(f"    → Lagrange-zone signal at phase {best[0]:+.3f}, {best[1]:.1f} sigma")
            print("    → COORBITAL REVIEW: HIGH PRIORITY")
        else:
            print("    → Off-primary but not at standard Lagrange phases")
            print("    → ARCHITECTURE REVIEW: MODERATE PRIORITY")
    elif any(s >= 4.0 for _, s in b_peaks):
        print("  ○ MODERATE SIGNAL IN CLEAN ZONE B — worth manual review")
    else:
        print("  ✓ NO SIGNIFICANT INDEPENDENT OFF-PRIMARY SIGNAL")
    
    if any(s >= 6.0 for _, s in c_peaks):
        print("  ⚠ Strong secondary zone signal — EB scenario should be ruled out first")
    print("="*60 + "\n")

    # Çizim
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))

    # Üst panel: Full range
    ax1.plot(scan_phases, sig_map, color="blue", lw=1.5, label="Signal Power")
    ax1.axvspan(-dur_phase * 3.0, dur_phase * 3.0, color="yellow", alpha=0.15, label="Zone A (transit)")
    ax1.axvspan(-0.5, -dur_phase * 3.0, color="lightgreen", alpha=0.08)
    ax1.axvspan(dur_phase * 3.0, 0.5, color="lightgreen", alpha=0.08, label="Zone B+C (clean)")
    ax1.axvline(0, color="black", ls="--", alpha=0.6, label="Primary")
    ax1.axvline(0.5, color="red", ls="--", alpha=0.4, label="Secondary")
    ax1.axvline(-0.166, color="orange", ls=":", alpha=0.6, label="L4")
    ax1.axvline(0.166, color="green", ls=":", alpha=0.6, label="L5")
    ax1.axhline(5.0, color="gray", ls=":", lw=0.8)
    ax1.axhline(3.0, color="lightgray", ls=":", lw=0.8)
    ax1.set_title(f"Phase Space Power Map: TIC {args.tic} S{args.sector} (P={args.period:.4f}d)")
    ax1.set_xlabel("Phase")
    ax1.set_ylabel("Sigma")
    ax1.grid(True, alpha=0.2)
    ax1.legend(fontsize=8, loc="upper right")
    ax1.set_xlim(-0.5, 0.5)

    # Alt panel: Zoom Zone B (clean off-primary)
    ax2.plot(scan_phases, sig_map, color="blue", lw=1.5)
    ax2.axvline(-0.166, color="orange", ls=":", lw=1.5, label="L4 (−0.167)")
    ax2.axvline(0.166, color="green", ls=":", lw=1.5, label="L5 (+0.167)")
    ax2.axvline(0.25, color="purple", ls=":", lw=1.0, label="Leading quad (0.25)")
    ax2.axvline(-0.25, color="brown", ls=":", lw=1.0, label="Trailing quad (−0.25)")
    ax2.axhline(5.0, color="red", ls="--", lw=0.8, label="5 sigma")
    ax2.axhline(3.0, color="gray", ls="--", lw=0.8, label="3 sigma")
    ax2.set_title("Zone B+C Zoom (Off-Primary Independent Signals)")
    ax2.set_xlabel("Phase")
    ax2.set_ylabel("Sigma")
    ax2.grid(True, alpha=0.2)
    ax2.legend(fontsize=8, loc="upper right")
    ax2.set_xlim(-0.5, 0.5)
    ax2.set_ylim(-3, max(sig_map.max() * 1.1, 8))

    plt.tight_layout()
    
    fig_path = outdir / f"TIC_{args.tic}_S{args.sector}_phase_map.png"
    plt.savefig(fig_path, dpi=150, bbox_inches="tight")
    plt.close()
    logger.info(f"Power Map çizildi: {fig_path}")

if __name__ == "__main__":
    main()
