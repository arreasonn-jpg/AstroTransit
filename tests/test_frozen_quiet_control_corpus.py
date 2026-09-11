"""Regression contract for the frozen 100-target quiet-control corpus."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

SCRIPT = Path("scripts/validation/build_quiet_controls.py")
SPEC = importlib.util.spec_from_file_location("build_quiet_controls", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)
MANIFEST = Path(
    "validation_runs/final_acceptance_v1/false_positive_controls/corpus_manifest.json"
)


def canonical_sha256(payload):
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    return hashlib.sha256(data).hexdigest()


def test_frozen_quiet_control_artifacts_rebuild_exactly():
    manifest = json.loads(MANIFEST.read_text())
    corpus, audit = MODULE.build(
        Path(manifest["sources"]["pool"]["path"]),
        Path(manifest["sources"]["labelled_corpus"]["path"]),
        Path(manifest["sources"]["prior_injection_hosts"]["path"]),
        required=manifest["required_count"],
        seed=manifest["selection"]["seed"],
    )
    assert corpus["status"] == audit["status"] == "frozen"
    assert corpus["selected_count"] == audit["selected_count"] == 100
    assert audit["eligible_count"] == manifest["eligible_count"] == 283
    assert canonical_sha256(corpus) == manifest["artifacts"][
        "quiet_controls_json_sha256"
    ]
    assert canonical_sha256(audit) == manifest["artifacts"][
        "selection_audit_json_sha256"
    ]
    assert corpus["selection"] == manifest["selection"]


def test_frozen_controls_are_unique_and_detector_independent():
    manifest = json.loads(MANIFEST.read_text())
    corpus, _ = MODULE.build(
        Path(manifest["sources"]["pool"]["path"]),
        Path(manifest["sources"]["labelled_corpus"]["path"]),
        Path(manifest["sources"]["prior_injection_hosts"]["path"]),
        required=100,
        seed=20260912,
    )
    target_ids = [case["target_id"] for case in corpus["cases"]]
    assert len(target_ids) == len(set(target_ids)) == 100
    assert corpus["selection"]["detector_used_for_selection"] is False
    assert corpus["selection"]["prior_injection_hosts_excluded"] is True
    assert all(case["label"] == "quiet_star" for case in corpus["cases"])
