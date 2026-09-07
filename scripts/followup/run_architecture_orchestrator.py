#!/usr/bin/env python3
"""
Architecture Follow-up Orchestrator

Amaç: Aday havuzundaki (CSV/Parquet) her hedef için uçtan uca
mimari anomali analizi yapmak ve EB/Co-orbital ayrımını otomatik
olarak skorlamak.
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd
import numpy as np
from loguru import logger
import lightkurve as lk
from scipy.interpolate import UnivariateSpline
from tqdm import tqdm

from astrotransit.quality.eb_coorbital_discriminator import EBCooorbitalDiscriminator, DiscriminatorInput

def download_and_flatten(tic_id, sector):
    try:
        search = lk.search_lightcurve(f"TIC {tic_id}", sector=sector, author="SPOC", exptime=120)
        if len(search) == 0:
            return None, None
        lc = search[0].download()
        time = np.array(lc.time.value, dtype=float)
        flux = np.array(lc.flux.value, dtype=float)
        qual = np.array(lc.quality.value, dtype=int)
        v = np.isfinite(time) & np.isfinite(flux) & (qual == 0)
        time, flux = time[v], flux[v]
        flux /= np.nanmedian(flux)
        
        sp = UnivariateSpline(time, flux, k=3, s=len(time)*0.8)
        return time, flux / sp(time)
    except Exception as e:
        logger.warning(f"LC Error TIC {tic_id}: {e}")
        return None, None

def scan_phase(phase, flux, dur_phase, target_phase, half_width):
    shifted = ((phase - target_phase + 0.5) % 1.0) - 0.5
    in_w = np.abs(shifted) < half_width
    if in_w.sum() < 5:
        return 0.0, 0.0
    in_f = flux[in_w]
    out_f = flux[~in_w]
    if len(out_f) < 10:
        return 0.0, 0.0
    baseline = np.nanmedian(out_f)
    std = max(np.nanstd(out_f), 1e-9)
    depth_ppm = (baseline - np.nanmedian(in_f)) * 1e6
    sig = (depth_ppm / 1e6) / std * np.sqrt(len(in_f))
    return depth_ppm, sig

def test_repeatability(time, phase, flux, dur_phase, target_phase):
    t_mid = np.nanmedian(time)
    m1 = time <= t_mid
    m2 = time > t_mid
    
    _, s1 = scan_phase(phase[m1], flux[m1], dur_phase, target_phase, max(dur_phase*1.5, 0.01))
    _, s2 = scan_phase(phase[m2], flux[m2], dur_phase, target_phase, max(dur_phase*1.5, 0.01))
    
    if s1 >= 2.0 and s2 >= 2.0: return "REPEATABLE ★"
    if s1 >= 2.0 and s2 < 2.0: return "FIRST HALF ONLY"
    if s2 >= 2.0 and s1 < 2.0: return "SECOND HALF ONLY"
    return "NOT REPEATABLE"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, required=True, help="Input CSV/Parquet of candidates")
    parser.add_argument("--output-dir", type=str, default="outputs_architecture_orchestrator")
    parser.add_argument("--limit", type=int, default=10, help="Max candidates to process")
    args = parser.parse_args()

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    
    df = pd.read_parquet(args.input) if args.input.endswith(".parquet") else pd.read_csv(args.input)
    
    # Sadece period_mismatch olanları veya yüksek skoru olanları al
    if "architecture_interest_score" in df.columns:
        df = df.sort_values("architecture_interest_score", ascending=False)
    
    targets = df.head(args.limit)
    logger.info(f"{len(targets)} aday için Orchestrator başlatılıyor...")
    
    results = []
    disc = EBCooorbitalDiscriminator()

    for _, row in tqdm(targets.iterrows(), total=len(targets)):
        tic = int(row["tic_id"]) if "tic_id" in row else int(str(row["source_id"]).split()[-1])
        sector = int(row["sector"])
        period = float(row["period"])
        t0 = float(row["t0"])
        dur_hrs = float(row.get("duration_hours", 2.0))
        odd_even = float(row.get("tls_odd_even_mismatch", 0.0))
        
        if period <= 0: continue
        
        time, flux = download_and_flatten(tic, sector)
        if time is None: continue
        
        phase = ((time - t0 + 0.5 * period) % period) / period - 0.5
        dur_phase = (dur_hrs / 24.0) / period
        w = max(dur_phase * 1.5, 0.01)
        
        p_dep, p_sig = scan_phase(phase, flux, dur_phase, 0.0, dur_phase)
        s_dep, s_sig = scan_phase(phase, flux, dur_phase, 0.5, dur_phase)
        l4_dep, l4_sig = scan_phase(phase, flux, dur_phase, -0.1667, w)
        l5_dep, l5_sig = scan_phase(phase, flux, dur_phase, 0.1667, w)
        
        l4_rep = test_repeatability(time, phase, flux, dur_phase, -0.1667)
        l5_rep = test_repeatability(time, phase, flux, dur_phase, 0.1667)
        
        # Kısa periyotlu sistemlerde (P < 3 gün) co-orbital analiz
        # güvenilmez. dur_phase'i yapay olarak 0.09 yap (short mode tetiklesin)
        effective_dur_phase = dur_phase if period >= 3.0 else 0.09

        inp = DiscriminatorInput(
            target_id=f"TIC {tic}", sector=sector,
            primary_depth_ppm=p_dep, primary_sig=p_sig,
            secondary_depth_ppm=s_dep, secondary_sig=s_sig,
            l4_depth_ppm=l4_dep, l4_sig=l4_sig,
            l5_depth_ppm=l5_dep, l5_sig=l5_sig,
            odd_even_mismatch=odd_even,
            l4_repeatability=l4_rep,
            l5_repeatability=l5_rep,
            dur_phase=effective_dur_phase,
        )
        
        res = disc.discriminate(inp)
        
        out = {
            "TIC": tic, "Sector": sector, "Period": round(period,3),
            "Primary_Sig": round(p_sig,1), "Secondary_Sig": round(s_sig,1),
            "L4_Sig": round(l4_sig,1), "L5_Sig": round(l5_sig,1),
            "Odd_Even": round(odd_even,1),
            "EB_Score": res.eb_score, "Co_Score": res.coorbital_score,
            "Verdict": res.verdict, "Confidence": res.confidence
        }
        results.append(out)

    res_df = pd.DataFrame(results)
    res_df = res_df.sort_values("Co_Score", ascending=False)
    
    csv_out = outdir / "orchestrator_results.csv"
    res_df.to_csv(csv_out, index=False)
    
    print("\n" + "="*80)
    print("ARCHITECTURE ORCHESTRATOR SUMMARY")
    print("="*80)
    print(res_df.to_string(index=False))
    print("="*80)
    print(f"Detailed CSV: {csv_out}")

if __name__ == "__main__":
    main()
