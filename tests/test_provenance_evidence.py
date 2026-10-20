"""provenance kayıt-yükü kontratı doğrulamaları (B2 düzeltmesi)."""

from __future__ import annotations

import json
from pathlib import Path

from astrotransit.validation.provenance import report_carries_provenance


def test_missing_file_is_not_provenance(tmp_path: Path):
    assert report_carries_provenance(tmp_path / "yok.json") is False


def test_plain_report_without_manifest_keys_is_rejected(tmp_path: Path):
    p = tmp_path / "plain.json"
    p.write_text(json.dumps({"status": "measured", "recall": 0.5}), encoding="utf-8")
    assert report_carries_provenance(p) is False


def test_empty_json_is_rejected(tmp_path: Path):
    p = tmp_path / "empty.json"
    p.write_text("{geçersiz", encoding="utf-8")
    assert report_carries_provenance(p) is False


def test_commit_or_hash_keys_accept(tmp_path: Path):
    p = tmp_path / "hash.json"
    p.write_text(json.dumps({"report_sha256": "a" * 64}), encoding="utf-8")
    assert report_carries_provenance(p) is True


def test_nested_evidence_manifest_accepts(tmp_path: Path):
    p = tmp_path / "nested.json"
    p.write_text(
        json.dumps({"evidence": {"cohort_sha256": "b" * 64}}),
        encoding="utf-8",
    )
    assert report_carries_provenance(p) is True


def test_non_dict_payload_rejected(tmp_path: Path):
    p = tmp_path / "list.json"
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert report_carries_provenance(p) is False
