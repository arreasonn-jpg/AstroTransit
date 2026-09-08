"""Build a reproducible known-planet benchmark corpus from NASA Exoplanet Archive.

This script never labels TOIs or candidates as planets. It only selects records
from the archive's confirmed-planet table and writes the source query and
retrieval date alongside each row.

Example:
    python scripts/validation/build_known_planet_corpus.py --limit 100 \
        --output benchmarks/verified_targets_nasa_v1.json
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TAP_ENDPOINT = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
QUERY = """select top {limit} tic_id,pl_name,pl_orbper,pl_rade,disc_refname
from pscomppars
where default_flag=1 and pl_controv_flag=0
  and tic_id is not null and pl_orbper is not null and pl_rade is not null
order by pl_orbper asc"""


def fetch_rows(limit: int) -> list[dict[str, str]]:
    if limit < 1:
        raise ValueError("limit en az 1 olmalıdır")
    query = QUERY.format(limit=int(limit))
    params = urlencode({"query": query, "format": "json"})
    request = Request(f"{TAP_ENDPOINT}?{params}", headers={"User-Agent": "AstroTransit/validation"})
    with urlopen(request, timeout=60) as response:  # noqa: S310 - fixed HTTPS endpoint
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError("NASA Archive beklenmeyen JSON döndürdü")
    return payload


def normalize(rows: list[dict[str, str]], retrieved_at: str) -> list[dict[str, object]]:
    output = []
    seen: set[str] = set()
    for row in rows:
        tic = str(row.get("tic_id") or "").strip()
        try:
            period = float(row["pl_orbper"])
            radius = float(row["pl_rade"])
        except (KeyError, TypeError, ValueError):
            continue
        if not tic or tic in seen or period <= 0 or radius <= 0:
            continue
        seen.add(tic)
        difficulty = "easy" if period < 10 and radius > 4 else "medium" if period < 30 else "hard"
        output.append({
            "tic_id": tic,
            "name": str(row.get("pl_name") or "unknown"),
            "period": period,
            "rp_rearth": radius,
            "difficulty": difficulty,
            "available_sectors": [],
            "reference": str(row.get("disc_refname") or "NASA Exoplanet Archive pscomppars"),
            "provenance": {"source": "NASA Exoplanet Archive", "retrieved_at_utc": retrieved_at},
        })
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    rows = normalize(fetch_rows(args.limit), retrieved_at)
    if not rows:
        raise SystemExit("No confirmed planet rows returned; no output written.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} confirmed targets to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
