#!/usr/bin/env python3
"""Build the FAZ 2b development corpus.

The blind holdout (Blind v1) measured recall 0.704 and FPR 0.719 on 144
real TESS targets. To iterate on the algorithm without contaminating the
blind set, we build a *parallel* corpus from the development partition
of the same frozen split.

Same selection method (sha256 seeded rank), same strata, same quotas,
different selection seed and different split. The 144 blind holdout IDs
are explicitly excluded so the two corpora are disjoint.
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
    normalize_target_id,
    select_holdout,
)

BLIND_MANIFEST = ROOT / "validation_runs/final_acceptance_v1/blind_holdout/holdout_manifest.json"
DEFAULT_OUTPUT = ROOT / "validation_runs/final_acceptance_v1/dev_holdout/dev_manifest.json"

#: Different selection seed from the blind corpus (which used 20260918).
DEV_SELECTION_SEED = 20260919
#: Same split seed as the blind corpus so the two partitions are disjoint.
DEV_SPLIT_SEED = 13
#: Target per-label quota (matches the blind corpus: 72 + 72).
DEV_PER_LABEL = 72
#: Which partition of the frozen split to draw from.
DEV_SPLIT = "development"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--per-label",
        type=int,
        default=DEV_PER_LABEL,
    )
    parser.add_argument(
        "--selection-seed",
        type=int,
        default=DEV_SELECTION_SEED,
    )
    parser.add_argument(
        "--split",
        type=str,
        default=DEV_SPLIT,
        choices=["development", "validation"],
    )
    args = parser.parse_args()

    blind = json.loads(BLIND_MANIFEST.read_text(encoding="utf-8"))
    blind_ids = {normalize_target_id(c["target_id"]) for c in blind["cases"]}
    excluded: set[str] = set(blind_ids)
    for source_ids in blind["exclusions"]["sources"].values():
        excluded.update(normalize_target_id(x) for x in source_ids)

    corpus = json.loads((ROOT / LABELLED_CORPUS).read_text(encoding="utf-8"))
    cases = corpus["cases"]

    print(f"loaded labelled corpus: {len(cases)} cases")
    print(f"excluded IDs (blind + prior gates): {len(excluded)}")

    result: dict[str, Any] = select_holdout(
        cases,
        excluded_ids=excluded,
        per_label=args.per_label,
        seed=args.selection_seed,
        split_seed=DEV_SPLIT_SEED,
        split=args.split,
        minimum_per_stratum=MINIMUM_CASES_PER_STRATUM,
    )

    result["materialization"] = f"{args.split}_partition_for_algorithm_development"
    result["claim_boundary"] = (
        "Development corpus for algorithm iteration. Same selection method "
        "as the blind holdout (sha256 seeded rank, detector-blind), drawn "
        "from a disjoint partition of the same frozen split. Not a "
        "validation gate; results here guide revision before a second "
        "blind run."
    )
    result["sources"] = {
        "labelled_corpus": LABELLED_CORPUS,
        "blind_manifest": str(BLIND_MANIFEST.relative_to(ROOT)),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print()
    print(f"wrote {args.output}")
    print(f"  n_cases:       {result['counts']}")
    print(f"  stratum_counts: {json.dumps(result['stratum_counts'], indent=2)}")
    print(f"  holdout_sha256: {result['holdout_sha256']}")

    # Sanity: check disjointness
    dev_ids = {normalize_target_id(c["target_id"]) for c in result["cases"]}
    overlap = dev_ids & blind_ids
    print(f"  overlap with blind: {len(overlap)}")
    assert not overlap, f"blind/dev overlap: {overlap}"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
