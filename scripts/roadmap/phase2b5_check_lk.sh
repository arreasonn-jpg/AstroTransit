#!/usr/bin/env bash
# Verify lightkurve returns centroid columns for TESS SPOC data.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b5_check_lk_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== lightkurve centroid check =="

python - <<'PY'
import lightkurve as lk
import warnings
warnings.filterwarnings("ignore")

# TIC 25155310 — already in cache
print("Searching TIC 25155310 sector 69...")
sr = lk.search_lightcurve("TIC 25155310", sector=69, author="SPOC",
                          exptime=120)
print(f"  results: {len(sr)}")
if len(sr) == 0:
    print("  NO RESULTS — try alternate target")
    sr = lk.search_lightcurve("TIC 25155310", author="SPOC", exptime=120)
    print(f"  broad search: {len(sr)}")
if len(sr) == 0:
    raise SystemExit(1)

lc = sr[0].download()
print(f"  LightCurve type: {type(lc).__name__}")
print(f"  columns: {list(lc.columns)}")
print(f"  meta keys: {list(lc.meta.keys())[:30]}")

# Check for centroid columns
for col in ("mom_centr1", "mom_centr2", "centroid_col", "centroid_row",
            "pos_corr1", "pos_corr2"):
    if col in lc.columns:
        import numpy as np
        vals = np.asarray(lc[col])
        print(f"  {col}: present, shape={vals.shape}, "
              f"median={np.nanmedian(vals):.4f}, "
              f"std={np.nanstd(vals):.6f}")
    else:
        print(f"  {col}: MISSING")

# to_pandas columns
df = lc.to_pandas()
print(f"  pandas columns: {list(df.columns)}")
PY

echo
echo "== DONE =="
