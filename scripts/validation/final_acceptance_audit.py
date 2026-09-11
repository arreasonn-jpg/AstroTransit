#!/usr/bin/env python3
"""Audit the consolidated final-validation program without inventing evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

CLOSED = {"measured", "pass"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(program_path: Path) -> dict[str, object]:
    program = json.loads(program_path.read_text(encoding="utf-8"))
    gates = []
    for gate in program["gates"]:
        output = Path(gate["required_output"])
        recorded = dict(gate)
        recorded["evidence_exists"] = output.is_file()
        recorded["evidence_sha256"] = sha256(output) if output.is_file() else None
        if output.is_file():
            try:
                evidence = json.loads(output.read_text(encoding="utf-8"))
                evidence_status = str(evidence.get("status", "unknown")).lower()
            except (OSError, json.JSONDecodeError):
                evidence_status = "invalid"
            recorded["evidence_status"] = evidence_status
            recorded["closed"] = evidence_status in CLOSED
        else:
            recorded["evidence_status"] = "missing"
            recorded["closed"] = False
        gates.append(recorded)
    closed = sum(bool(gate["closed"]) for gate in gates)
    return {
        "schema_version": "1.0",
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
