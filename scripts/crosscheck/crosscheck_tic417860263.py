from __future__ import annotations

import json
from pathlib import Path

from astroquery.mast import Catalogs
from astroquery.simbad import Simbad
from astroquery.vizier import Vizier

TIC_ID = 417860263
SEARCH_RADIUS_ARCSEC = 30
NEARBY_RADIUS_ARCSEC = 10

OUT_DIR = Path("outputs_discovery/reports")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def safe_float(x):
    try:
        return float(x)
    except Exception:
        return None

def main():
    result = {
        "tic_id": TIC_ID,
        "tic_query_success": False,
        "tic_basic": {},
        "simbad_matches_within_30arcsec": [],
        "vizier_gaia_matches_within_10arcsec": [],
        "vizier_2mass_matches_within_10arcsec": [],
        "notes": [],
    }

    # 1) TIC catalog query
    tic = Catalogs.query_criteria(catalog="Tic", ID=TIC_ID)
    if len(tic) == 0:
        result["notes"].append("TIC query returned no rows.")
    else:
        row = tic[0]
        ra = safe_float(row["ra"])
        dec = safe_float(row["dec"])
        tmag = safe_float(row["Tmag"])
        teff = safe_float(row["Teff"])
        rad = safe_float(row["rad"])
        mass = safe_float(row["mass"])
        gaia = row["GAIA"] if "GAIA" in row.colnames else None

        result["tic_query_success"] = True
        result["tic_basic"] = {
            "ra_deg": ra,
            "dec_deg": dec,
            "Tmag": tmag,
            "Teff_K": teff,
            "Rstar_Rsun": rad,
            "Mstar_Msun": mass,
            "Gaia_ID": str(gaia) if gaia is not None else None,
        }

        # 2) SIMBAD cone search
        custom = Simbad()
        custom.add_votable_fields("otype")
        simbad_tbl = custom.query_region(
            f"{ra} {dec}",
            radius=f"{SEARCH_RADIUS_ARCSEC}s"
        )

        if simbad_tbl is not None:
            # DEBUG: sütun isimlerini gör
            print("SIMBAD columns:", simbad_tbl.colnames)
            for r in simbad_tbl:
                row_dict = {}
                for col in simbad_tbl.colnames:
                    try:
                        row_dict[col] = str(r[col])
                    except Exception:
                        row_dict[col] = None
                result["simbad_matches_within_30arcsec"].append(row_dict)

        # 3) VizieR Gaia DR3 nearby sources
        viz = Vizier(columns=["*"], row_limit=50)
        gaia_tables = viz.query_region(
            f"{ra} {dec}",
            radius=f"{NEARBY_RADIUS_ARCSEC}s",
            catalog="I/355/gaiadr3"
        )
        if gaia_tables:
            tbl = gaia_tables[0]
            for r in tbl:
                result["vizier_gaia_matches_within_10arcsec"].append({
                    "Source": str(r["Source"]) if "Source" in tbl.colnames else None,
                    "RA_ICRS": safe_float(r["RA_ICRS"]) if "RA_ICRS" in tbl.colnames else None,
                    "DE_ICRS": safe_float(r["DE_ICRS"]) if "DE_ICRS" in tbl.colnames else None,
                    "Gmag": safe_float(r["Gmag"]) if "Gmag" in tbl.colnames else None,
                    "Plx": safe_float(r["Plx"]) if "Plx" in tbl.colnames else None,
                    "pmRA": safe_float(r["pmRA"]) if "pmRA" in tbl.colnames else None,
                    "pmDE": safe_float(r["pmDE"]) if "pmDE" in tbl.colnames else None,
                })

        # 4) VizieR 2MASS nearby sources
        tmass_tables = viz.query_region(
            f"{ra} {dec}",
            radius=f"{NEARBY_RADIUS_ARCSEC}s",
            catalog="II/246/out"
        )
        if tmass_tables:
            tbl = tmass_tables[0]
            for r in tbl:
                result["vizier_2mass_matches_within_10arcsec"].append({
                    "_2MASS": str(r["_2MASS"]) if "_2MASS" in tbl.colnames else None,
                    "RAJ2000": safe_float(r["RAJ2000"]) if "RAJ2000" in tbl.colnames else None,
                    "DEJ2000": safe_float(r["DEJ2000"]) if "DEJ2000" in tbl.colnames else None,
                    "Jmag": safe_float(r["Jmag"]) if "Jmag" in tbl.colnames else None,
                    "Hmag": safe_float(r["Hmag"]) if "Hmag" in tbl.colnames else None,
                    "Kmag": safe_float(r["Kmag"]) if "Kmag" in tbl.colnames else None,
                })

    # save JSON
    json_path = OUT_DIR / "TIC_417860263_crosscheck.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # save Markdown summary
    md_path = OUT_DIR / "TIC_417860263_crosscheck.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# TIC {TIC_ID} Cross-check Report\n\n")
        f.write("## TIC Basic\n")
        if result["tic_query_success"]:
            for k, v in result["tic_basic"].items():
                f.write(f"- **{k}**: {v}\n")
        else:
            f.write("- TIC query failed\n")

        f.write("\n## SIMBAD matches within 30 arcsec\n")
        if result["simbad_matches_within_30arcsec"]:
            for row in result["simbad_matches_within_30arcsec"]:
                f.write(f"- {row}\n")
        else:
            f.write("- No SIMBAD matches returned\n")

        f.write("\n## Gaia DR3 matches within 10 arcsec\n")
        if result["vizier_gaia_matches_within_10arcsec"]:
            for row in result["vizier_gaia_matches_within_10arcsec"]:
                f.write(f"- {row}\n")
        else:
            f.write("- No Gaia matches returned\n")

        f.write("\n## 2MASS matches within 10 arcsec\n")
        if result["vizier_2mass_matches_within_10arcsec"]:
            for row in result["vizier_2mass_matches_within_10arcsec"]:
                f.write(f"- {row}\n")
        else:
            f.write("- No 2MASS matches returned\n")

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