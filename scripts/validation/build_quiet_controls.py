#!/usr/bin/env python3
"""Build a deterministic, detector-independent quiet-control corpus."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tic_number(value: Any) -> str:
    return str(value).upper().replace("TIC", "").strip()


def load_ids(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        rows = payload.get("cases", payload.get("hosts", []))
    else:
        rows = payload
    return {
        tic_number(row.get("target_id", row.get("tic_id", "")))
        for row in rows
        if isinstance(row, dict)
    }


def finite_positive(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def candidate_rows(
    pool: Path,
    excluded_labels: set[str],
    excluded_hosts: set[str],
    *,
    seed: int,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    accepted: list[dict[str, Any]] = []
    rejected: Counter[str] = Counter()
    seen: set[str] = set()
    with pool.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {
            "tid",
            "sector_count",
            "sector_list",
            "st_tmag",
            "st_teff",
            "st_rad",
        }
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"Candidate pool missing columns: {sorted(required)}")
        for pool_index, row in enumerate(reader):
            tic = tic_number(row["tid"])
            sectors = [
                int(item)
                for item in str(row["sector_list"]).split(",")
                if item.strip()
            ]
            reason = None
            if not tic or tic in seen:
                reason = "empty_or_duplicate_tic"
            elif tic in excluded_labels:
                reason = "labelled_toi_or_tfop_history"
            elif tic in excluded_hosts:
                reason = "prior_injection_host"
            elif int(row["sector_count"]) < 2 or len(sectors) < 2:
                reason = "fewer_than_two_catalog_sectors"
            elif not all(
                finite_positive(row[key]) for key in ("st_tmag", "st_teff", "st_rad")
            ):
                reason = "nonfinite_stellar_metadata"
            if reason:
                rejected[reason] += 1
                continue
            seen.add(tic)
            rank = hashlib.sha256(f"{seed}:{tic}".encode()).hexdigest()
            accepted.append(
                {
                    "pool_index": pool_index,
                    "tic_id": tic,
                    "target_id": f"TIC {tic}",
                    "sectors": [sectors[0], sectors[-1]],
                    "catalog_sector_count": int(row["sector_count"]),
                    "tmag": float(row["st_tmag"]),
                    "teff_k": float(row["st_teff"]),
                    "radius_rsun": float(row["st_rad"]),
                    "selection_rank": rank,
                }
            )
    accepted.sort(key=lambda item: (item["selection_rank"], item["tic_id"]))
    return accepted, rejected


def build(
    pool: Path,
    labelled_corpus: Path,
    prior_hosts: Path,
    *,
    required: int,
    seed: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    labelled_ids = load_ids(labelled_corpus)
    prior_host_ids = load_ids(prior_hosts)
    eligible, rejected = candidate_rows(
        pool,
        labelled_ids,
        prior_host_ids,
        seed=seed,
    )
    selected = eligible[:required]
    pool_hash = sha256(pool)
    cases = [
        {
            "target_id": row["target_id"],
            "label": "quiet_star",
            "reference": f"catalog_negative_control_v1:{pool_hash}:{row['tic_id']}",
            "sectors": row["sectors"],
            "notes": (
                "Operational catalog-negative control; absence of TOI/TFOP history is not "
                "proof of no planet. AstroTransit output was not used for selection."
            ),
        }
        for row in selected
    ]
    status = "frozen" if len(cases) == required else "insufficient_candidates"
    payload = {
        "schema_version": "1.0",
        "corpus": "independent_quiet_controls_v1",
        "status": status,
        "label_definition": "operational_catalog_negative_control",
        "required_count": required,
        "selected_count": len(cases),
        "selection": {
            "method": "sha256_seeded_rank_after_catalog_only_exclusions_v1",
            "seed": seed,
            "detector_used_for_selection": False,
            "prior_injection_hosts_excluded": True,
        },
        "sources": {
            "pool": {"path": str(pool), "sha256": pool_hash},
            "labelled_corpus": {
                "path": str(labelled_corpus),
                "sha256": sha256(labelled_corpus),
            },
            "prior_injection_hosts": {
                "path": str(prior_hosts),
                "sha256": sha256(prior_hosts),
            },
        },
        "cases": cases,
        "claim_boundary": (
            "These are detector-independent catalog-negative controls from one frozen target "
            "pool, not proof of planet absence and not a population-representative FPR sample."
        ),
    }
    audit = {
        "schema_version": "1.0",
        "status": status,
        "eligible_count": len(eligible),
        "selected_count": len(cases),
        "required_count": required,
        "rejection_counts": dict(sorted(rejected.items())),
        "selected": selected,
    }
    return payload, audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--labelled-corpus", type=Path, required=True)
    parser.add_argument("--prior-hosts", type=Path, required=True)
    parser.add_argument("--required", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260912)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    if args.required < 100:
        raise SystemExit("required must be at least 100")
    payload, audit = build(
        args.pool,
        args.labelled_corpus,
        args.prior_hosts,
        required=args.required,
        seed=args.seed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    args.audit.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(
        f"Selected {payload['selected_count']}/{payload['required_count']} "
        f"detector-independent controls"
    )
    return 0 if payload["status"] == "frozen" else 2


if __name__ == "__main__":
    raise SystemExit(main())
