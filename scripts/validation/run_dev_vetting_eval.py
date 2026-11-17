"""DEV-only evaluation: run the full pipeline on the balanced24 dev corpus and
dump per-sector vetting/metric rows. NEVER touches the blind holdout manifest.

Red line (docs/blind_recall_roadmap.md): all recall fixes are validated on this
dev corpus first; the blind holdout is run exactly once at the end.

Writes validation_runs/_triage/dev_eval_shard0.json by default (triage dir, not
a gate); ``--output`` can direct a fresh run to a separate evidence path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import scripts.validation.run_blind_holdout as blind_runner  # noqa: E402
from astrotransit.pipelines.orchestrator import AstroTransitOrchestrator  # noqa: E402

# Windows has no SIGALRM; the dev runner is local-only, so use a no-op time limit.
if not hasattr(blind_runner.signal, "SIGALRM"):
    from contextlib import contextmanager

    @contextmanager
    def _noop_time_limit(seconds):
        yield

    blind_runner._time_limit = _noop_time_limit

_evaluate_case = blind_runner._evaluate_case

MANIFEST = ROOT / "validation_runs/final_acceptance_v1/dev_holdout/dev_manifest_balanced24.json"
OUT = ROOT / "validation_runs/_triage/dev_eval_shard0.json"


def _f(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _reaggregate_rows(rows: list[dict], cases: list[dict]) -> list[dict]:
    """Reapply the current aggregation to persisted per-sector measurements."""

    expected = {
        blind_runner.normalize_target_id(case["target_id"]): str(case["label"])
        for case in cases
    }
    if len(expected) != len(cases):
        raise ValueError("development manifest contains duplicate target IDs")

    output: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        target_id = blind_runner.normalize_target_id(row.get("target_id", ""))
        if target_id not in expected:
            raise ValueError(f"unexpected development row target: {target_id!r}")
        if target_id in seen:
            raise ValueError(f"duplicate development row target: {target_id}")
        seen.add(target_id)
        if str(row.get("label")) != expected[target_id]:
            raise ValueError(f"development row label mismatch for {target_id}")
        if row.get("error"):
            raise ValueError(f"development evaluation failed for {target_id}: {row['error']}")
        per_sector = row.get("per_sector")
        if not isinstance(per_sector, list):
            raise ValueError(f"development row has no per-sector measurements: {target_id}")

        signals = []
        for sector in per_sector:
            tests = sector.get("vetting_tests", []) or []
            signals.append({
                "has_candidate": bool(sector.get("has_candidate")),
                "candidate_confirmed": bool(sector.get("candidate_confirmed")),
                "vetting_is_false_positive": bool(
                    sector.get("vetting_is_false_positive")
                ),
                "failed_tests": [
                    str(test.get("name", "") or "")
                    for test in tests
                    if str(test.get("verdict", "")).lower() == "fail"
                ],
                "candidate_period_days": sector.get("candidate_period_days"),
            })
        accepted, aggregation = blind_runner._aggregate_sector_signals(signals)
        output.append({**row, "accepted_candidate": accepted, "aggregation": aggregation})

    missing = sorted(set(expected) - seen)
    if missing:
        raise ValueError(f"development evaluation missing targets: {missing}")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument(
        "--reaggregate-from",
        type=Path,
        default=None,
        help="reapply the current decision rule to a complete per-sector development output",
    )
    args = parser.parse_args(argv)

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if args.reaggregate_from is not None:
        if args.output.resolve() == args.reaggregate_from.resolve():
            parser.error("--output must differ from --reaggregate-from")
        source_text = args.reaggregate_from.read_text(encoding="utf-8")
        payload = json.loads(source_text)
        rows = payload.get("rows") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError("source must contain a 'rows' list of objects")
        payload["rows"] = _reaggregate_rows(rows, manifest["cases"])
        payload["reaggregation_provenance"] = {
            "source": str(args.reaggregate_from),
            "source_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
            "rule": "majority_veto_plus_period_consistency",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print("reaggregated", len(rows), "development rows to", args.output)
        return 0

    rows = []
    with AstroTransitOrchestrator(force_map=True, skip_visualization=True, log_level="WARNING") as orch:
        for i, case in enumerate(manifest["cases"], 1):
            row = _evaluate_case(case, orch, sector_client=None)
            rows.append(row)
            print(f"[{i}/{len(manifest['cases'])}] {row['target_id']} ({case['label']}): accepted={row.get('accepted_candidate')} err={str(row.get('error',''))[:60]}", flush=True)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps({"rows": rows}, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("wrote", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
