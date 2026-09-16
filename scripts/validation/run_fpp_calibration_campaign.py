#!/usr/bin/env python3
"""Run and aggregate the labelled FPP-calibration campaign (acceptance gate).

The gate contract lives in
``validation_runs/final_acceptance_v1/program.json`` under
``fpp_quality_calibration`` and its evidence path is
``validation_runs/final_acceptance_v1/fpp_calibration/report.json``. This
script produces that artifact; nothing else may claim the gate.

Three subcommands:

``build-cohorts``
    Deterministic, detector-independent selection of labelled false positives
    and labelled planets from the frozen TFOP disposition corpus. Runs fully
    offline and verifies the frozen cohort hash.

``run-shard``
    Executes the pipeline for one shard. Needs MAST access; this is the CI
    lane. Rows carry per-target FPP telemetry (``astrotransit.validation.
    fpp_telemetry``).

``aggregate``
    Offline: reads shard rows, scores the heuristic proxy on frozen
    development/validation/blind-test splits and writes the gate report.

Missing FPP values stay ``not_evaluated`` and are never converted to ``0.0``.
Quiet controls are never used as calibration labels.
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from astrotransit.validation.benchmark_report import normalize_target_id  # noqa: E402
from astrotransit.validation.corpus import CorpusCase, load_corpus  # noqa: E402
from astrotransit.validation.fpp_benchmark import FPPBenchmarkCase  # noqa: E402
from astrotransit.validation.fpp_calibration import (  # noqa: E402
    FPP_CALIBRATION_SEED,
    FPP_CALIBRATION_THRESHOLD,
    build_fpp_calibration_report,
)
from astrotransit.validation.provenance import build_manifest  # noqa: E402

LABELLED_CORPUS = "benchmarks/corpora/tfop_disposition_corpus_v1.json"
PRIOR_INJECTION_HOSTS = "validation_runs/v1_injection_recovery/real_noise_v1/input/quiet_hosts.json"
COHORT_MANIFEST = "validation_runs/final_acceptance_v1/fpp_calibration/cohort_manifest.json"
COHORT_METHOD = "sha256_seeded_rank_after_label_and_host_exclusions_v1"
COHORT_SEED = 20260917
REQUIRED_PER_LABEL = 100
CAMPAIGN = "fpp_quality_calibration_v1"


def canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _display_path(path: Path) -> str:
    """Repona göre göreli yol; repo dışı geçici yollar absolute kalır."""

    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def _rank(seed: int, target_id: str) -> str:
    return hashlib.sha256(f"{seed}:{target_id}".encode()).hexdigest()


def select_cohorts(
    labelled_corpus: Path,
    prior_hosts: Path,
    *,
    required: int = REQUIRED_PER_LABEL,
    seed: int = COHORT_SEED,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Selects frozen labelled cohorts without ever consulting the detector."""

    cases = load_corpus(labelled_corpus)
    excluded_hosts: set[str] = set()
    if prior_hosts.is_file():
        payload = json.loads(prior_hosts.read_text(encoding="utf-8"))
        rows = payload.get("hosts", payload.get("cases", [])) if isinstance(payload, dict) else payload
        for row in rows:
            value = row.get("target_id", row.get("tic_id", "")) if isinstance(row, dict) else row
            excluded_hosts.add(normalize_target_id(value))

    rejected: Counter[str] = Counter()
    pools: dict[str, list[dict[str, Any]]] = {"false_positive": [], "planet": []}
    for case in cases:
        target = normalize_target_id(case.target_id)
        if case.label not in pools:
            rejected["unusable_label_for_calibration"] += 1
            continue
        if target in excluded_hosts:
            rejected["prior_injection_host"] += 1
            continue
        pools[case.label].append(
            {
                "target_id": target,
                "label": case.label,
                "reference": case.reference,
                "sectors": list(case.sectors),
                "notes": case.notes,
                "selection_rank": _rank(seed, target),
            }
        )

    cohorts: dict[str, list[dict[str, Any]]] = {}
    for label, rows in pools.items():
        rows.sort(key=lambda row: (row["selection_rank"], row["target_id"]))
        if len(rows) < required:
            rejected[f"insufficient_pool_for_{label}"] += 1
        cohorts[label] = rows[:required]

    fp_rows = cohorts["false_positive"]
    planet_rows = cohorts["planet"]
    overlap = {row["target_id"] for row in fp_rows} & {row["target_id"] for row in planet_rows}
    if overlap:
        raise ValueError(f"labelled cohorts overlap: {sorted(overlap)[:5]}")

    cases_out = [
        {"target_id": row["target_id"], "label": row["label"], "reference": row["reference"]}
        for row in [*fp_rows, *planet_rows]
    ]
    status = "frozen" if len(cases_out) == 2 * required and not overlap else "insufficient_candidates"
    payload = {
        "schema_version": "1.0",
        "corpus": CAMPAIGN,
        "status": status,
        "required_count": required,
        "selected_count": len(cases_out),
        "counts": {label: len(rows) for label, rows in cohorts.items()},
        "selection": {
            "method": COHORT_METHOD,
            "seed": seed,
            "metric_seed": FPP_CALIBRATION_SEED,
            "detector_used_for_selection": False,
            "prior_injection_hosts_excluded": True,
        },
        "label_definition": {
            "false_positive": "TFOP working-group disposition label",
            "planet": "TFOP working-group disposition label",
        },
        "cases": cases_out,
    }
    audit = {
        "schema_version": "1.0",
        "campaign": CAMPAIGN,
        "status": status,
        "seed": seed,
        "required_count": required,
        "selected_count": len(cases_out),
        "eligible_counts": {label: len(rows) for label, rows in pools.items()},
        "rejection_counts": dict(sorted(rejected.items())),
        "cohort_sha256": hashlib.sha256(canonical_json(payload)).hexdigest(),
        "sources": {
            "labelled_corpus": {"path": _display_path(labelled_corpus), "sha256": sha256(labelled_corpus)},
            "prior_injection_hosts": {
                "path": _display_path(prior_hosts),
                "sha256": sha256(prior_hosts) if prior_hosts.is_file() else None,
            },
        },
        "claim_boundary": (
            "Cohort membership comes only from external catalogue dispositions. AstroTransit "
            "output was never used to select targets, so this selection cannot inflate the "
            "measured separation of the FPP proxy."
        ),
    }
    return payload, audit


