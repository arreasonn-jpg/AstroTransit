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
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:3000]}")
    return resp.json()


def run_safe(name: str, query: str, out: dict):
    try:
        out["queries"][name] = tap_query(query)
    except Exception as e:
        out["queries"][name] = {"error": str(e), "query": query}


def choose_first(cols: set[str], candidates: list[str]) -> str | None:
    for c in candidates:
        if c in cols:
            return c
    return None


def main():
    with open(CROSSCHECK_JSON, "r", encoding="utf-8") as f:
        cross = json.load(f)

    tic_id = cross["tic_id"]
    ra = cross["tic_basic"]["ra_deg"]
    dec = cross["tic_basic"]["dec_deg"]

    result = {
        "target": {
            "tic_id": tic_id,
            "ra_deg": ra,
            "dec_deg": dec,
        },
        "queries": {},
        "notes": [],
    }

    # 1) TOI schema
    schema_query = """
    select top 300 column_name, datatype
    from TAP_SCHEMA.columns
    where table_name = 'toi'
    order by column_name
    """
    run_safe("toi_schema", schema_query, result)

    schema_rows = result["queries"].get("toi_schema", [])
    if isinstance(schema_rows, dict) and "error" in schema_rows:
        # save and exit gracefully
        result["notes"].append("Could not read TOI schema; downstream queries skipped.")
    else:
        cols = {row["column_name"] for row in schema_rows if "column_name" in row}

        # likely column names
        tic_col = choose_first(cols, ["tid", "tic_id", "tic", "TIC_ID"])
        ra_col = choose_first(cols, ["ra", "radeg", "ra_deg"])
        dec_col = choose_first(cols, ["dec", "decdeg", "dec_deg"])

        # prefer a readable subset of columns if present
        preferred = [
            "toi",
            "toipfx",
            "tid",
            "tic_id",
            "tfopwg_disp",
            "disp",
            "ra",
            "dec",
            "pl_pnum",
            "planet_radius",
            "period",
            "epoch",
            "duration",
            "depth",
            "comments",
        ]
        select_cols = [c for c in preferred if c in cols]

        # fallback if almost none exist
        if not select_cols:
            select_cols = sorted(list(cols))[:12]

        select_sql = ", ".join(select_cols)

        # 2) smoke test
        smoke_query = f"""
        select top 5 {select_sql}
        from toi
        """
        run_safe("toi_smoke", smoke_query, result)

        # 3) exact TIC match
        if tic_col is not None:
            tic_query = f"""
            select top 50 {select_sql}
            from toi
            where {tic_col} = {tic_id}
            """
            run_safe("toi_exact_tic_match", tic_query, result)
        else:
            result["notes"].append("No TIC-like column found in TOI schema.")

        # 4) cone search if ra/dec exist
        if ra_col is not None and dec_col is not None:
            radius_arcsec = 30.0
            radius_deg = radius_arcsec / 3600.0
            cone_query = f"""
            select top 50 {select_sql}
            from toi
            where CONTAINS(
                POINT('ICRS', {ra_col}, {dec_col}),
                CIRCLE('ICRS', {ra}, {dec}, {radius_deg})
            ) = 1
            """
            run_safe("toi_cone_30arcsec", cone_query, result)
        else:
            result["notes"].append("No RA/DEC columns found in TOI schema.")

    # save json
    json_path = OUT_DIR / "TIC_417860263_toi_check.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # save md
    md_path = OUT_DIR / "TIC_417860263_toi_check.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TIC 417860263 TOI Check\n\n")

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