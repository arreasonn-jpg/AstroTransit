from __future__ import annotations

import json
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
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:2000]}")
    return resp.json()


def run_safe(query_name: str, query: str, result: dict):
    try:
        result["queries"][query_name] = tap_query(query)
    except Exception as e:
        result["queries"][query_name] = {"error": str(e), "query": query}


def main():
    with open(CROSSCHECK_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    ra = data["tic_basic"]["ra_deg"]
    dec = data["tic_basic"]["dec_deg"]
    gaia_id = data["tic_basic"]["Gaia_ID"]
    simbad_name = None
    if data["simbad_matches_within_30arcsec"]:
        simbad_name = data["simbad_matches_within_30arcsec"][0].get("main_id")

    radius_arcsec = 30.0
    radius_deg = radius_arcsec / 3600.0

    result = {
        "target": {
            "tic_id": data["tic_id"],
            "ra_deg": ra,
            "dec_deg": dec,
            "gaia_id": gaia_id,
            "simbad_name": simbad_name,
        },
        "queries": {},
        "notes": [],
    }

    # 0) smoke test
    smoke_query = """
    select top 3 pl_name, hostname, ra, dec
    from pscomppars
    """
    run_safe("smoke_pscomppars", smoke_query, result)

    # 1) schema probe
    schema_query = """
    select top 200 column_name, datatype
    from TAP_SCHEMA.columns
    where table_name = 'pscomppars'
    order by column_name
    """
    run_safe("pscomppars_schema", schema_query, result)

    # 2) cone search, only safe/basic columns
    cone_query = f"""
    select top 50
        pl_name, hostname, disc_year, disc_facility, ra, dec, sy_vmag
    from pscomppars
    where CONTAINS(
        POINT('ICRS', ra, dec),
        CIRCLE('ICRS', {ra}, {dec}, {radius_deg})
    ) = 1
    """
    run_safe("pscomppars_cone_30arcsec", cone_query, result)

    # 3) exact hostname search
    if simbad_name:
        safe_name = simbad_name.replace("'", "''")
        host_query = f"""
        select top 50
            pl_name, hostname, disc_year, disc_facility, ra, dec, sy_vmag
        from pscomppars
        where hostname = '{safe_name}'
        """
        run_safe("pscomppars_exact_hostname", host_query, result)

    # 4) loose hostname search
    if simbad_name:
        alias_fragment = simbad_name.replace("HD ", "").replace("'", "''")
        like_query = f"""
        select top 50
            pl_name, hostname, disc_year, disc_facility, ra, dec, sy_vmag
        from pscomppars
        where hostname like '%{alias_fragment}%'
        """
        run_safe("pscomppars_loose_hostname", like_query, result)

    # save json
    json_path = OUT_DIR / "TIC_417860263_exoplanet_archive_check.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # save md
    md_path = OUT_DIR / "TIC_417860263_exoplanet_archive_check.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TIC 417860263 Exoplanet Archive Check\n\n")
        f.write("## Target\n")
        for k, v in result["target"].items():
            f.write(f"- **{k}**: {v}\n")

        f.write("\n## Query Results\n")
        for name, rows in result["queries"].items():
            f.write(f"\n### {name}\n")
            if isinstance(rows, dict) and "error" in rows:
                f.write(f"- ERROR: {rows['error']}\n")
                f.write("```sql\n")
                f.write(rows.get("query", "").strip())
                f.write("\n```\n")
            elif not rows:
                f.write("- No rows returned\n")
            else:
                for row in rows:
                    f.write(f"- {row}\n")

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