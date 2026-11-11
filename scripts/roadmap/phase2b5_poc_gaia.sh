#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b5_gaia_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== Gaia DR3 crowding POC =="

python - <<'PY'
import json
import time
import numpy as np
from pathlib import Path
from astroquery.mast import Catalogs
from astroquery.gaia import Gaia
import warnings
warnings.filterwarnings("ignore")
Gaia.ROW_LIMIT = 500

# Pick 5 FP + 5 planet from blind v2
S = Path("outputs/blind-holdout-v2-20261011_085204/shards")
fp_pool, planet_pool = [], []
for sp in sorted(S.glob("shard-*.json")):
    try:
        d = json.loads(sp.read_text())
    except Exception:
        continue
    for r in d.get("rows", []):
        tid = str(r.get("target_id", "")).strip()
        strat = str(r.get("stratum", ""))
        if not tid: continue
        if strat.startswith("false_positive") and len(fp_pool) < 5:
            fp_pool.append((tid, strat))
        elif strat.startswith("planet") and len(planet_pool) < 5:
            planet_pool.append((tid, strat))

print(f"FP: {[t[0] for t in fp_pool]}")
print(f"Planet: {[t[0] for t in planet_pool]}")
print()

def get_tic_coords(tid):
    try:
        result = Catalogs.query_criteria(catalog="Tic", ID=tid)
        if len(result) == 0:
            return None
        row = result[0]
        return float(row["ra"]), float(row["dec"]), float(row.get("Tmag") or 0)
    except Exception as e:
        return None

def gaia_query(ra, dec, radius_arcsec):
    try:
        r_deg = radius_arcsec / 3600.0
        q = f"""
        SELECT source_id, ra, dec, phot_g_mean_mag, parallax, ruwe
        FROM gaiadr3.gaia_source
        WHERE 1=CONTAINS(POINT('ICRS', ra, dec),
                         CIRCLE('ICRS', {ra}, {dec}, {r_deg}))
        """
        job = Gaia.launch_job(q)
        t = job.get_results()
        return t
    except Exception as e:
        return None

def analyze(tid, stratum):
    coords = get_tic_coords(tid)
    if coords is None:
        return None, "tic_lookup_failed"
    ra, dec, tmag = coords
    t = gaia_query(ra, dec, 60.0)  # 60 arcsec = ~3 TESS pixels
    if t is None:
        return None, "gaia_query_failed"
    if len(t) == 0:
        return {"tid": tid, "stratum": stratum, "n": 0,
                "delta_mag": None, "tmag": tmag,
                "crowding_flag": False}, "ok"
    # Compute distances and find brightest neighbor (excluding target itself)
    ras = np.asarray(t["ra"], dtype=float)
    decs = np.asarray(t["dec"], dtype=float)
    gmag = np.asarray(t["phot_g_mean_mag"], dtype=float)
    # Simple angular distance
    cos_dec = np.cos(np.radians(dec))
    dra = (ras - ra) * cos_dec
    ddec = decs - dec
    dist_arcsec = np.hypot(dra, ddec) * 3600.0
    # Exclude target itself (dist < 2 arcsec)
    mask = dist_arcsec > 2.0
    n_neighbors = int(mask.sum())
    if n_neighbors == 0:
        return {"tid": tid, "stratum": stratum, "n": 0,
                "delta_mag": None, "tmag": tmag,
                "crowding_flag": False}, "ok"
    # Find brightest neighbor within 60 arcsec
    gmag_filt = gmag[mask]
    dist_filt = dist_arcsec[mask]
    brightest_idx = int(np.argmin(gmag_filt))
    brightest_g = float(gmag_filt[brightest_idx])
    brightest_dist = float(dist_filt[brightest_idx])
    # Convert Tmag to approximate Gmag (rough: Tmag ~ Gmag)
    delta_mag = brightest_g - tmag  # negative if neighbor is brighter
    # Crowding flag: bright neighbor within 21 arcsec (1 pixel)
    bright_within_1px = ((gmag_filt - tmag < 2.0) & (dist_filt < 21.0)).sum()
    return {
        "tid": tid, "stratum": stratum,
        "n_neighbors_60as": n_neighbors,
        "brightest_delta_mag": delta_mag,
        "brightest_dist_arcsec": brightest_dist,
        "bright_within_1px": int(bright_within_1px),
        "tmag": tmag,
    }, "ok"

def show(pool, name):
    print(f"\n=== {name} ===")
    for tid, strat in pool:
        res, msg = analyze(tid, strat)
        time.sleep(1)  # be polite to Gaia
        if res is None:
            print(f"  {tid:>12s} {strat:22s}  FAILED ({msg})")
            continue
        if res["n_neighbors_60as"] == 0:
            print(f"  {tid:>12s} {strat:22s}  "
                  f"no Gaia neighbors within 60\"")
        else:
            print(f"  {tid:>12s} {strat:22s}  "
                  f"N_60as={res['n_neighbors_60as']:3d}  "
                  f"brightest Δmag={res['brightest_delta_mag']:+.2f}  "
                  f"dist={res['brightest_dist_arcsec']:5.1f}\"  "
                  f"within_1px={res['bright_within_1px']}")

show(fp_pool, "FALSE POSITIVES")
show(planet_pool, "PLANETS")
print("\n== DONE ==")
PY
