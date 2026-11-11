#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b5_poc_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== centroid_shift POC v2 =="

python - <<'PY'
import json
import lightkurve as lk
import numpy as np
import warnings
from pathlib import Path
warnings.filterwarnings("ignore")

S = Path("outputs/blind-holdout-v2-20261011_085204/shards")
fp_pool = []
planet_pool = []
for sp in sorted(S.glob("shard-*.json")):
    try:
        d = json.loads(sp.read_text())
    except Exception:
        continue
    for r in d.get("rows", []):
        tid = r.get("target_id")
        strat = str(r.get("stratum", ""))
        if not tid: continue
        if strat.startswith("false_positive") and len(fp_pool) < 3:
            fp_pool.append((tid, strat))
        elif strat.startswith("planet") and len(planet_pool) < 3:
            planet_pool.append((tid, strat))

print(f"FP targets:      {fp_pool}")
print(f"Planet targets:  {planet_pool}")
print()

def compute_centroid_shift(tid: str):
    try:
        sr = lk.search_lightcurve(f"TIC {tid}", author="SPOC", exptime=120)
        if len(sr) == 0:
            return None, "no_spoc_120s"
        lc = sr[0].download()
        if lc is None:
            return None, "download_failed"
        if "mom_centr1" not in lc.columns or "mom_centr2" not in lc.columns:
            return None, "no_centroid_columns"
        c1 = np.asarray(lc["mom_centr1"], dtype=float)
        c2 = np.asarray(lc["mom_centr2"], dtype=float)
        f  = np.asarray(lc["flux"], dtype=float)
        mask = np.isfinite(c1) & np.isfinite(c2) & np.isfinite(f)
        c1, c2, f = c1[mask], c2[mask], f[mask]
        if len(f) < 1000:
            return None, f"too_few_points:{len(f)}"
        c1_med = np.median(c1)
        c2_med = np.median(c2)
        # 5% deepest points as transit
        threshold = np.percentile(f, 5)
        in_tr = f < threshold
        if in_tr.sum() < 20:
            return None, "no_dip"
        dc1 = float(c1[in_tr].mean() - c1_med)
        dc2 = float(c2[in_tr].mean() - c2_med)
        shift_pixels = float(np.hypot(dc1, dc2))
        # TESS pixel ~21 arcsec
        return {
            "target_id": tid,
            "dc1": dc1, "dc2": dc2,
            "shift_px": shift_pixels,
            "shift_arcsec": shift_pixels * 21.0,
            "n": int(len(f)),
        }, "ok"
    except Exception as e:
        return None, f"{type(e).__name__}:{str(e)[:60]}"

print("=== FALSE POSITIVES ===")
for tid, strat in fp_pool:
    res, msg = compute_centroid_shift(tid)
    if res:
        print(f"  {tid} ({strat})")
        print(f"    shift: {res['shift_px']:.4f} px  ({res['shift_arcsec']:.3f} arcsec)")
        print(f"    dc1={res['dc1']:+.4f}  dc2={res['dc2']:+.4f}  N={res['n']}")
    else:
        print(f"  {tid}: FAILED ({msg})")

print()
print("=== PLANETS ===")
for tid, strat in planet_pool:
    res, msg = compute_centroid_shift(tid)
    if res:
        print(f"  {tid} ({strat})")
        print(f"    shift: {res['shift_px']:.4f} px  ({res['shift_arcsec']:.3f} arcsec)")
        print(f"    dc1={res['dc1']:+.4f}  dc2={res['dc2']:+.4f}  N={res['n']}")
    else:
        print(f"  {tid}: FAILED ({msg})")

print()
print("=== POC DONE ===")
PY
