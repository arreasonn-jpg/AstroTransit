"""Kapıyı kapatmanın tek izinli yolu: dondurma betiğinin reddetme davranışı.

Bu testler, FPP kalibrasyon kapısının ancak **ölçüm önceden ilan edilmiş
sözleşme geçildiğinde** `measured`'a dönebildiğini; tek bir check'in bile
bozulmasının program.json'ı byte byte değişmez bırakmasını doğrular.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pytest

import scripts.validation.freeze_fpp_calibration_evidence as freeze_module
import scripts.validation.run_fpp_calibration_campaign as campaign
from tests.test_fpp_calibration_campaign import PROGRAM, _args, _rows, _write_shards

FROZEN_MANIFEST = campaign.ROOT / campaign.COHORT_MANIFEST


def _measured_report(tmp_path: Path):
    (tmp_path / "config.toml").write_text("[general]\n", encoding="utf-8")
    rows = _rows(100, 100, fp_fpp=lambda i: 0.70 + 0.002 * i, planet_fpp=lambda i: 0.02 + 0.001 * i)
    args = _args(tmp_path, _write_shards(tmp_path, rows, shard_count=4), cohort_manifest=FROZEN_MANIFEST, min_per_label=100)
    assert campaign.aggregate(args) == 0
    return args, rows


def _program_gate() -> dict:
    program = json.loads(PROGRAM.read_text(encoding="utf-8"))
    return next(gate for gate in program["gates"] if gate["id"] == "fpp_quality_calibration")


def test_clean_report_and_hashes_pass_verification(tmp_path: Path):
    args, rows = _measured_report(tmp_path)
    report = json.loads(args.output.read_text(encoding="utf-8"))
    problems = freeze_module.verify(
        report,
        gate=_program_gate(),
        cohort_manifest=json.loads(FROZEN_MANIFEST.read_text(encoding="utf-8")),
        ci_manifest=json.loads(args.manifest.read_text(encoding="utf-8")),
        report_sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
        rows=rows,
    )
    assert problems == []


def test_verify_refuses_a_pending_or_blocking_report(tmp_path: Path):
    args, rows = _measured_report(tmp_path)
    report = json.loads(args.output.read_text(encoding="utf-8"))
    report["status"] = "pending_run"
    problems = freeze_module.verify(
        report,
        gate=_program_gate(),
        cohort_manifest=json.loads(FROZEN_MANIFEST.read_text(encoding="utf-8")),
        ci_manifest=None,
        report_sha256=None,
        rows=rows,
    )
    assert any("status" in problem for problem in problems)

    blocked = json.loads(args.output.read_text(encoding="utf-8"))
    blocked["blocking_reasons"] = ["blind_test_roc_auc_at_or_below_chance:0.4<0.5"]
    problems = freeze_module.verify(
        blocked,
        gate=_program_gate(),
        cohort_manifest=json.loads(FROZEN_MANIFEST.read_text(encoding="utf-8")),
        ci_manifest=None,
        report_sha256=None,
        rows=rows,
    )
    assert any("blocking_reasons" in problem for problem in problems)


def test_verify_refuses_tampered_rows(tmp_path: Path):
    args, rows = _measured_report(tmp_path)
    report = json.loads(args.output.read_text(encoding="utf-8"))
    tampered = [dict(row) for row in rows]
    # Bir tek FPP değerini iyileştirmek bile satır özünü bozar.
    tampered[0]["target_fpp"] = 0.999
    problems = freeze_module.verify(
        report,
        gate=_program_gate(),
        cohort_manifest=json.loads(FROZEN_MANIFEST.read_text(encoding="utf-8")),
        ci_manifest=None,
        report_sha256=None,
        rows=tampered,
    )
    assert any("rows digest mismatch" in problem for problem in problems)


def test_verify_refuses_cohort_drift_and_missing_manifest(tmp_path: Path):
    args, rows = _measured_report(tmp_path)
    report = json.loads(args.output.read_text(encoding="utf-8"))
    drifted = dict(json.loads(FROZEN_MANIFEST.read_text(encoding="utf-8")), cohort_sha256="f" * 64)
    problems = freeze_module.verify(
        report,
        gate=_program_gate(),
        cohort_manifest=drifted,
        ci_manifest=None,
        report_sha256=None,
        rows=rows,
    )
    assert any("cohort binding mismatch" in problem for problem in problems)

    problems = freeze_module.verify(
        report,
        gate=_program_gate(),
        cohort_manifest=None,
        ci_manifest=None,
        report_sha256=None,
        rows=rows,
    )
    assert any("frozen cohort manifest is required" in problem for problem in problems)


def test_verify_refuses_a_gate_without_predeclared_checks(tmp_path: Path):
    args, rows = _measured_report(tmp_path)
    report = json.loads(args.output.read_text(encoding="utf-8"))
    gate = dict(_program_gate())
    gate.pop("acceptance_checks", None)
    problems = freeze_module.verify(
        report,
        gate=gate,
        cohort_manifest=json.loads(FROZEN_MANIFEST.read_text(encoding="utf-8")),
        ci_manifest=None,
        report_sha256=None,
        rows=rows,
    )
    assert any("pre-declared acceptance_checks" in problem for problem in problems)


def test_freeze_writes_evidence_and_flips_only_the_fpp_gate(tmp_path: Path):
    args, _rows_used = _measured_report(tmp_path)
    dest = tmp_path / "validation_runs" / "fpp_calibration"
    dest.mkdir(parents=True, exist_ok=True)
    # Kanonik yolu test dizinine taşı: guard, dest-dir ile required_output'un
    # aynı dizin olmasını zorunlu kılar.
    program_text = PROGRAM.read_text(encoding="utf-8").replace(
        '"required_output": "validation_runs/final_acceptance_v1/fpp_calibration/report.json"',
        f'"required_output": "{dest / "report.json"}"',
        1,
    )
    program_copy = tmp_path / "program.json"
    program_copy.write_text(program_text, encoding="utf-8")

    freeze_args = argparse.Namespace(
        report=args.output,
        rows=args.rows_out,
        cases=args.cases_output,
        ci_manifest=args.manifest,
        cohort_manifest=FROZEN_MANIFEST,
        program=program_copy,
        dest_dir=dest,
        dry_run=False,
    )
    assert freeze_module.freeze(freeze_args) == 0

    program = json.loads(program_copy.read_text(encoding="utf-8"))
    gates = {gate["id"]: gate for gate in program["gates"]}
    assert gates["fpp_quality_calibration"]["status"] == "measured"
    assert len(gates) == 11
    assert gates["labelled_fp_quiet_controls"]["status"] == "pending_run"
    assert gates["blind_domain_holdout"]["status"] == "pending_data"
    assert gates["final_report_release"]["status"] == "blocked_by_gates"

    assert (dest / "report.json").is_file()
    assert (dest / "rows.jsonl").is_file()
    assert (dest / "fpp_cases.json").is_file()
    evidence = json.loads((dest / "evidence_manifest.json").read_text(encoding="utf-8"))
    assert evidence["gate"] == "fpp_quality_calibration"
    assert evidence["accepted_checks"] == len(_program_gate()["acceptance_checks"])
    assert evidence["cohort_sha256"] == json.loads(FROZEN_MANIFEST.read_text(encoding="utf-8"))["cohort_sha256"]
    assert hashlib.sha256((dest / "report.json").read_bytes()).hexdigest() == evidence["report_sha256"]

    # Dondurulmuş kanıt, denetçi tarafından gerçekten kapalı sayılır.
    import scripts.validation.final_acceptance_audit as audit_module

    result = audit_module.audit(program_copy)
    closed = [gate["id"] for gate in result["gates"] if gate["closed"]]
    assert closed == ["parameter_recovery", "fpp_quality_calibration"]


def test_freeze_refuses_a_noncanonical_dest_dir(tmp_path: Path):
    """Kanıt, kapının required_output dizini dışında bir yere yazılamaz."""

    args, _ = _measured_report(tmp_path)
    program_copy = tmp_path / "program.json"
    program_copy.write_text(PROGRAM.read_text(encoding="utf-8"), encoding="utf-8")
    rc = freeze_module.freeze(
        argparse.Namespace(
            report=args.output,
            rows=args.rows_out,
            cases=None,
            ci_manifest=None,
            cohort_manifest=FROZEN_MANIFEST,
            program=program_copy,
            dest_dir=tmp_path / "somewhere_else",
            dry_run=False,
        )
    )
    assert rc == 2
    assert program_copy.read_text(encoding="utf-8") == PROGRAM.read_text(encoding="utf-8")


def test_freeze_dry_run_changes_nothing(tmp_path: Path):
    args, _ = _measured_report(tmp_path)
    program_copy = tmp_path / "program.json"
    original = PROGRAM.read_text(encoding="utf-8")
    program_copy.write_text(original, encoding="utf-8")
    before = args.output.read_bytes()

    rc = freeze_module.freeze(
        argparse.Namespace(
            report=args.output,
            rows=args.rows_out,
            cases=None,
            ci_manifest=args.manifest,
            cohort_manifest=FROZEN_MANIFEST,
            program=program_copy,
            dest_dir=tmp_path / "dest",
            dry_run=True,
        )
    )
    assert rc == 0
    assert program_copy.read_text(encoding="utf-8") == original
    assert args.output.read_bytes() == before
    assert not (tmp_path / "dest").exists()


def test_freeze_refuses_and_leaves_program_untouched(tmp_path: Path):
    args, _ = _measured_report(tmp_path)
    # rows.jsonl'i rapordaki özetle uyuşmayacak şekilde boz.
    rows_path = args.rows_out
    lines = rows_path.read_text(encoding="utf-8").splitlines()
    broken = json.loads(lines[0])
    broken["target_fpp"] = 0.123
    rows_path.write_text("\n".join([json.dumps(broken), *lines[1:]]) + "\n", encoding="utf-8")

    program_copy = tmp_path / "program.json"
    original = PROGRAM.read_text(encoding="utf-8")
    program_copy.write_text(original, encoding="utf-8")

    rc = freeze_module.freeze(
        argparse.Namespace(
            report=args.output,
            rows=rows_path,
            cases=None,
            ci_manifest=None,
            cohort_manifest=FROZEN_MANIFEST,
            program=program_copy,
            dest_dir=tmp_path / "dest",
            dry_run=False,
        )
    )
    assert rc == 2
    assert program_copy.read_text(encoding="utf-8") == original
    assert not (tmp_path / "dest").exists()


def test_patch_gate_status_is_surgical():
    text = PROGRAM.read_text(encoding="utf-8")
    patched = freeze_module.patch_gate_status(text, "measured")
    assert patched.count('"status": "measured"') == text.count('"status": "measured"') + 1
    assert '"status": "pending_run"' in patched  # diğer kapılar dokunulmadı
    with pytest.raises(ValueError, match="already recorded"):
        freeze_module.patch_gate_status(patched, "measured")
    with pytest.raises(ValueError, match="not found"):
        freeze_module.patch_gate_status('{"gates": []}', "measured")


def test_smoke_run_reports_telemetry_without_writing_gate_artifacts(tmp_path: Path, monkeypatch, capsys):
    """`smoke` tek hedefte zinciri koşar; kapı yolu olan bir dosya üretmez."""

    fake_row = {
        "target_id": "TIC 17361",
        "label": "false_positive",
        "evaluated": True,
        "accepted_candidate": False,
        "error": "",
        "target_fpp_available": True,
        "target_fpp": 0.73,
        "target_fpp_availability_reason": "ok",
    }

    def _fake_evaluate_case(case, orchestrator, sector_client):
        assert case.target_id == "TIC 17361"
        return dict(fake_row)

    class _Client:
        def get_available_sectors(self, target):
            return [1]

    class _Orchestrator:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    import astrotransit.data.tess_client as tess_module
    import astrotransit.pipelines.orchestrator as orchestrator_module
    import scripts.validation.run_false_positive_controls as controls

    monkeypatch.setattr(tess_module, "TESSClient", lambda *a, **k: _Client())
    monkeypatch.setattr(orchestrator_module, "AstroTransitOrchestrator", _Orchestrator)
    monkeypatch.setattr(controls, "_evaluate_case", _fake_evaluate_case)

    config = tmp_path / "config.toml"
    config.write_text("[general]\n", encoding="utf-8")
    rc = campaign.smoke(
        argparse.Namespace(
            target_id="TIC 17361",
            label="false_positive",
            reference="",
            sectors=None,
            config=config,
            output=None,
            strict=True,
        )
    )
    assert rc == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["target_fpp"] == 0.73
    assert printed["label"] == "false_positive"