def _verify_frozen_manifest(payload: dict[str, Any], audit: dict[str, Any], manifest_path: Path) -> None:
    if not manifest_path.is_file():
        raise ValueError(
            f"frozen cohort manifest missing: {manifest_path}; run build-cohorts and commit it"
        )
    frozen = json.loads(manifest_path.read_text(encoding="utf-8"))
    selection = frozen.get("selection") or {}
    checks = {
        "cohort_sha256": (audit["cohort_sha256"], frozen.get("cohort_sha256")),
        "selected_count": (payload["selected_count"], frozen.get("selected_count")),
        "seed": (payload["selection"]["seed"], selection.get("seed", frozen.get("seed"))),
    }
    for key, (expected, observed) in checks.items():
        if observed != expected:
            raise ValueError(
                f"frozen cohort manifest disagrees on {key}: {observed!r} != {expected!r}"
            )
    corpus_hash = audit["sources"]["labelled_corpus"]["sha256"]
    if frozen.get("sources", {}).get("labelled_corpus", {}).get("sha256") != corpus_hash:
        raise ValueError("frozen cohort manifest points at a different labelled corpus")


def build_cohorts(args: argparse.Namespace) -> int:
    payload, audit = select_cohorts(args.labelled_corpus, args.prior_hosts, seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(payload))
    args.audit.write_bytes(canonical_json(audit))
    if args.manifest:
        manifest = {
            "schema_version": "1.0",
            "corpus": CAMPAIGN,
            "status": payload["status"],
            "materialization": "deterministic_rebuild_from_frozen_sources",
            "required_count": payload["required_count"],
            "selected_count": payload["selected_count"],
            "counts": payload["counts"],
            "selection": payload["selection"],
            "cohort_sha256": audit["cohort_sha256"],
            "selection_audit_sha256": hashlib.sha256(canonical_json(audit)).hexdigest(),
            "sources": audit["sources"],
            "rejection_counts": audit["rejection_counts"],
            "claim_boundary": audit["claim_boundary"],
        }
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_bytes(canonical_json(manifest))
        print(json.dumps(manifest, indent=2, sort_keys=True))
    print(
        json.dumps(
            {
                "status": payload["status"],
                "selected_count": payload["selected_count"],
                "cohort_sha256": audit["cohort_sha256"],
                "rejection_counts": audit["rejection_counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if payload["status"] == "frozen" else 2


def _cohort_cases(manifest_path: Path, labelled_corpus: Path, prior_hosts: Path, *, seed: int) -> list[CorpusCase]:
    payload, audit = select_cohorts(labelled_corpus, prior_hosts, seed=seed)
    _verify_frozen_manifest(payload, audit, manifest_path)
    labelled = {normalize_target_id(case.target_id): case for case in load_corpus(labelled_corpus)}
    cases: list[CorpusCase] = []
    for row in payload["cases"]:
        case = labelled.get(str(row["target_id"]))
        if case is None or case.label != row["label"]:
            raise ValueError(f"cohort target lost its frozen label: {row['target_id']}")
        cases.append(case)
    return cases


def run_shard(args: argparse.Namespace) -> int:
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        raise ValueError("invalid shard index/count")
    from scripts.validation.run_false_positive_controls import _evaluate_case

    cases = _cohort_cases(args.cohort_manifest, args.labelled_corpus, args.prior_hosts, seed=args.seed)
    selected = [case for index, case in enumerate(cases) if index % args.shard_count == args.shard_index]

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
        "campaign": CAMPAIGN,
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "case_count": len(rows),
        "cohort_sha256": hashlib.sha256(canonical_json({"ids": [row["target_id"] for row in rows]})).hexdigest(),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(payload))
    print(f"Wrote FPP-calibration shard {args.shard_index}: {len(rows)} cases to {args.output}")
    return 0


def _read_rows(shards: Path, shard_count: int, rows_path: Path | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if rows_path is not None and rows_path.is_file():
        rows = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return rows, {"source": str(rows_path), "sha256": sha256(rows_path)}
    rows: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}
    for index in range(shard_count):
        path = shards / f"shard-{index:02d}.json"
        if not path.exists():
            raise FileNotFoundError(f"missing shard: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("campaign") != CAMPAIGN:
            raise ValueError(f"unexpected campaign in {path}: {payload.get('campaign')!r}")
        if payload["shard_index"] != index or payload["shard_count"] != shard_count:
            raise ValueError(f"invalid shard contract: {path}")
        rows.extend(payload["rows"])
        metadata = {**metadata, "shard_sha256": {**metadata.get("shard_sha256", {}), str(index): sha256(path)}}
    metadata["source"] = str(shards)
    return rows, metadata


def aggregate(args: argparse.Namespace) -> int:
    rows, source = _read_rows(args.shards, args.shard_count, args.rows)
    ids = [str(row.get("target_id", "")) for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("campaign rows contain duplicate target ids")
    counts = Counter(str(row.get("label")) for row in rows)
    for label in ("false_positive", "planet"):
        if counts[label] < args.min_per_label:
            raise ValueError(
                f"insufficient labelled {label} rows for a frozen campaign: "
                f"{counts[label]} < {args.min_per_label}"
            )

    cohort_info: dict[str, Any] = {}
    if args.cohort_manifest and args.cohort_manifest.is_file():
        frozen = json.loads(args.cohort_manifest.read_text(encoding="utf-8"))
        cohort_info = {
            "method": frozen["selection"]["method"],
            "seed": frozen["selection"]["seed"],
            "detector_used_for_selection": frozen["selection"]["detector_used_for_selection"],
            "cohort_sha256": frozen["cohort_sha256"],
            "selected_count": frozen["selected_count"],
            "labelled_corpus_sha256": frozen["sources"]["labelled_corpus"]["sha256"],
        }

    config_payload: dict[str, Any] = {}
    if args.config and args.config.is_file():
        config_payload = {"path": str(args.config), "sha256": sha256(args.config)}
    provenance = build_manifest(
        config=config_payload,
        seed=args.split_seed,
        pipeline_version=_pipeline_version(),
        root=ROOT,
    )
    report = build_fpp_calibration_report(
        rows,
        threshold=args.threshold,
        seed=args.split_seed,
        cohorts=cohort_info,
        provenance=provenance,
        environment={
            "python": sys.version,
            "platform": platform.platform(),
            "github_sha": os.environ.get("GITHUB_SHA"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    rows.sort(key=lambda row: (0 if row.get("label") == "false_positive" else 1, str(row.get("target_id", ""))))
    report["source"] = source
    report["rows_sha256"] = hashlib.sha256(canonical_json(rows)).hexdigest()
    report["recorded_rows"] = len(rows)
    report["label_counts"] = dict(sorted(counts.items()))
    if args.rows_out:
        args.rows_out.parent.mkdir(parents=True, exist_ok=True)
        args.rows_out.write_text(
            "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(report))
    if args.cases_output:
        cases = [
            {"target_id": case.target_id, "is_false_positive": case.is_false_positive, "fpp": case.fpp}
            for case in _materialized_cases(rows)
        ]
        args.cases_output.parent.mkdir(parents=True, exist_ok=True)
        args.cases_output.write_bytes(canonical_json({"schema_version": "1.0", "cases": cases}))
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_bytes(
            canonical_json(
                {
                    "report_sha256": sha256(args.output),
                    "rows_sha256": report["rows_sha256"],
                    "status": report["status"],
                    "recorded_rows": report["recorded_rows"],
                }
            )
        )
    print(
        json.dumps(
            {
                "status": report["status"],
                "blocking_reasons": report["blocking_reasons"],
                "cases": report["cases"],
                "blind_test": report["splits"]["blind_test"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _materialized_cases(rows: list[dict[str, Any]]) -> list[FPPBenchmarkCase]:
    from astrotransit.validation.fpp_telemetry import read_row_fpp

    cases: list[FPPBenchmarkCase] = []
    for row in rows:
        value, _method, reason = read_row_fpp(row)
        label = str(row.get("label"))
        if reason != "ok" or value is None or label not in {"false_positive", "planet"}:
            continue
        cases.append(FPPBenchmarkCase(str(row["target_id"]), label == "false_positive", float(value)))
    return cases


def _pipeline_version() -> str:
    from astrotransit.version import __version__

    return __version__


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build-cohorts")
    build.add_argument("--labelled-corpus", type=Path, default=ROOT / LABELLED_CORPUS)
    build.add_argument("--prior-hosts", type=Path, default=ROOT / PRIOR_INJECTION_HOSTS)
    build.add_argument("--seed", type=int, default=COHORT_SEED)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--audit", type=Path, required=True)
    build.add_argument("--manifest", type=Path)
    build.set_defaults(handler=build_cohorts)

    run = sub.add_parser("run-shard")
    run.add_argument("--labelled-corpus", type=Path, default=ROOT / LABELLED_CORPUS)
    run.add_argument("--prior-hosts", type=Path, default=ROOT / PRIOR_INJECTION_HOSTS)
    run.add_argument("--cohort-manifest", type=Path, default=ROOT / COHORT_MANIFEST)
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--seed", type=int, default=COHORT_SEED)
    run.add_argument("--shard-index", type=int, required=True)
    run.add_argument("--shard-count", type=int, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.set_defaults(handler=run_shard)

    combine = sub.add_parser("aggregate")
    combine.add_argument("--shards", type=Path)
    combine.add_argument("--rows", type=Path)
    combine.add_argument("--rows-out", type=Path, dest="rows_out")
    combine.add_argument("--shard-count", type=int, default=20)
    combine.add_argument("--min-per-label", type=int, default=60)
    combine.add_argument("--threshold", type=float, default=FPP_CALIBRATION_THRESHOLD)
    combine.add_argument("--split-seed", type=int, default=FPP_CALIBRATION_SEED)
    combine.add_argument("--cohort-manifest", type=Path, default=ROOT / COHORT_MANIFEST)
    combine.add_argument("--config", type=Path)
    combine.add_argument("--output", type=Path, required=True)
    combine.add_argument("--cases-output", type=Path)
    combine.add_argument("--manifest", type=Path)
    combine.set_defaults(handler=aggregate)
    return root


def main() -> int:
    args = parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
