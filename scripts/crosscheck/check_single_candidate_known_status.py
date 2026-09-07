from pathlib import Path
import sys
import re
import argparse

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))


def normalize_tic(v):
    if v is None:
        return None
    digits = re.sub(r"\D", "", str(v))
    return int(digits) if digits else None


def parse_args():
    parser = argparse.ArgumentParser(
        description="Check whether a TIC is already present in TOI / verified sets / Exoplanet Archive."
    )
    parser.add_argument(
        "--tic",
        default="417860263",
        help="TIC ID to check, e.g. 352146741 or 'TIC 352146741'"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    target = normalize_tic(args.tic)

    if target is None:
        print(f"Gecersiz TIC girdisi: {args.tic}")
        return 1

    import pandas as pd

    print("=" * 72)
    print(f"  Candidate Known-Status Check: TIC {target}")
    print("=" * 72)

    # TOI check
    toi_file = project_root / "benchmarks" / "toi_catalog.csv"
    in_toi = False
    if toi_file.exists():
        toi = pd.read_csv(toi_file)
        toi_ids = set(normalize_tic(v) for v in toi["tid"].tolist())
        in_toi = target in toi_ids
    print(f"TOI katalogunda var mi? {in_toi}")

    # Verified targets
    verified_file = project_root / "benchmarks" / "verified_targets.json"
    in_verified = False
    if verified_file.exists():
        import json
        verified = json.load(open(verified_file, encoding="utf-8"))
        for item in verified:
            if normalize_tic(item.get("tic_id")) == target:
                in_verified = True
                break
    print(f"Golden/verified test setinde var mi? {in_verified}")

    # Exoplanet archive exact TIC check
    archive_match = False
    try:
        from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchive
        tbl = NasaExoplanetArchive.query_criteria(
            table="pscomppars",
            select="pl_name,tic_id,disc_facility",
            where=f"tic_id like '%{target}%'"
        )
        if len(tbl) > 0:
            archive_match = True
            print(f"Exoplanet Archive'da TIC benzeri eslesme var: {len(tbl)}")
            print(tbl)
        else:
            print("Exoplanet Archive'da TIC eslesmesi yok")
    except Exception as e:
        print(f"Exoplanet Archive sorgusu basarisiz: {e}")

    if in_toi or in_verified or archive_match:
        status = "KNOWN_MATCH_FOUND"
    else:
        status = "NO_KNOWN_MATCH_FOUND"

    print(f"STATUS: {status}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
