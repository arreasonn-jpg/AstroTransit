"""Expand the known-planet ground truth (Gate 2) from TFOP dispositions.

The release-acceptance gate "Known planets" requires >=50 labelled targets
with an expected/recovered table. ``benchmarks/verified_targets.json``
started with 9 hand-curated giants; this script expands it deterministically
from the TESS FOP Working Group dispositions in
``benchmarks/toi_catalog.csv`` — an independent label source, not an
AstroTransit output.

Selection (all deterministic, no RNG):

* disposition ``KP`` (known planet) or ``CP`` (confirmed planet);
* finite positive ``pl_rade`` and ``0.3 <= pl_orbper <= 30`` days
  (the cascade's BLS search range; long-period ground truth needs a
  separate, duration-aware benchmark);
* one entry per TIC: when a star hosts several TOIs, the shortest-period
  planet is kept (the one a single-sector cascade is most likely to recover);
* targets already present in the existing ground truth are skipped;
* stratified by operational difficulty derived from transit depth
  (``pl_trandep`` in ppm: >=2000 "easy", >=200 "medium", else "hard") via
  round-robin across tiers, so the benchmark set is not all easy giants;
* first 50 selected targets (tier order easy/medium/hard, numeric TIC
  order within a tier).

Limitations recorded in each entry's ``reference``: the disposition is the
label; ``available_sectors`` is left empty so the pipeline discovers sectors
from MAST at run time. This file is ground truth, never a performance
claim.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

MAX_NEW_TARGETS = 50
BLS_MIN_PERIOD_DAYS = 0.3
BLS_MAX_PERIOD_DAYS = 30.0
DIFFICULTY_RANK = {"easy": 0, "medium": 1, "hard": 2}
REFERENCE_TEMPLATE = (
    "TESS FOP Working Group disposition '{disp}' via NASA Exoplanet Archive "
    "TESS FOP WG catalog snapshot (benchmarks/toi_catalog.csv, accessed 2026-09-08); TOI {toi}"
)


def difficulty_for(depth_ppm: float) -> str:
    if depth_ppm >= 2000.0:
        return "easy"
    if depth_ppm >= 200.0:
        return "medium"
    return "hard"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=Path("benchmarks/toi_catalog.csv"))
    parser.add_argument(
        "--verified",
        type=Path,
        default=Path("benchmarks/verified_targets.json"),
        help="Ground-truth JSON (modified in place, keeps legacy entries)",
    )
    parser.add_argument("--max-new", type=int, default=MAX_NEW_TARGETS)
    args = parser.parse_args()

    existing = json.loads(args.verified.read_text(encoding="utf-8"))
    if isinstance(existing, dict):
        existing = existing["targets"]
    existing_tics = {str(row["tic_id"]) for row in existing}

    per_star: dict[str, dict[str, float]] = {}
    disp_of: dict[str, set[str]] = {}
    with args.input.open(newline="", encoding="utf-8-sig") as handle:
        for record in csv.DictReader(handle):
            disposition = (record.get("tfopwg_disp") or "").strip().upper()
            if disposition not in ("KP", "CP"):
                continue
            tid = (record.get("tid") or "").strip()
            if not tid or tid in existing_tics:
                continue
            try:
                period = float(record["pl_orbper"])
                radius = float(record["pl_rade"])
                depth = float(record.get("pl_trandep") or 0.0)
            except (KeyError, TypeError, ValueError):
                continue
            if not (BLS_MIN_PERIOD_DAYS <= period <= BLS_MAX_PERIOD_DAYS and radius > 0):
                continue
            toi = (record.get("toi") or "").strip()
            current = per_star.get(tid)
            if current is None or period < current["period"]:
                per_star[tid] = {"period": period, "radius": radius, "depth": depth, "toi": toi}
            disp_of.setdefault(tid, set()).add(disposition)

    candidates = []
    for tid, planet in per_star.items():
        candidates.append(
            (
                DIFFICULTY_RANK[difficulty_for(planet["depth"])],
                int(tid) if tid.isdigit() else 0,
                tid,
                planet,
                "/".join(sorted(disp_of[tid])),
            )
        )

    tiers: dict[int, list[tuple[int, str, dict[str, float], str]]] = defaultdict(list)
    for rank, tid_num, tid, planet, disp in candidates:
        tiers[rank].append((tid_num, tid, planet, disp))
    for rank in tiers:
        tiers[rank].sort(key=lambda item: item[0])

    # Round-robin across tiers (easy, medium, hard) for a balanced mix;
    # fall back to whatever tiers still have candidates.
    selected = []
    index = {rank: 0 for rank in (0, 1, 2)}
    while len(selected) < args.max_new:
        progressed = False
        for rank in (0, 1, 2):
            if len(selected) >= args.max_new:
                break
            if index[rank] < len(tiers[rank]):
                _, tid, planet, disp = tiers[rank][index[rank]]
                index[rank] += 1
                selected.append((rank, int(tid) if tid.isdigit() else 0, tid, planet, disp))
                progressed = True
        if not progressed:
            break

    new_rows = []
    for _, _, tid, planet, disp in selected:
        new_rows.append({
            "tic_id": tid,
            "name": planet["toi"],
            "sector": None,
            "period": round(planet["period"], 8),
            "rp_rearth": round(planet["radius"], 6),
            "difficulty": difficulty_for(planet["depth"]),
            "available_sectors": [],
            "reference": REFERENCE_TEMPLATE.format(disp=disp, toi=planet["toi"]),
        })

    merged = list(existing) + new_rows
    if len({row["tic_id"] for row in merged}) != len(merged):
        raise SystemExit("Duplicate tic_id after merge; refusing to write.")
    args.verified.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    from collections import Counter

    counts = Counter(row["difficulty"] for row in new_rows)
    print(f"Wrote {len(new_rows)} new targets to {args.verified} (total {len(merged)})")
    for difficulty in ("easy", "medium", "hard"):
        print(f"  new {difficulty}: {counts.get(difficulty, 0)}")
    print("Legacy entries preserved; new entries cite the TFOP disposition in 'reference'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
