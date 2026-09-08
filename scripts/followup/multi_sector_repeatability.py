#!/usr/bin/env python3
"""
Multi-Sector Signal Repeatability Test

Fikir: Aynı hedefin farklı TESS sektörlerindeki verilerini
ayrı ayrı indirip, aynı periyot/epoch ile katlayarak (fold)
L4/L5 veya omuz sinyallerinin sektörler arası ne kadar 
tutarlı olduğunu ölçer.

Gerçek bir mimari yapı (trojan, vs) farklı sektörlerde
aynı fazda görünmelidir.
"""

from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
from loguru import logger
from scipy.interpolate import UnivariateSpline
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    import lightkurve as lk
except ImportError:
    raise ImportError("pip install lightkurve")


def download_all_sectors(tic_id: int):
    """Hedefin tüm SPOC kısa-kadans verilerini indirir."""
    logger.info(f"TIC {tic_id} için tüm SPOC sektörleri aranıyor...")
    search = lk.search_lightcurve(f"TIC {tic_id}", author="SPOC", exptime=120)
    
    if len(search) == 0:
        return {}

    lcs_by_sector = {}
    
    # Sektörleri benzersiz yap ve en iyi/ilk veriyi al
    for s in search:
        sector_num = s.mission[0].split(" ")[-1]
        try:
            sector_num = int(sector_num)
        except ValueError:
            continue
            
        if sector_num not in lcs_by_sector:
            try:
                lc = s.download()
                time = np.array(lc.time.value, dtype=float)
                flux = np.array(getattr(lc.flux, "value", lc.flux), dtype=float)
                qual = np.array(getattr(lc.quality, "value", lc.quality), dtype=int)
                
                v = np.isfinite(time) & np.isfinite(flux) & (qual == 0)
                time, flux = time[v], flux[v]
                flux /= np.nanmedian(flux)
                
                # Detrend
                try:
                    sp = UnivariateSpline(time, flux, k=3, s=len(time)*0.8)
                    flux /= sp(time)
                except Exception:
                    pass
                
                lcs_by_sector[sector_num] = (time, flux)
                logger.info(f"Sektör {sector_num} indirildi ve temizlendi. ({len(time)} nokta)")
            except Exception as e:
                logger.warning(f"Sektör {sector_num} indirilemedi: {e}")

    return lcs_by_sector


def fold(time, period, t0):
    return ((time - t0 + 0.5 * period) % period) / period - 0.5


def scan_phases(phase, flux, dur_phase, steps=500):
    centers = np.linspace(-0.5, 0.5, steps)
    sig_map = np.zeros(steps)
    depth_map = np.zeros(steps)
    
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
        
        depth_map[i] = depth * 1e6
        sig_map[i] = depth / sigma * np.sqrt(len(in_f))
        
    return centers, sig_map


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tic", type=int, required=True)
    parser.add_argument("--period", type=float, required=True)
    parser.add_argument("--t0", type=float, required=True)
    parser.add_argument("--duration-hours", type=float, required=True)
    parser.add_argument("--output-dir", type=str, default="outputs_architecture_review")
    args = parser.parse_args()

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    
    if args.period < 2.0:
        logger.error(f"Periyot çok kısa ({args.period:.2f} d). Co-orbital analizi geçersiz.")
        return

    logger.info(f"Multi-Sector Repeatability: TIC {args.tic}")
    
    lcs = download_all_sectors(args.tic)
    if len(lcs) < 2:
        logger.warning(f"TIC {args.tic} için yeterli sektör yok (Sadece {len(lcs)} sektör). Multi-sector testi yapılamaz.")
        return

    dur_phase = (args.duration_hours / 24.0) / args.period
    
    # Tüm sektörleri birleştirip "Full LC" oluştur
    all_time = np.concatenate([t for t, f in lcs.values()])
    all_flux = np.concatenate([f for t, f in lcs.values()])
    
    all_phase = fold(all_time, args.period, args.t0)
    centers, sig_full = scan_phases(all_phase, all_flux, dur_phase)

    # Her sektör için ayrı ayrı tara
    sector_sigs = {}
    for sec_num, (t, f) in sorted(lcs.items()):
        p = fold(t, args.period, args.t0)
        _, s_map = scan_phases(p, f, dur_phase)
        sector_sigs[sec_num] = s_map

    print("\n" + "="*80)
    print(f"MULTI-SECTOR REPEATABILITY: TIC {args.tic}")
    print("="*80)
    
    sectors_list = sorted(lcs.keys())
    header = f"{'Phase':>8} {'Full':>8}"
    for s in sectors_list:
        header += f" {'S'+str(s):>8}"
    print(header)
    print("-" * 80)

    # İlgilendiğimiz hedef fazlar
    target_phases = [-0.1667, 0.1667, 0.25, -0.25, 0.5]
    labels = ["L4", "L5", "Leading Quad", "Trailing Quad", "Secondary"]

    for t_phase, label in zip(target_phases, labels):
        # Scan dizisinde bu faza en yakın indeksi bul
        idx = np.argmin(np.abs(centers - t_phase))
        
        full_val = sig_full[idx]
        row_str = f"{t_phase:>+8.4f} {full_val:>8.1f}"
        
        sec_vals = []
        for s in sectors_list:
            v = sector_sigs[s][idx]
            sec_vals.append(v)
            row_str += f" {v:>8.1f}"
            
        # Karar: Bir sinyal tüm sektörlerde 2 sigma'dan büyük mü?
        consistent = all(v >= 2.0 for v in sec_vals) and full_val >= 3.0
        if consistent:
            row_str += f"  → REPEATABLE ★ ({label})"
        else:
            row_str += f"  → Noise/Alias ({label})"
            
        print(row_str)

    print("="*80 + "\n")

    # Çizim
    fig, axes = plt.subplots(len(lcs) + 1, 1, figsize=(14, 4 * (len(lcs) + 1)), sharex=True)
    
    # Full
    axes[0].plot(centers, sig_full, color="blue", label="All Sectors Combined")
    axes[0].set_title(f"TIC {args.tic} - All Sectors")
    axes[0].axhline(3.0, color="gray", ls="--", alpha=0.5)
    
    # Sektörler
    for i, sec_num in enumerate(sectors_list):
        ax = axes[i+1]
        ax.plot(centers, sector_sigs[sec_num], color="green", label=f"Sector {sec_num}")
        ax.set_title(f"Sector {sec_num}")
        ax.axhline(3.0, color="gray", ls="--", alpha=0.5)

    for ax in axes:
        ax.axvline(0, color="black", ls="--", alpha=0.5)
        ax.axvline(-0.166, color="orange", ls=":", alpha=0.5, label="L4")
        ax.axvline(0.166, color="orange", ls=":", alpha=0.5, label="L5")
        ax.set_ylabel("Sigma")
        ax.legend(loc="upper right")

    axes[-1].set_xlabel("Phase")
    plt.tight_layout()
    
    fig_path = outdir / f"TIC_{args.tic}_multisector_repeat.png"
    plt.savefig(fig_path, dpi=150)
    plt.close()
    logger.info(f"Figür yazıldı: {fig_path}")

if __name__ == "__main__":
    main()
