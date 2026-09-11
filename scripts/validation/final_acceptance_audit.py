#!/usr/bin/env python3
"""Audit the consolidated final-validation program without inventing evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

CLOSED = {"measured", "pass"}
_MISSING = object()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _lookup(payload: dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _evaluate_check(payload: dict[str, Any], check: dict[str, Any]) -> dict[str, Any]:
    path = str(check["path"])
    operator = str(check["operator"])
    expected = check.get("value")
    actual = _lookup(payload, path)
    passed = False
    if actual is not _MISSING:
        if operator == "equals":
            passed = actual == expected
        elif operator == "gte":
            passed = isinstance(actual, (int, float)) and actual >= expected
        elif operator == "lte":
            passed = isinstance(actual, (int, float)) and actual <= expected
        else:
            raise ValueError(f"Unsupported acceptance operator: {operator}")
    return {
        "path": path,
        "operator": operator,
        "expected": expected,
        "actual": None if actual is _MISSING else actual,
        "passed": passed,
    }


def audit(program_path: Path) -> dict[str, object]:
    program = json.loads(program_path.read_text(encoding="utf-8"))
    gates = []
    for gate in program["gates"]:
        output = Path(gate["required_output"])
        recorded = dict(gate)
        recorded["evidence_exists"] = output.is_file()
        recorded["evidence_sha256"] = sha256(output) if output.is_file() else None
        evidence: dict[str, Any] = {}
        if output.is_file():
            try:
                evidence = json.loads(output.read_text(encoding="utf-8"))
                evidence_status = str(evidence.get("status", "unknown")).lower()
            except (OSError, json.JSONDecodeError):
                evidence_status = "invalid"
        else:
            evidence_status = "missing"
        checks = gate.get("acceptance_checks", [])
        results = [_evaluate_check(evidence, check) for check in checks]
        if not checks:
            acceptance_status = "contract_missing"
        elif all(result["passed"] for result in results):
            acceptance_status = "pass"
        else:
            acceptance_status = "fail"
        recorded["evidence_status"] = evidence_status
        recorded["acceptance_status"] = acceptance_status
        recorded["acceptance_results"] = results
        recorded["closed"] = (
            str(gate.get("status", "")).lower() in CLOSED
            and evidence_status in CLOSED
            and acceptance_status == "pass"
        )
        gates.append(recorded)
    closed = sum(bool(gate["closed"]) for gate in gates)
    return {
        "schema_version": "1.1",
        "program": program["program"],
        "status": "complete" if closed == len(gates) else "in_progress",
        "closed_gates": closed,
        "total_gates": len(gates),
        "gates": gates,
        "claim_boundary": program["claim_policy"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--program", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    report = audit(args.program)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if args.require_complete and report["status"] != "complete":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
