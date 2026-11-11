#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b5_poc2_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== centroid-flux correlation POC =="

python - <<'PY'
import json
import lightkurve as lk
import numpy as np
import warnings
from pathlib import Path
warnings.filterwarnings("ignore")

S = Path("outputs/blind-holdout-v2-20261011_085204/shards")
fp_pool, planet_pool = [], []
for sp in sorted(S.glob("shard-*.json")):
    try:
        d = json.loads(sp.read_text())
    except Exception:
        continue
    for r in d.get("rows", []):
        tid = r.get("target_id")
        strat = str(r.get("stratum", ""))
        if not tid: continue
        if strat.startswith("false_positive") and len(fp_pool) < 5:
            fp_pool.append((tid, strat))
        elif strat.startswith("planet") and len(planet_pool) < 5:
            planet_pool.append((tid, strat))

print(f"FP: {[t[0] for t in fp_pool]}")
print(f"Planet: {[t[0] for t in planet_pool]}")
print()

def centroid_corr(tid):
    try:
        sr = lk.search_lightcurve(f"TIC {tid}", author="SPOC", exptime=120)
        if len(sr) == 0:
            return None, "no_data"
        lc = sr[0].download()
        if lc is None:
            return None, "dl_fail"
        c1 = np.asarray(lc["mom_centr1"], dtype=float)
        c2 = np.asarray(lc["mom_centr2"], dtype=float)
        f  = np.asarray(lc["flux"], dtype=float)
        q  = np.asarray(lc["quality"], dtype=float) if "quality" in lc.columns else np.zeros_like(f)
        mask = np.isfinite(c1) & np.isfinite(c2) & np.isfinite(f) & (q == 0)
        c1, c2, f = c1[mask], c2[mask], f[mask]
        if len(f) < 1000:
            return None, "few"
        # Detrend flux simple: subtract median
        f_d = f - np.median(f)
        c1_d = c1 - np.median(c1)
        c2_d = c2 - np.median(c2)
        # Pearson correlation
        r1 = float(np.corrcoef(c1_d, f_d)[0,1])
        r2 = float(np.corrcoef(c2_d, f_d)[0,1])
        # Also try Spearman (rank-based, robust)
        from scipy.stats import spearmanr
        s1 = float(spearmanr(c1_d, f_d).statistic)
        s2 = float(spearmanr(c2_d, f_d).statistic)
        # Combined metric: max |r| over both axes
        return {
            "pearson_1": r1, "pearson_2": r2,
            "spearman_1": s1, "spearman_2": s2,
            "max_spearman": max(abs(s1), abs(s2)),
            "n": int(len(f)),
        }, "ok"
    except Exception as e:
        return None, f"{type(e).__name__}:{str(e)[:50]}"

print("=== FALSE POSITIVES ===")
for tid, strat in fp_pool:
    res, msg = centroid_corr(tid)
    if res:
        print(f"  {tid:>12s} {strat:22s}  "
              f"pearson=({res['pearson_1']:+.4f},{res['pearson_2']:+.4f})  "
              f"spearman=({res['spearman_1']:+.4f},{res['spearman_2']:+.4f})  "
              f"max|sp|={res['max_spearman']:.4f}  N={res['n']}")
    else:
        print(f"  {tid:>12s}: FAILED ({msg})")

print()
print("=== PLANETS ===")
for tid, strat in planet_pool:
    res, msg = centroid_corr(tid)
    if res:
        print(f"  {tid:>12s} {strat:22s}  "
              f"pearson=({res['pearson_1']:+.4f},{res['pearson_2']:+.4f})  "
              f"spearman=({res['spearman_1']:+.4f},{res['spearman_2']:+.4f})  "
              f"max|sp|={res['max_spearman']:.4f}  N={res['n']}")
    else:
        print(f"  {tid:>12s}: FAILED ({msg})")

print()
print("== DONE ==")
PY
