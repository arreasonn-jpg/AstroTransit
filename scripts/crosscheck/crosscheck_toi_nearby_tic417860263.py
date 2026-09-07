from __future__ import annotations

import json
import math
from pathlib import Path
import requests

CROSSCHECK_JSON = Path("outputs_discovery/reports/TIC_417860263_crosscheck.json")
OUT_DIR = Path("outputs_discovery/reports")
OUT_DIR.mkdir(parents=True, exist_ok=True)

TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"


def tap_query(query: str):
    resp = requests.get(
        TAP_URL,
        params={"query": query, "format": "json"},
        timeout=60,
    )
    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:3000]}")
    return resp.json()


def angsep_arcsec(ra1_deg, dec1_deg, ra2_deg, dec2_deg):
    ra1 = math.radians(ra1_deg)
    dec1 = math.radians(dec1_deg)
    ra2 = math.radians(ra2_deg)
    dec2 = math.radians(dec2_deg)

    cosd = (
        math.sin(dec1) * math.sin(dec2)
        + math.cos(dec1) * math.cos(dec2) * math.cos(ra1 - ra2)
    )
    cosd = max(-1.0, min(1.0, cosd))
    return math.degrees(math.acos(cosd)) * 3600.0


def main():
    with open(CROSSCHECK_JSON, "r", encoding="utf-8") as f:
        cross = json.load(f)

    tic_id = cross["tic_id"]
    ra = cross["tic_basic"]["ra_deg"]
    dec = cross["tic_basic"]["dec_deg"]

    radius_arcsec = 30.0
    radius_deg = radius_arcsec / 3600.0

    # small rectangular prefilter
    dec_min = dec - radius_deg
    dec_max = dec + radius_deg

    # RA wrap-safe handling near 0 deg
    ra_min = ra - radius_deg
    ra_max = ra + radius_deg

    if ra_min < 0:
        ra_clause = f"(ra >= {360 + ra_min} or ra <= {ra_max})"
    elif ra_max >= 360:
        ra_clause = f"(ra >= {ra_min} or ra <= {ra_max - 360})"
    else:
        ra_clause = f"(ra between {ra_min} and {ra_max})"

    query = f"""
    select top 200
        toi, toipfx, tid, tfopwg_disp, ra, dec, pl_pnum,
        pl_orbper, pl_rade, pl_trandep, pl_trandurh, pl_tranmid,
        st_tmag, st_teff, st_rad, sectors, ctoi_alias
    from toi
    where {ra_clause}
      and dec between {dec_min} and {dec_max}
    """

    result = {
        "target": {
            "tic_id": tic_id,
            "ra_deg": ra,
            "dec_deg": dec,
            "search_radius_arcsec": radius_arcsec,
        },
        "raw_rows": [],
        "matches_within_30arcsec": [],
        "notes": [],
    }

    try:
        rows = tap_query(query)
        result["raw_rows"] = rows
        for row in rows:
            try:
                sep = angsep_arcsec(ra, dec, float(row["ra"]), float(row["dec"]))
            except Exception:
                continue
            row2 = dict(row)
            row2["sep_arcsec"] = sep
            if sep <= radius_arcsec:
                result["matches_within_30arcsec"].append(row2)
    except Exception as e:
        result["notes"].append(str(e))
        result["notes"].append(query)

    json_path = OUT_DIR / "TIC_417860263_toi_nearby_check.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    md_path = OUT_DIR / "TIC_417860263_toi_nearby_check.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TIC 417860263 Nearby TOI Check\n\n")

        f.write("## Target\n")
        for k, v in result["target"].items():
            f.write(f"- **{k}**: {v}\n")

        f.write("\n## Matches within 30 arcsec\n")
        if result["matches_within_30arcsec"]:
            for row in result["matches_within_30arcsec"]:
                f.write(f"- {row}\n")
        else:
            f.write("- No rows returned within 30 arcsec after client-side filtering\n")

        f.write("\n## Notes\n")
        if result["notes"]:
            for note in result["notes"]:
                f.write(f"- {note}\n")
        else:
            f.write("- None\n")

    print(f"Saved: {json_path}")
    print(f"Saved: {md_path}")


if __name__ == "__main__":
    main()