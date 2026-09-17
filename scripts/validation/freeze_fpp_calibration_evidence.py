#!/usr/bin/env python3
"""Freeze measured FPP-calibration evidence into the acceptance program.

This is the only sanctioned way to flip the ``fpp_quality_calibration`` gate
to ``measured``. It refuses to touch anything unless every condition below
holds, so a gate can never be closed by optimism:

1. the report declares ``status == "measured"`` and no ``blocking_reasons``;
2. the report's identity matches the campaign (``campaign`` + schema);
3. every pre-declared ``acceptance_checks`` entry in ``program.json`` passes
   against the report (same evaluator the audit uses);
4. the cohort binding matches the frozen ``cohort_manifest.json``;
5. artifact hashes match the CI manifest and the recomputed row digest.

Usage::

    python scripts/validation/freeze_fpp_calibration_evidence.py \\
      --report outputs/fpp-calibration-v1/report.json \\
      --rows outputs/fpp-calibration-v1/rows.jsonl \\
      --cases outputs/fpp-calibration-v1/fpp_cases.json \\
      --ci-manifest outputs/fpp-calibration-v1/manifest.json --dry-run

``--dry-run`` performs every check and prints what would change.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.validation.final_acceptance_audit import _evaluate_check  # noqa: E402
from scripts.validation.run_fpp_calibration_campaign import (  # noqa: E402
    CAMPAIGN,
    COHORT_MANIFEST,
    canonical_json,
)

GATE_ID = "fpp_quality_calibration"
SCHEMA_VERSION = "1.0"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows_digest(rows: list[dict[str, Any]]) -> str:
    """Recompute the aggregator's row identity (same sort, same canonical form)."""

    ordered = sorted(
        rows,
        key=lambda row: (0 if row.get("label") == "false_positive" else 1, str(row.get("target_id", ""))),
    )
    return hashlib.sha256(canonical_json(ordered)).hexdigest()


def load_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def verify(
    report: dict[str, Any],
    *,
    gate: dict[str, Any],
    cohort_manifest: dict[str, Any] | None,
    ci_manifest: dict[str, Any] | None,
    report_sha256: str | None,
    rows: list[dict[str, Any]] | None,
) -> list[str]:
    """Return a list of blocking problems; empty means the gate may be frozen."""

    problems: list[str] = []
    if str(report.get("campaign")) != CAMPAIGN:
        problems.append(f"campaign mismatch: {report.get('campaign')!r} != {CAMPAIGN!r}")
    if str(report.get("schema_version")) != SCHEMA_VERSION:
        problems.append(f"schema mismatch: {report.get('schema_version')!r} != {SCHEMA_VERSION!r}")
    if str(report.get("status")).lower() != "measured":
        problems.append(f"report status is {report.get('status')!r}; a run that did not measure cannot freeze")
    blockers = list(report.get("blocking_reasons") or [])
    if blockers:
        problems.append(f"report carries blocking_reasons: {blockers}")
    if report_sha256 and report.get("provenance", {}).get("report_sha256") not in (None, report_sha256):
        problems.append("report embeds a different report_sha256 than the provided artifact")
    if int(report.get("recorded_rows", -1)) != (len(rows) if rows is not None else int(report.get("recorded_rows", 0))):
        problems.append(
            f"recorded_rows ({report.get('recorded_rows')}) != rows file ({0 if rows is None else len(rows)})"
        )
    if rows is not None:
        digest = rows_digest(rows)
        if report.get("rows_sha256") != digest:
            problems.append(f"rows digest mismatch: recomputed {digest[:12]} != report {str(report.get('rows_sha256'))[:12]}")
    if ci_manifest:
        if report_sha256 and ci_manifest.get("report_sha256") != report_sha256:
            problems.append("CI manifest report_sha256 does not match the report file")
        if ci_manifest.get("rows_sha256") and rows is not None and ci_manifest["rows_sha256"] != report.get("rows_sha256"):
            problems.append("CI manifest rows_sha256 does not match the report")
        if str(ci_manifest.get("status", "measured")).lower() != "measured":
            problems.append(f"CI manifest status is {ci_manifest.get('status')!r}")
    if cohort_manifest:
        frozen_hash = (report.get("cohorts", {}).get("frozen_selection", {}) or {}).get("cohort_sha256")
        if frozen_hash != cohort_manifest.get("cohort_sha256"):
            problems.append(
                f"cohort binding mismatch: report {str(frozen_hash)[:12]} != manifest {str(cohort_manifest.get('cohort_sha256'))[:12]}"
            )
    else:
        problems.append("frozen cohort manifest is required to verify the cohort binding")

    checks = list(gate.get("acceptance_checks") or [])
    if not checks:
        problems.append("gate has no pre-declared acceptance_checks; freeze the contract before measuring")
    else:
        for check in checks:
            result = _evaluate_check(report, check)
            if not result["passed"]:
                problems.append(
                    f"acceptance check failed: {result['path']} {result['operator']} "
                    f"{result['expected']!r} (actual {result['actual']!r})"
                )
    return problems


