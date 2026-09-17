#!/usr/bin/env python3
"""Freeze and measure the blind domain holdout gate.

``build-corpus`` and ``check`` are fully offline: membership is derived from
committed label sources, the disjointness proof is recorded, and the corpus hash
is frozen. ``run-shard`` / ``aggregate`` need light curves (MAST) and are meant
for CI or a machine with archive access; they refuse to run against anything but
the frozen corpus.

The gate contract (thresholds) is pre-declared in
``validation_runs/final_acceptance_v1/program.json`` and never edited here.
Freezing the gate status is a separate, explicit commit of the produced evidence.
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

from astrotransit.validation.blind_holdout import (  # noqa: E402
    CAMPAIGN,
    DECLARED_CEILING_FALSE_POSITIVE_RATE,
    DECLARED_FLOOR_RECALL,
    FP_RUN_SUBSET,
    GATE_ID,
    HOLDOUT_MANIFEST,
    HOLDOUT_SEED,
    LABELLED_CORPUS,
    MINIMUM_CASES_PER_STRATUM,
    MINIMUM_EVALUATED_CASES,
    PRIOR_INJECTION_HOSTS,
    REQUIRED_OUTPUT,
    SELECTION_METHOD,
    SPLIT_SEED,
    build_holdout_report,
    holdout_sha256,
    load_exclusion_ids,
    normalize_target_id,
    select_holdout,
)

PROGRAM = str(ROOT / "validation_runs/final_acceptance_v1/program.json")
PER_LABEL = 72
ROW_VERSION = "1.0"


def canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def sha256_file(path: Path) -> str | None:
    return None if not path.is_file() else hashlib.sha256(path.read_bytes()).hexdigest()


def _cohort_ids() -> list[str]:
    """Frozen FPP-calibration cohort ids (recomputed offline) for disjointness."""

    try:
        from scripts.validation.run_fpp_calibration_campaign import select_cohorts
    except Exception:  # noqa: BLE001 - campaign script must stay optional here
        return []
    try:
        payload, _ = select_cohorts(
            ROOT / LABELLED_CORPUS,
            ROOT / PRIOR_INJECTION_HOSTS,
            seed=HOLDOUT_SEED,
        )
    except Exception:  # noqa: BLE001
        return []
    ids: set[str] = set()
    for group in ("false_positives", "planets"):
        for row in payload.get(group, []) or []:
            ids.add(normalize_target_id(row.get("target_id", "")))
    return sorted(ids)


def _measured_rows_ids() -> list[str]:
    """Any target already consumed by a prior gate that left row files behind."""

    ids: set[str] = set()
    patterns = (
        "validation_runs/final_acceptance_v1/**/rows.jsonl",
        "validation_runs/final_acceptance_v1/**/shard-*.json",
        "validation_runs/v1_injection_recovery/**/rows.jsonl",
    )
    for pattern in patterns:
        for path in sorted(ROOT.glob(pattern)):
            try:
                if path.suffix == ".jsonl":
                    for line in path.read_text(encoding="utf-8").splitlines():
                        if line.strip():
                            ids.add(normalize_target_id(json.loads(line).get("target_id", "")))
                else:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    for row in payload.get("rows", []) or []:
                        ids.add(normalize_target_id(row.get("target_id", "")))
            except Exception:  # noqa: BLE001 - an unreadable artefact must not fake a holdout
                continue
    ids.discard("")
    return sorted(ids)


def exclusion_sources() -> dict[str, list[str]]:
    sources = {
        "fp_run_subset": [],
        "prior_injection_quiet_hosts": [],
        "fpp_calibration_cohort": _cohort_ids(),
        "prior_gate_row_files": _measured_rows_ids(),
    }
    for name, relative in (("fp_run_subset", FP_RUN_SUBSET), ("prior_injection_quiet_hosts", PRIOR_INJECTION_HOSTS)):
        per_source, _ = load_exclusion_ids({name: ROOT / relative})
        sources[name] = per_source[name]
    return sources


def build_corpus(args: argparse.Namespace) -> int:
    cases = json.loads((ROOT / LABELLED_CORPUS).read_text(encoding="utf-8"))["cases"]
    sources = exclusion_sources()
    combined: set[str] = set()
    for ids in sources.values():
        combined |= set(ids)
    payload = select_holdout(
        cases,
        excluded_ids=combined,
        per_label=args.per_label,
        seed=args.seed,
        split_seed=args.split_seed,
        minimum_per_stratum=args.minimum_per_stratum,
    )
    payload["exclusions"] = {
        "sources": {name: ids for name, ids in sorted(sources.items())},
        "n_excluded_ids": len(combined),
        "policy": (
            "every id touched by a prior gate is removed before ranking, so the holdout cannot inherit a "
            "selection advantage from earlier measurements"
        ),
    }
    payload["sources"] = {
        "labelled_corpus": LABELLED_CORPUS,
        "labelled_corpus_sha256": sha256_file(ROOT / LABELLED_CORPUS),
        "fp_run_subset": FP_RUN_SUBSET,
        "fp_run_subset_sha256": sha256_file(ROOT / FP_RUN_SUBSET),
        "prior_injection_hosts": PRIOR_INJECTION_HOSTS,
        "prior_injection_hosts_sha256": sha256_file(ROOT / PRIOR_INJECTION_HOSTS),
    }
    payload["holdout_sha256"] = holdout_sha256(payload["cases"])
    output = Path(args.output)
    if args.dry_run:
        keys = ("counts", "stratum_counts", "pool_sizes", "holdout_sha256")
        print(json.dumps({key: payload[key] for key in keys}, indent=2, sort_keys=True))
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json(payload))
    print(
        json.dumps(
            {
                "output": str(output),
                "n_cases": len(payload["cases"]),
                "counts": payload["counts"],
                "stratum_counts": payload["stratum_counts"],
                "excluded_ids": payload["exclusions"]["n_excluded_ids"],
                "holdout_sha256": payload["holdout_sha256"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _load_frozen(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.is_file():
        raise ValueError(f"frozen holdout manifest missing: {manifest_path}; run build-corpus first")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _verify_membership(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("status") != "frozen":
        raise ValueError(f"holdout corpus is not frozen: status={manifest.get('status')!r}")
    cases = list(manifest["cases"])
    digest = holdout_sha256(cases)
    if digest != manifest.get("holdout_sha256"):
        raise ValueError(f"holdout membership drifted from the frozen corpus: {digest[:12]} != {str(manifest.get('holdout_sha256'))[:12]}")
    return cases


def check_contract(args: argparse.Namespace) -> int:
    """Prove offline that the committed corpus and program.json still agree."""

    manifest = _load_frozen(Path(args.manifest))
    cases = _verify_membership(manifest)
    rebuilt = select_holdout(
        json.loads((ROOT / LABELLED_CORPUS).read_text(encoding="utf-8"))["cases"],
        excluded_ids={item for ids in manifest["exclusions"]["sources"].values() for item in ids},
        per_label=int(manifest["selection"]["per_label_quota"]),
        seed=int(manifest["selection"]["seed"]),
        split_seed=int(manifest["selection"]["split_seed"]),
        minimum_per_stratum=int(manifest["selection"]["minimum_per_stratum"]),
    )
    if rebuilt["holdout_sha256"] != manifest["holdout_sha256"]:
        raise ValueError("the committed holdout differs from a rebuild of its frozen sources")
    if [row["target_id"] for row in rebuilt["cases"]] != [row["target_id"] for row in cases]:
        raise ValueError("holdout case order or membership changed")
    if min(manifest["stratum_counts"].values()) < int(manifest["selection"]["minimum_per_stratum"]):
        raise ValueError("a stratum is undersampled in the frozen holdout")

    program = json.loads(Path(PROGRAM).read_text(encoding="utf-8"))
    gate = next((item for item in program["gates"] if item.get("id") == GATE_ID), None)
    if gate is None:
        raise ValueError(f"gate {GATE_ID} missing from program.json")
    checks = {str(item.get("path")): item for item in gate.get("acceptance_checks", [])}
    if checks.get("corpus.sha256", {}).get("value") != manifest["holdout_sha256"]:
        raise ValueError("program.json pins a different holdout corpus than the committed manifest")
    if checks.get("overall.recall", {}).get("value") != manifest["floors"]["recall"]:
        raise ValueError("program.json and the frozen corpus disagree on the recall floor")
    if checks.get("overall.false_positive_rate", {}).get("value") != manifest["floors"]["false_positive_rate_ceiling"]:
        raise ValueError("program.json and the frozen corpus disagree on the false-positive ceiling")
    if checks.get("method.retrained", {}).get("value") is not False:
        raise ValueError("the holdout must declare that nothing was retrained on it")
    print(
        json.dumps(
            {
                "holdout_sha256": manifest["holdout_sha256"],
                "n_cases": len(cases),
                "counts": manifest["counts"],
                "stratum_counts": manifest["stratum_counts"],
                "excluded_ids": manifest["exclusions"]["n_excluded_ids"],
                "declared_checks": len(gate.get("acceptance_checks", [])),
                "status": "contract_consistent",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _evaluate_case(case: dict[str, Any], orchestrator: Any, sector_client: Any) -> dict[str, Any]:
    """Tek hedef: sektör seçimi → pipeline → kabul edilmiş aday var mı?"""

    requested = [int(item) for item in case.get("sectors", []) or []]
    sector_source = "frozen_corpus"
    error = ""
    if not requested:
        sector_source = "lowest_available_spoc_120s_at_run"
        try:
            requested = list(sector_client.get_available_sectors(case["target_id"]))[:1]
        except Exception as exc:  # noqa: BLE001 - archive failure stays an error row
            error = f"sector_lookup_failed:{type(exc).__name__}: {exc}"
    row = {
        "target_id": normalize_target_id(case["target_id"]),
        "label": case["label"],
        "stratum": case["stratum"],
        "requested_sectors": requested,
        "sector_source": sector_source,
        "successful_sector_count": 0,
        "accepted_candidate": None,
        "candidate_count": None,
        "error": error,
    }
    if not requested:
        row["error"] = error or "no_available_spoc_120s_sector"
        return row
    try:
        result = orchestrator.run_single(row["target_id"], sectors=requested)
        sectors = list(getattr(result, "sector_results", []) or [])
        confirmed = [item for item in sectors if getattr(item, "candidate_confirmed", False)]
        row["successful_sector_count"] = sum(1 for item in sectors if getattr(item, "success", False))
        row["candidate_count"] = len(sectors)
        row["accepted_candidate"] = bool(confirmed)
        row["quality_classes"] = [
            str(getattr(getattr(getattr(item, "quality", None), "score", None), "candidate_class", "") or "")
            for item in sectors
        ]
        row["quality_scores"] = [
            getattr(getattr(getattr(item, "quality", None), "score", None), "total_score", None) for item in sectors
        ]
    except Exception as exc:  # noqa: BLE001 - a failed target must never count as a pass
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def run_shard(args: argparse.Namespace) -> int:
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        raise ValueError("invalid shard index/count")
    manifest = _load_frozen(Path(args.manifest))
    cases = _verify_membership(manifest)
    selected = [case for index, case in enumerate(cases) if index % args.shard_count == args.shard_index]

    if args.offline:
        rows = [
            {
                **{key: case[key] for key in ("target_id", "label", "stratum")},
                "requested_sectors": [],
                "sector_source": "offline_placeholder",
                "successful_sector_count": 0,
                "accepted_candidate": None,
                "candidate_count": None,
                "error": "offline_mode_no_light_curves",
            }
            for case in selected
        ]
    else:
        from astrotransit.data.tess_client import TESSClient
        from astrotransit.pipelines.orchestrator import AstroTransitOrchestrator

        sector_client = TESSClient()
        with AstroTransitOrchestrator(
            config_path=str(args.config) if args.config else None,
            force_map=True,
            skip_visualization=True,
            log_level="INFO",
        ) as orchestrator:
            rows = [_evaluate_case(case, orchestrator, sector_client) for case in selected]

    payload = {
        "schema_version": ROW_VERSION,
        "campaign": CAMPAIGN,
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "case_count": len(rows),
        "holdout_sha256": manifest["holdout_sha256"],
        "rows": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json(payload))
    print(f"Wrote shard {args.shard_index}: {len(rows)} cases -> {output}")
    return 0


def aggregate(args: argparse.Namespace) -> int:
    manifest = _load_frozen(Path(args.manifest))
    corpus_ids = {case["target_id"] for case in manifest["cases"]}
    rows: list[dict[str, Any]] = []
    sources: list[str] = []
    seen: set[str] = set()
    for item in args.rows:
        path = Path(item)
        paths = sorted(path.glob("shard-*.json")) or sorted(path.glob("*.json")) if path.is_dir() else [path]
        for shard in paths:
            sources.append(str(shard))
            payload = json.loads(shard.read_text(encoding="utf-8"))
            for row in payload["rows"]:
                if row["target_id"] in seen:
                    continue
                seen.add(row["target_id"])
                rows.append(row)
    if not rows:
        raise ValueError("aggregate: değerlendirme satırı bulunamadı (--rows)")
    unknown = sorted(seen - corpus_ids)
    if unknown:
        raise ValueError(f"aggregate: korpusda olmayan hedef(ler) değerlendirilemez: {unknown[:5]}")

    from astrotransit.validation.provenance import build_manifest

    provenance = build_manifest(
        input_path=Path(args.manifest),
        config={"shard_files": len(sources), "n_rows": len(rows), "config": None if args.config is None else str(args.config)},
        seed=int(manifest["selection"]["seed"]),
        root=ROOT,
    )
    provenance["holdout_manifest_sha256"] = hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest()
    provenance["shard_files"] = [Path(item).name for item in sources]

    report = build_holdout_report(
        rows,
        manifest=manifest,
        split_seed=int(manifest["selection"]["split_seed"]),
        floor_recall=args.floor_recall,
        ceiling_false_positive_rate=args.ceiling_false_positive_rate,
        minimum_evaluated=args.minimum_evaluated,
        minimum_per_stratum=args.minimum_per_stratum,
        provenance=provenance,
        environment={
            "python": sys.version,
            "platform": platform.platform(),
            "github_sha": os.environ.get("GITHUB_SHA"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "row_sources": sources,
        },
    )
    report["rows_sha256"] = hashlib.sha256(canonical_json(rows)).hexdigest()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json(report))
    print(
        json.dumps(
            {
                "status": report["status"],
                "blocking_reasons": report["blocking_reasons"],
                "data": report["data"],
                "overall": report["overall"],
                "holdout_sha256": report["corpus"]["sha256"],
                "strata": {
                    name: {
                        "n": block["n_evaluated"],
                        "recall": block["recall"],
                        "false_positive_rate": block["false_positive_rate"],
                    }
                    for name, block in report["strata"].items()
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "measured" else 3


def summary(args: argparse.Namespace) -> int:
    manifest = _load_frozen(Path(args.manifest))
    labels = Counter(case["label"] for case in manifest["cases"])
    print(
        json.dumps(
            {
                "campaign": CAMPAIGN,
                "status": manifest["status"],
                "selection_method": SELECTION_METHOD,
                "counts": dict(sorted(labels.items())),
                "stratum_counts": manifest["stratum_counts"],
                "pool_sizes": manifest["pool_sizes"],
                "excluded_ids": manifest["exclusions"]["n_excluded_ids"],
                "holdout_sha256": manifest["holdout_sha256"],
                "floors": manifest["floors"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build-corpus")
    build.add_argument("--per-label", type=int, default=PER_LABEL)
    build.add_argument("--seed", type=int, default=HOLDOUT_SEED)
    build.add_argument("--split-seed", type=int, default=SPLIT_SEED)
    build.add_argument("--minimum-per-stratum", type=int, default=MINIMUM_CASES_PER_STRATUM)
    build.add_argument("--output", default=str(ROOT / HOLDOUT_MANIFEST))
    build.add_argument("--dry-run", action="store_true")
    build.set_defaults(handler=build_corpus)

    contract = sub.add_parser("check")
    contract.add_argument("--manifest", default=str(ROOT / HOLDOUT_MANIFEST))
    contract.set_defaults(handler=check_contract)

    execute = sub.add_parser("run-shard")
    execute.add_argument("--manifest", default=str(ROOT / HOLDOUT_MANIFEST))
    execute.add_argument("--shard-index", type=int, required=True)
    execute.add_argument("--shard-count", type=int, default=1)
    execute.add_argument("--config", type=Path)
    execute.add_argument("--output", required=True)
    execute.add_argument("--offline", action="store_true", help="write unrunnable rows (contract testing only)")
    execute.set_defaults(handler=run_shard)

    collect = sub.add_parser("aggregate")
    collect.add_argument("--manifest", default=str(ROOT / HOLDOUT_MANIFEST))
    collect.add_argument("--rows", type=Path, nargs="+", required=True)
    collect.add_argument("--config", type=Path)
    collect.add_argument("--output", default=str(ROOT / REQUIRED_OUTPUT))
    collect.add_argument("--floor-recall", type=float, default=DECLARED_FLOOR_RECALL)
    collect.add_argument("--ceiling-false-positive-rate", type=float, default=DECLARED_CEILING_FALSE_POSITIVE_RATE)
    collect.add_argument("--minimum-evaluated", type=int, default=MINIMUM_EVALUATED_CASES)
    collect.add_argument("--minimum-per-stratum", type=int, default=MINIMUM_CASES_PER_STRATUM)
    collect.set_defaults(handler=aggregate)

    info = sub.add_parser("summary")
    info.add_argument("--manifest", default=str(ROOT / HOLDOUT_MANIFEST))
    info.set_defaults(handler=summary)
    return root


def main() -> int:
    args = parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
