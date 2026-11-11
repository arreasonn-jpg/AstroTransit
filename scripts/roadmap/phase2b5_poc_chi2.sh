#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b5_chi2_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== per-transit chi2 POC =="

python - <<'PY'
import json
import numpy as np
from pathlib import Path
from scipy.stats import chi2 as chi2_dist

# ---------- Load cache with hash index ----------
CACHE = Path(".cache/astrotransit/tess")
cache_by_tid = {}
for f in CACHE.glob("*.npz"):
    try:
        d = np.load(f)
        meta = json.loads(str(d["meta_json"]))
        tid = str(meta.get("target_id", "")).replace("TIC ", "").strip()
        if tid:
            cache_by_tid.setdefault(tid, []).append(f)
    except Exception:
        continue
print(f"cache targets: {len(cache_by_tid)}")

# ---------- Load candidate params from instrumented blind v2 shards ----------
PARAMS = {}
S = Path("outputs/blind-holdout-v2-20261011_085204/shards")
for sp in sorted(S.glob("shard-*.json")):
    try:
        d = json.loads(sp.read_text())
    except Exception:
        continue
    for r in d.get("rows", []):
        tid = str(r.get("target_id", "")).strip()
        strat = str(r.get("stratum", ""))
        for sec in (r.get("per_sector") or []):
            p = sec.get("candidate_period_days")
            dur = sec.get("candidate_duration_days")
            if tid and p and dur:
                PARAMS.setdefault(tid, {"period": p, "duration": dur,
                                        "stratum": strat})

print(f"params known: {len(PARAMS)}")

# ---------- Per-transit chi2 ----------
def per_transit_chi2(time, flux, period, duration):
    if period <= 0 or duration <= 0 or len(time) < 200:
        return None
    # Fold at period, coarse phase binning to find dip
    phase = ((time - time.min()) % period) / period
    nbins = 100
    bin_edges = np.linspace(0, 1, nbins+1)
    bin_idx = np.clip(np.digitize(phase, bin_edges) - 1, 0, nbins-1)
    bin_med = np.full(nbins, np.nan)
    for k in range(nbins):
        m = bin_idx == k
        if m.sum() >= 3:
            bin_med[k] = np.median(flux[m])
    if np.all(np.isnan(bin_med)):
        return None
    dip_bin = int(np.nanargmin(bin_med))
    dip_phase = 0.5 * (bin_edges[dip_bin] + bin_edges[dip_bin+1])
    t0 = time.min() + dip_phase * period

    # Transit centers
    t_first = t0
    while t_first - period > time.min():
        t_first -= period
    centers = []
    t = t_first
    while t < time.max():
        if t > time.min() + duration:
            centers.append(t)
        t += period
    if len(centers) < 3:
        return None

    depths = []
    for c in centers:
        in_mask = np.abs(time - c) < duration / 2
        out_mask = (np.abs(time - c) > duration) & (np.abs(time - c) < 2 * period)
        if in_mask.sum() < 3 or out_mask.sum() < 10:
            continue
        base = float(np.median(flux[out_mask]))
        depth = base - float(np.mean(flux[in_mask]))
        sigma = float(np.std(flux[out_mask]))
        if sigma <= 0:
            continue
        sigma_d = sigma / np.sqrt(in_mask.sum())
        depths.append((depth, sigma_d))

    if len(depths) < 3:
        return None

    D = np.array([d for d, _ in depths])
    E = np.array([e for _, e in depths])
    if (E <= 0).any():
        return None
    w = 1.0 / (E ** 2)
    d_mean = float(np.sum(D * w) / np.sum(w))
    chi2 = float(np.sum((D - d_mean) ** 2 / (E ** 2)))
    dof = len(D) - 1
    pval = float(1 - chi2_dist.cdf(chi2, dof))
    return {
        "n_transits": len(D),
        "period_days": period,
        "duration_hours": duration * 24,
        "d_mean_ppm": d_mean * 1e6,
        "chi2": chi2,
        "dof": dof,
        "chi2_per_dof": chi2 / dof,
        "p_value": pval,
        "depths_ppm": (D * 1e6).tolist(),
    }

# ---------- Pick 5 FP + 5 planet from params ----------
fp_pool = [t for t, p in PARAMS.items() if p["stratum"].startswith("false_positive")][:5]
planet_pool = [t for t, p in PARAMS.items() if p["stratum"].startswith("planet")][:5]

def show(pool, name):
    print(f"\n=== {name} ===")
    for tid in pool:
        params = PARAMS[tid]
        if tid not in cache_by_tid:
            print(f"  {tid}: no cache"); continue
        f = cache_by_tid[tid][0]
        d = np.load(f)
        t, fx = d["time"], d["flux"]
        res = per_transit_chi2(t, fx, params["period"], params["duration"])
        if res is None:
            print(f"  {tid:>12s} {params['stratum']:22s}  insufficient")
            continue
        print(f"  {tid:>12s} {params['stratum']:22s}  "
              f"N={res['n_transits']:2d}  "
              f"chi2/dof={res['chi2_per_dof']:8.2f}  "
              f"p={res['p_value']:.4f}  "
              f"d_mean={res['d_mean_ppm']:8.0f} ppm")

show(fp_pool, "FALSE POSITIVES")
show(planet_pool, "PLANETS")

print("\n== DONE ==")
PY