def patch_gate_status(program_text: str, status: str) -> str:
    """Flip only the recorded status of the FPP gate, keeping formatting intact."""

    marker = f'"id": "{GATE_ID}",'
    index = program_text.find(marker)
    if index < 0:
        raise ValueError(f"gate {GATE_ID!r} not found in program.json")
    window_end = program_text.find('"required_output"', index)
    if window_end < 0:
        raise ValueError("gate entry is missing required_output; refusing to edit blind")
    window = program_text[index:window_end]
    updated_window = window
    for previous in ("pending_run", "pending_data", "measured", "pass", "blocked_by_gates"):
        needle = f'"status": "{previous}",'
        if needle in updated_window:
            updated_window = updated_window.replace(needle, f'"status": "{status}",', 1)
            break
    else:
        raise ValueError("gate entry has no parsable status field")
    if updated_window == window:
        raise ValueError(f"gate status already recorded as {status!r}; nothing to freeze")
    return program_text[:index] + updated_window + program_text[window_end:]


def freeze(args: argparse.Namespace) -> int:
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    program_text = Path(args.program).read_text(encoding="utf-8")
    program = json.loads(program_text)
    gate = next((item for item in program["gates"] if item.get("id") == GATE_ID), None)
    if gate is None:
        raise ValueError(f"{GATE_ID} gate missing from {args.program}")

    cohort_manifest = None
    cohort_path = Path(args.cohort_manifest) if args.cohort_manifest else ROOT / COHORT_MANIFEST
    if cohort_path.is_file():
        cohort_manifest = json.loads(cohort_path.read_text(encoding="utf-8"))
    ci_manifest = json.loads(Path(args.ci_manifest).read_text(encoding="utf-8")) if args.ci_manifest else None
    rows = load_rows(Path(args.rows)) if args.rows else None
    report_sha256 = sha256_file(Path(args.report))

    problems = verify(
        report,
        gate=gate,
        cohort_manifest=cohort_manifest,
        ci_manifest=ci_manifest,
        report_sha256=report_sha256,
        rows=rows,
    )
    if problems:
        print("REFUSING TO FREEZE — unresolved conditions:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(
            json.dumps(
                {
                    "would_freeze_gate": GATE_ID,
                    "gate_status_before": gate.get("status"),
                    "report_sha256": report_sha256,
                    "rows_sha256": report.get("rows_sha256"),
                    "metrics": {
                        name: {
                            "n_cases": block.get("n_cases"),
                            "brier_score": block.get("brier_score"),
                            "roc_auc": block.get("roc_auc"),
                        }
                        for name, block in (report.get("splits") or {}).items()
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    dest = Path(args.dest_dir)
    # Kanıt, kapının `required_output` yoluyla aynı dizinde durmak zorundadır;
    # aksi halde program.json "measured" der ama denetçi kanıtı bulamaz.
    required = Path(gate["required_output"])
    canonical_dest = required.parent if str(required.parent) not in ("", ".") else ROOT
    if dest.resolve() != (ROOT / canonical_dest).resolve():
        print(
            "REFUSING TO FREEZE — --dest-dir is not the gate's canonical evidence path\n"
            f"  expected: {ROOT / canonical_dest}\n"
            f"  given:    {dest}",
            file=sys.stderr,
        )
        return 2
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "report.json").write_bytes(canonical_json(report))
    written = ["report.json"]
    for label, source in (("rows.jsonl", args.rows), ("fpp_cases.json", args.cases)):
        if source:
            (dest / label).write_bytes(Path(source).read_bytes())
            written.append(label)
    evidence = {
        "schema_version": "1.0",
        "gate": GATE_ID,
        "campaign": CAMPAIGN,
        "report_sha256": sha256_file(dest / "report.json"),
        "source_report_sha256": report_sha256,
        "rows_sha256": report.get("rows_sha256"),
        "cohort_sha256": (cohort_manifest or {}).get("cohort_sha256"),
        "accepted_checks": len(gate.get("acceptance_checks") or []),
        "github_run_id": report.get("environment", {}).get("github_run_id"),
        "artifacts": written,
        "freeze_policy": (
            "Frozen by scripts/validation/freeze_fpp_calibration_evidence.py after every "
            "pre-declared acceptance check passed; no check was relaxed to achieve closure."
        ),
    }
    (dest / "evidence_manifest.json").write_bytes(canonical_json(evidence))
    Path(args.program).write_text(patch_gate_status(program_text, "measured"), encoding="utf-8")
    print(json.dumps({"frozen": True, "program": str(args.program), "evidence": evidence}, indent=2, sort_keys=True))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--report", type=Path, required=True)
    root.add_argument("--rows", type=Path)
    root.add_argument("--cases", type=Path)
    root.add_argument("--ci-manifest", type=Path)
    root.add_argument("--cohort-manifest", type=Path)
    root.add_argument("--program", type=Path, default=ROOT / "validation_runs/final_acceptance_v1/program.json")
    root.add_argument("--dest-dir", type=Path, default=ROOT / "validation_runs/final_acceptance_v1/fpp_calibration")
    root.add_argument("--dry-run", action="store_true")
    return root


def main() -> int:
    return freeze(parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
