"""Contracts for the consolidated final-acceptance program."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path("scripts/validation/final_acceptance_audit.py")
SPEC = importlib.util.spec_from_file_location("final_acceptance_audit", SCRIPT)
AUDIT = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(AUDIT)


def test_program_has_exactly_eleven_unique_gates():
    path = Path("validation_runs/final_acceptance_v1/program.json")
    program = json.loads(path.read_text())
    ids = [gate["id"] for gate in program["gates"]]
    assert len(ids) == len(set(ids)) == 11


def test_pending_evidence_never_closes_a_gate(tmp_path):
    evidence = tmp_path / "pending.json"
    evidence.write_text('{"status":"pending_run"}')
    program = tmp_path / "program.json"
    program.write_text(json.dumps({
        "program": "test",
        "claim_policy": "pending is not a score",
        "gates": [{"id": "gate", "status": "pending_run", "required_output": str(evidence)}],
    }))
    report = AUDIT.audit(program)
    assert report["closed_gates"] == 0
    assert report["status"] == "in_progress"
