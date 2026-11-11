#!/usr/bin/env python3
"""
Gaia DR3 crowding POC - full adversarial corpus.
Input : validation/adversarial_fp_v1.csv  (target_id,label)
Output: validation/gaia_crowding_full.csv

NOT: Bu POC, target_id'yi Gaia source_id olarak kabul eder.
Eger TIC ID kullaniyorsan, once TIC->Gaia crossmatch yap.
"""
from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

from astroquery.gaia import Gaia

TESS_PIXEL_ARCSEC = 21.0
SEARCH_RADIUS_ARCSEC = 60.0

INPUT = Path("validation/adversarial_fp_v1.csv")
OUTPUT = Path("validation/gaia_crowding_full.csv")


def query_crowding(tic_id: str) -> dict:
    src = int(tic_id)
    q = f"""
    SELECT source_id, ra, dec, phot_g_mean_mag,
           DISTANCE(
             POINT('ICRS', ra, dec),
             (SELECT ra FROM gaiadr3.gaia_source WHERE source_id = {src}),
             (SELECT dec FROM gaiadr3.gaia_source WHERE source_id = {src})
           ) * 3600.0 AS dist_arcsec
    FROM gaiadr3.gaia_source
    WHERE 1 = CONTAINS(
        POINT('ICRS', ra, dec),
        CIRCLE('ICRS',
            (SELECT ra FROM gaiadr3.gaia_source WHERE source_id = {src}),
            (SELECT dec FROM gaiadr3.gaia_source WHERE source_id = {src}),
            {SEARCH_RADIUS_ARCSEC / 3600.0})
    )
    """
    job = Gaia.launch_job_async(q)
    rows = job.get_results()

    target = next((r for r in rows if int(r["source_id"]) == src), None)
    if target is None:
        return {
            "N_60as": 0, "brightest_delta_mag": None,
            "dist_to_brightest_arcsec": None,
            "within_1px": 0, "within_1pixel": 0,
            "within_1arcsec": 0, "min_dist_arcsec": None,
            "G_mag_target": None, "G_mag_brightest": None,
        }

    g_target = target["phot_g_mean_mag"]
    neighbors = [r for r in rows if int(r["source_id"]) != src]

    if not neighbors:
        return {
            "N_60as": 0, "brightest_delta_mag": None,
            "dist_to_brightest_arcsec": None,
            "within_1px": 0, "within_1pixel": 0,
            "within_1arcsec": 0, "min_dist_arcsec": None,
            "G_mag_target": float(g_target) if g_target is not None else None,
            "G_mag_brightest": None,
        }

    brightest = min(neighbors, key=lambda r: r["phot_g_mean_mag"])
    delta_mag = float(brightest["phot_g_mean_mag"] - g_target) if g_target is not None else None

    dists = [float(r["dist_arcsec"]) for r in neighbors if r["dist_arcsec"] is not None]
    min_dist = min(dists) if dists else None

    within_1px = int(min_dist is not None and min_dist <= TESS_PIXEL_ARCSEC)
    within_1arcsec = int(min_dist is not None and min_dist <= 1.0)

    return {
        "N_60as": len(neighbors),
        "brightest_delta_mag": delta_mag,
        "dist_to_brightest_arcsec": float(brightest["dist_arcsec"]) if brightest["dist_arcsec"] is not None else None,
        "within_1px": within_1px,
        "within_1pixel": within_1px,
        "within_1arcsec": within_1arcsec,
        "min_dist_arcsec": min_dist,
        "G_mag_target": float(g_target) if g_target is not None else None,
        "G_mag_brightest": float(brightest["phot_g_mean_mag"]),
    }


def main() -> int:
    if not INPUT.exists():
        print(f"[FAIL] missing {INPUT}", file=sys.stderr)
        return 1

    with INPUT.open() as f:
        targets = list(csv.DictReader(f))

    print(f"[INFO] {len(targets)} targets", flush=True)

    fields = [
        "target_id", "label",
        "N_60as", "brightest_delta_mag", "dist_to_brightest_arcsec",
        "within_1px", "within_1pixel", "within_1arcsec", "min_dist_arcsec",
        "G_mag_target", "G_mag_brightest",
        "crowding_flag",
    ]

    with OUTPUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()

        for i, t in enumerate(targets, 1):
            tid = str(t["target_id"]).strip()
            label = t.get("label", "").strip()
            try:
                row = query_crowding(tid)
            except Exception as e:
                print(f"[WARN] {tid} failed: {e}", flush=True)
                row = {"N_60as": None, "brightest_delta_mag": None,
                       "dist_to_brightest_arcsec": None,
                       "within_1px": None, "within_1pixel": None,
                       "within_1arcsec": None, "min_dist_arcsec": None,
                       "G_mag_target": None, "G_mag_brightest": None}

            flag = 0
            if (row.get("N_60as") is not None and row["N_60as"] >= 30
                    and row.get("brightest_delta_mag") is not None
                    and row["brightest_delta_mag"] <= 3.0
                    and row.get("dist_to_brightest_arcsec") is not None
                    and row["dist_to_brightest_arcsec"] <= 20.0):
                flag = 1

            out = {"target_id": tid, "label": label, **row, "crowding_flag": flag}
            w.writerow(out)
            print(f"[{i}/{len(targets)}] {tid} ({label}) "
                  f"N={row.get('N_60as')} flag={flag}", flush=True)
            time.sleep(0.5)

    print(f"[DONE] {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
