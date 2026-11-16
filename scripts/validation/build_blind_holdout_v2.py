#!/usr/bin/env python3
"""Build the FAZ 2b blind domain holdout v2 corpus.

v1 measured recall 0.264 < 0.5 floor with 9 data errors and 27 missing rows.
v2 is a *fresh* frozen corpus from the same blind_test partition, disjoint from
v1 and from every prior gate, with a new selection seed. The 9 v1 data errors
(sector fetch failures) are addressed at run time by the retry/fallback logic
in run_blind_holdout.py, not by corpus surgery.

Red line: no blind data is consulted for selection or tuning. Selection is
sha256-seeded rank only; labels come from the frozen TFoP disposition corpus.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from astrotransit.validation.blind_holdout import (  # noqa: E402
    LABELLED_CORPUS,
    MINIMUM_CASES_PER_STRATUM,
    SPLIT_SEED,
    load_exclusion_ids,
    normalize_target_id,
    select_holdout,
)

V1_MANIFEST = ROOT / "validation_runs/final_acceptance_v1/blind_holdout/holdout_manifest.json"
DEFAULT_OUTPUT = ROOT / "validation_runs/final_acceptance_v1/blind_holdout_v2/holdout_manifest_v2.json"

#: New selection seed — different from v1 (20260918) so v2 picks fresh targets.
V2_SELECTION_SEED = 20261120
#: Same split seed as v1 so both corpora live in the same blind_test partition.
V2_SPLIT_SEED = SPLIT_SEED
#: Per-label quota; gate requires >=60/>=60, we keep 72/72 for margin.
V2_PER_LABEL = 72


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--per-label", type=int, default=V2_PER_LABEL)
    parser.add_argument("--selection-seed", type=int, default=V2_SELECTION_SEED)
    parser.add_argument("--split-seed", type=int, default=V2_SPLIT_SEED)
    parser.add_argument("--minimum-per-stratum", type=int, default=MINIMUM_CASES_PER_STRATUM)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--freeze-sectors",
        action="store_true",
        help="query MAST once per target and write the available sector list into each case",
    )
    parser.add_argument(
        "--max-sectors",
        type=int,
        default=6,
        help="cap on frozen sectors per target (default 6; keeps multi-sector aggregation meaningful)",
    )
    args = parser.parse_args()

    corpus = json.loads((ROOT / LABELLED_CORPUS).read_text(encoding="utf-8"))
    cases = corpus["cases"]

    # Exclude: v1 holdout IDs + all prior-gate IDs (same policy as v1).
    v1 = json.loads(V1_MANIFEST.read_text(encoding="utf-8"))
    v1_ids = {normalize_target_id(c["target_id"]) for c in v1["cases"]}
    prior_sources = {
        "fp_run_subset": ROOT / "benchmarks/corpora/fp_run_subset_v1.json",
        "prior_injection_quiet_hosts": ROOT / "validation_runs/v1_injection_recovery/real_noise_v1/input/quiet_hosts.json",
    }
    per_source, combined = load_exclusion_ids(prior_sources)
    excluded: set[str] = set(v1_ids) | combined
    # Also exclude any target that already has measured rows from prior gates.
    for pattern in (
        "validation_runs/final_acceptance_v1/**/rows.jsonl",
        "validation_runs/final_acceptance_v1/**/shard-*.json",
        "validation_runs/v1_injection_recovery/**/rows.jsonl",
    ):
        for path in sorted(ROOT.glob(pattern)):
            try:
                if path.suffix == ".jsonl":
                    for line in path.read_text(encoding="utf-8").splitlines():
                        if line.strip():
                            excluded.add(normalize_target_id(json.loads(line).get("target_id", "")))
                else:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    for row in payload.get("rows", []) or []:
                        excluded.add(normalize_target_id(row.get("target_id", "")))
            except Exception:
                continue
    excluded.discard("")

    print(f"loaded labelled corpus: {len(cases)} cases")
    print(f"excluded IDs (v1 holdout + prior gates): {len(excluded)}")

    result: dict[str, Any] = select_holdout(
        cases,
        excluded_ids=excluded,
        per_label=args.per_label,
        seed=args.selection_seed,
        split_seed=args.split_seed,
        split="blind_test",
        minimum_per_stratum=args.minimum_per_stratum,
    )
    result["campaign"] = "blind_domain_holdout_v2"
    result["materialization"] = "deterministic_rebuild_from_frozen_sources_v2"
    result["claim_boundary"] = (
        "v2 blind holdout: fresh sha256-seeded selection from the blind_test partition, "
        "disjoint from v1 and all prior gates. Labels are external TFoP WG dispositions. "
        "Nothing was tuned on this corpus; the single blind run happens after all "
        "algorithm changes are frozen and validated on development corpora."
    )
    result["exclusions"] = {
        "sources": {
            "v1_holdout": sorted(v1_ids),
            **{name: ids for name, ids in sorted(per_source.items())},
        },
        "n_excluded_ids": len(excluded),
        "policy": (
            "v1 holdout IDs and every id touched by a prior gate are removed before "
            "ranking, so v2 cannot inherit a selection advantage from earlier measurements"
        ),
    }
    result["sources"] = {
        "labelled_corpus": LABELLED_CORPUS,
        "v1_manifest": str(V1_MANIFEST.relative_to(ROOT)),
    }

    # Sanity: disjoint from v1.
    v2_ids = {normalize_target_id(c["target_id"]) for c in result["cases"]}
    overlap = v2_ids & v1_ids
    assert not overlap, f"v2/v1 overlap: {overlap}"

    # FAZ 2b.7: freeze sector availability into the manifest so the blind run
    # never depends on a live MAST lookup (v1 lost 9 rows to sector fetch
    # failures). Sector *availability* is archive metadata, not detector
    # output — freezing it keeps the run detector-blind.
    if args.freeze_sectors:
        from astrotransit.data.tess_client import TESSClient

        client = TESSClient()
        frozen = 0
        for case in result["cases"]:
            tid = normalize_target_id(case["target_id"])
            try:
                sectors = client.get_available_sectors(tid)
            except Exception as exc:
                print(f"  sector lookup failed for {tid}: {exc}")
                sectors = []
            case["sectors"] = sorted(sectors)[: args.max_sectors]
            if case["sectors"]:
                frozen += 1
        print(f"froze sectors for {frozen}/{len(result['cases'])} targets")
        # Re-freeze the hash AFTER sector lists are embedded.
        from astrotransit.validation.blind_holdout import holdout_sha256

        result["holdout_sha256"] = holdout_sha256(result["cases"])

    if args.dry_run:
        keys = ("counts", "stratum_counts", "pool_sizes", "holdout_sha256", "rejection_counts")
        print(json.dumps({key: result[key] for key in keys}, indent=2, sort_keys=True))
        print(f"overlap with v1: {len(overlap)}")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print()
    print(f"wrote {args.output}")
    print(f"  n_cases:        {result['counts']}")
    print(f"  stratum_counts: {json.dumps(result['stratum_counts'], sort_keys=True)}")
    print(f"  holdout_sha256: {result['holdout_sha256']}")
    print(f"  overlap with v1: {len(overlap)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
