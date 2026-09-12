#!/usr/bin/env python3
"""Run and aggregate the frozen false-positive and quiet-control campaign.

This is a detection-level evaluation. A cascade-confirmed candidate is an
"accepted candidate"; it is not an astrophysical classification or a formal
Bayesian false-positive probability.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from astrotransit.validation.benchmark_report import normalize_target_id
from astrotransit.validation.corpus import CorpusCase, load_corpus
from scripts.validation.build_quiet_controls import build as build_quiet_controls

QUIET_CORPUS_SHA256 = "a59e245487fc80e440fb9481734cf1f95e8778433de2b2ab9abe58f258974aea"
QUIET_SEED = 20260912
REQUIRED_PER_LABEL = 100


def canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def _subset_ids(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("targets", payload.get("cases", [])) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("false-positive subset must contain a targets list")
    return [
        normalize_target_id(
            row.get("target_id", row.get("tic_id", row)) if isinstance(row, dict) else row
        )
        for row in rows
    ]


def materialize_cases(
    labelled_corpus: Path,
    fp_subset: Path,
    quiet_pool: Path,
    prior_hosts: Path,
) -> tuple[list[CorpusCase], dict[str, Any]]:
    labelled = {
        normalize_target_id(case.target_id): case for case in load_corpus(labelled_corpus)
    }
    fp_cases: list[CorpusCase] = []
    seen: set[str] = set()
    for target_id in _subset_ids(fp_subset):
        case = labelled.get(target_id)
        if case is None or case.label != "false_positive" or target_id in seen:
            continue
        fp_cases.append(case)
        seen.add(target_id)
    if len(fp_cases) != REQUIRED_PER_LABEL:
        raise ValueError(
            f"expected exactly 100 labelled false positives, found {len(fp_cases)}"
        )

    quiet_payload, quiet_audit = build_quiet_controls(
        quiet_pool,
        labelled_corpus,
        prior_hosts,
        required=REQUIRED_PER_LABEL,
        seed=QUIET_SEED,
    )
    quiet_hash = hashlib.sha256(canonical_json(quiet_payload)).hexdigest()
    if quiet_hash != QUIET_CORPUS_SHA256:
        raise ValueError(f"quiet-control corpus hash changed: {quiet_hash}")
    quiet_cases = [
        CorpusCase(
            target_id=str(row["target_id"]),
            label=str(row["label"]),
            reference=str(row["reference"]),
            sectors=tuple(int(value) for value in row.get("sectors", [])),
            notes=str(row.get("notes", "")),
        )
        for row in quiet_payload["cases"]
    ]
    if len(quiet_cases) != REQUIRED_PER_LABEL:
        raise ValueError(
            f"expected exactly 100 quiet controls, found {len(quiet_cases)}"
        )
    all_ids = [
        normalize_target_id(case.target_id) for case in [*fp_cases, *quiet_cases]
    ]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("campaign contains duplicate target IDs")
    metadata = {
        "false_positive_count": len(fp_cases),
        "quiet_control_count": len(quiet_cases),
        "quiet_control_sha256": quiet_hash,
        "quiet_detector_used_for_selection": False,
        "quiet_eligible_count": int(quiet_audit["eligible_count"]),
    }
    return [*fp_cases, *quiet_cases], metadata


def _quality_value(sector_result: Any, name: str) -> Any:
    quality = getattr(sector_result, "quality", None)
    score = getattr(quality, "score", None)
    if name == "score":
        value = getattr(score, "total_score", None)
        return None if value is None else float(value)
    candidate_class = getattr(score, "candidate_class", None)
    return getattr(candidate_class, "value", None)


def _evaluate_case(
    case: CorpusCase,
    orchestrator: Any,
    sector_client: Any,
) -> dict[str, Any]:
    requested = list(case.sectors)
    sector_source = "frozen_corpus"
    availability_error = ""
    if not requested:
        sector_source = "lowest_available_spoc_120s_at_run"
        try:
            available = sector_client.get_available_sectors(case.target_id)
            requested = available[:1]
        except Exception as exc:
            availability_error = f"{type(exc).__name__}: {exc}"
    if not requested:
        return {
            "target_id": normalize_target_id(case.target_id),
            "label": case.label,
            "reference": case.reference,
            "requested_sectors": [],
            "sector_source": sector_source,
            "processed_sectors": [],
            "successful_sector_count": 0,
            "evaluated": False,
            "accepted_candidate": None,
            "candidate_count": None,
            "error": availability_error or "no_available_spoc_120s_sector",
            "sector_results": [],
        }
    try:
        result = orchestrator.run_single(case.target_id, sectors=requested)
        sectors = []
        for item in result.sector_results:
            sectors.append(
                {
                    "sector": int(item.sector),
                    "success": bool(item.success),
                    "has_candidate": bool(item.has_candidate),
                    "candidate_confirmed": bool(item.candidate_confirmed),
                    "quality_score": _quality_value(item, "score"),
                    "quality_class": _quality_value(item, "class"),
                    "error": str(item.error or ""),
                }
            )
        successful = sum(bool(row["success"]) for row in sectors)
        evaluated = bool(result.success and successful > 0)
        error_parts = [str(result.error)] if result.error else []
        error_parts.extend(row["error"] for row in sectors if row["error"])
        return {
            "target_id": normalize_target_id(case.target_id),
            "label": case.label,
            "reference": case.reference,
            "requested_sectors": requested,
            "sector_source": sector_source,
            "processed_sectors": [row["sector"] for row in sectors],
            "successful_sector_count": successful,
            "evaluated": evaluated,
            "accepted_candidate": (
                bool(result.candidates_confirmed > 0) if evaluated else None
            ),
            "candidate_count": int(result.candidates_confirmed) if evaluated else None,
            "error": "; ".join(error_parts),
            "sector_results": sectors,
        }
    except Exception as exc:
        return {
            "target_id": normalize_target_id(case.target_id),
            "label": case.label,
            "reference": case.reference,
            "requested_sectors": requested,
            "sector_source": sector_source,
            "processed_sectors": [],
            "successful_sector_count": 0,
            "evaluated": False,
            "accepted_candidate": None,
            "candidate_count": None,
            "error": f"{type(exc).__name__}: {exc}",
            "sector_results": [],
        }


def run_shard(args: argparse.Namespace) -> int:
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        raise ValueError("invalid shard index/count")
    cases, metadata = materialize_cases(
        args.labelled_corpus,
        args.fp_subset,
        args.quiet_pool,
        args.prior_hosts,
    )
    selected = [
        case
        for index, case in enumerate(cases)
        if index % args.shard_count == args.shard_index
    ]

    from astrotransit.data.tess_client import TESSClient
    from astrotransit.pipelines.orchestrator import AstroTransitOrchestrator

    sector_client = TESSClient()
    with AstroTransitOrchestrator(
        config_path=str(args.config),
        force_map=True,
        skip_visualization=True,
        log_level="INFO",
    ) as orchestrator:
        rows = [_evaluate_case(case, orchestrator, sector_client) for case in selected]
    payload = {
        "schema_version": "1.0",
        "campaign": "labelled_fp_quiet_controls_v1",
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "case_count": len(rows),
        "metadata": metadata,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(payload))
    print(f"Wrote shard {args.shard_index}: {len(rows)} cases to {args.output}")
    return 0


def _group_metrics(rows: list[dict[str, Any]], label: str) -> dict[str, Any]:
    labelled = [row for row in rows if row["label"] == label]
    evaluated = [row for row in labelled if row["evaluated"]]
    accepted = sum(row["accepted_candidate"] is True for row in evaluated)
    rejected = sum(row["accepted_candidate"] is False for row in evaluated)
    return {
        "labelled_count": len(labelled),
        "evaluated_count": len(evaluated),
        "unevaluated_count": len(labelled) - len(evaluated),
        "accepted_candidate_count": accepted,
        "rejected_count": rejected,
        "candidate_acceptance_rate": accepted / len(evaluated) if evaluated else None,
        "rejection_rate": rejected / len(evaluated) if evaluated else None,
    }


def aggregate_shards(
    shards: Path,
    shard_count: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payloads = []
    for index in range(shard_count):
        path = shards / f"shard-{index:02d}.json"
        if not path.exists():
            raise FileNotFoundError(f"missing shard: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload["shard_index"] != index or payload["shard_count"] != shard_count:
            raise ValueError(f"invalid shard contract: {path}")
        payloads.append(payload)
    rows = [row for payload in payloads for row in payload["rows"]]
    rows.sort(
        key=lambda row: (
            0 if row["label"] == "false_positive" else 1,
            row["target_id"],
        )
    )
    ids = [row["target_id"] for row in rows]
    if len(rows) != 200 or len(ids) != len(set(ids)):
        raise ValueError(
            f"expected 200 unique rows, found {len(rows)} rows/{len(set(ids))} IDs"
        )
    counts = Counter(row["label"] for row in rows)
    if counts != Counter({"false_positive": 100, "quiet_star": 100}):
        raise ValueError(f"unexpected label counts: {dict(counts)}")
    metadata = payloads[0]["metadata"]
    if any(payload["metadata"] != metadata for payload in payloads):
        raise ValueError("shards disagree on frozen corpus metadata")

    fp = _group_metrics(rows, "false_positive")
    quiet = _group_metrics(rows, "quiet_star")
    total_errors = sum(bool(row["error"]) or not row["evaluated"] for row in rows)
    acceptance_ready = (
        fp["evaluated_count"] >= 100
        and quiet["evaluated_count"] >= 100
        and total_errors == 0
    )
    report = {
        "schema_version": "1.0",
        "campaign": "labelled_fp_quiet_controls_v1",
        "status": "measured",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "corpora": {
            "false_positives": {
                "labelled_count": fp["labelled_count"],
                "source": "benchmarks/corpora/tfop_disposition_corpus_v1.json",
                "subset": "benchmarks/corpora/fp_run_subset_v1.json",
            },
            "quiet_controls": {
                "labelled_count": quiet["labelled_count"],
                "sha256": metadata["quiet_control_sha256"],
                "detector_used_for_selection": metadata[
                    "quiet_detector_used_for_selection"
                ],
            },
        },
        "evaluation": {
            "false_positives": fp,
            "quiet_controls": quiet,
            "total_errors": total_errors,
            "acceptance_ready": acceptance_ready,
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "github_sha": os.environ.get("GITHUB_SHA"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        },
        "claim_boundary": (
            "Detection-level candidate acceptance on two frozen, independently labelled "
            "corpora. This is not a population-wide false-positive rate, proof that quiet "
            "controls contain no planets, astrophysical classification accuracy, or formal "
            "FPP calibration."
        ),
    }
    return report, rows


def aggregate(args: argparse.Namespace) -> int:
    report, rows = aggregate_shards(args.shards, args.shard_count)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.rows.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(report))
    args.rows.write_text(
        "".join(
            json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows
        ),
        encoding="utf-8",
    )
    print(json.dumps(report["evaluation"], indent=2, sort_keys=True))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run-shard")
    run.add_argument("--labelled-corpus", type=Path, required=True)
    run.add_argument("--fp-subset", type=Path, required=True)
    run.add_argument("--quiet-pool", type=Path, required=True)
    run.add_argument("--prior-hosts", type=Path, required=True)
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--shard-index", type=int, required=True)
    run.add_argument("--shard-count", type=int, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.set_defaults(handler=run_shard)
    combine = sub.add_parser("aggregate")
    combine.add_argument("--shards", type=Path, required=True)
    combine.add_argument("--shard-count", type=int, required=True)
    combine.add_argument("--output", type=Path, required=True)
    combine.add_argument("--rows", type=Path, required=True)
    combine.set_defaults(handler=aggregate)
    return root


def main() -> int:
    args = parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
