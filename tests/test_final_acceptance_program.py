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
    evidence.write_text('{"status":"pending_run","n":100}')
    program = tmp_path / "program.json"
    program.write_text(json.dumps({
        "program": "test",
        "claim_policy": "pending is not a score",
        "gates": [{
            "id": "gate",
            "status": "pending_run",
            "required_output": str(evidence),
            "acceptance_checks": [{"path": "n", "operator": "gte", "value": 100}],
        }],
    }))
    report = AUDIT.audit(program)
    assert report["closed_gates"] == 0
    assert report["status"] == "in_progress"


def test_measured_evidence_without_acceptance_contract_never_closes(tmp_path):
    evidence = tmp_path / "measured.json"
    evidence.write_text('{"status":"measured"}')
    program = tmp_path / "program.json"
    program.write_text(json.dumps({
        "program": "test",
        "claim_policy": "explicit acceptance required",
        "gates": [{
            "id": "gate",
            "status": "measured",
            "required_output": str(evidence),
        }],
    }))
    gate = AUDIT.audit(program)["gates"][0]
    assert gate["acceptance_status"] == "contract_missing"
    assert gate["closed"] is False


def test_measured_evidence_closes_only_when_all_checks_pass(tmp_path):
    evidence = tmp_path / "measured.json"
    evidence.write_text('{"status":"measured","counts":{"negative":100}}')
    program = tmp_path / "program.json"
    program.write_text(json.dumps({
        "program": "test",
        "claim_policy": "explicit acceptance required",
        "gates": [{
            "id": "gate",
            "status": "measured",
            "required_output": str(evidence),
            "acceptance_checks": [
                {"path": "counts.negative", "operator": "gte", "value": 100},
            ],
        }],
    }))
    report = AUDIT.audit(program)
    assert report["closed_gates"] == 1
    assert report["status"] == "complete"


def test_current_program_closes_only_parameter_recovery():
    report = AUDIT.audit(Path("validation_runs/final_acceptance_v1/program.json"))
    assert report["closed_gates"] == 1
    closed_ids = [gate["id"] for gate in report["gates"] if gate["closed"]]
    assert closed_ids == ["parameter_recovery"]
