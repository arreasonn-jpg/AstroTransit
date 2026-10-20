"""`astrotransit reproduce --verify` evidans doğrulama testleri."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from typer.testing import CliRunner

from cli.main import _verify_evidence_manifest, app


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_reproduce_manifest_roundtrip(tmp_path: Path):
    output = tmp_path / "report_out.json"
    output.write_text('{"a": 1}', encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"output_path": str(output), "output_hash": _sha(output)}),
        encoding="utf-8",
    )
    verification = _verify_evidence_manifest(manifest, lambda p: _sha(Path(p).resolve()))
    assert verification["ok"] is True
    assert verification["checks"][0]["match"] is True


def test_report_rows_hashes_verified(tmp_path: Path):
    report = tmp_path / "report.json"
    report.write_text('{"gate": "x"}', encoding="utf-8")
    rows = tmp_path / "rows.jsonl"
    rows.write_text('{"row": 1}\n', encoding="utf-8")
    manifest = tmp_path / "evidence_manifest.json"
    manifest.write_text(
        json.dumps({"report_sha256": _sha(report), "rows_sha256": _sha(rows)}),
        encoding="utf-8",
    )
    verification = _verify_evidence_manifest(manifest, lambda p: _sha(Path(p).resolve()))
    assert verification["ok"] is True
    assert len(verification["checks"]) == 2


def test_mismatch_fails_and_missing_files_fail(tmp_path: Path):
    report = tmp_path / "report.json"
    report.write_text('{"gate": "x"}', encoding="utf-8")
    manifest = tmp_path / "evidence_manifest.json"
    manifest.write_text(
        json.dumps({"report_sha256": "0" * 64, "rows_sha256": "1" * 64}),
        encoding="utf-8",
    )
    verification = _verify_evidence_manifest(manifest, lambda p: _sha(Path(p).resolve()))
    assert verification["ok"] is False
    statuses = [c["match"] for c in verification["checks"]]
    assert statuses == [False, False]  # report hash uyuşmaz, rows dosyası yok


def test_no_hashable_fields_rejected(tmp_path: Path):
    manifest = tmp_path / "plain.json"
    manifest.write_text(json.dumps({"status": "measured"}), encoding="utf-8")
    verification = _verify_evidence_manifest(manifest, _sha)
    assert verification["ok"] is False
    assert "hash" in verification["error"]


def test_cli_reproduce_verify_invocation(tmp_path: Path):
    output = tmp_path / "report_out.json"
    output.write_text('{"a": 1}', encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"output_path": str(output), "output_hash": _sha(output)}),
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(app, ["reproduce", "--verify", str(manifest)])
    assert result.exit_code == 0


def test_cli_reproduce_verify_failure_exits_1(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"report_sha256": "0" * 64}), encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["reproduce", "--verify", str(manifest)])
    assert result.exit_code == 1


def test_cli_reproduce_without_dataset_or_verify_exits_2():
    runner = CliRunner()
    result = runner.invoke(app, ["reproduce"])
    assert result.exit_code == 2
