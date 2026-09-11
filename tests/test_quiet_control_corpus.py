"""Contracts for the independent quiet-control corpus builder."""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path("scripts/validation/build_quiet_controls.py")
SPEC = importlib.util.spec_from_file_location("build_quiet_controls", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_current_sources_produce_one_hundred_independent_controls():
    payload, audit = MODULE.build(
        Path("benchmarks/discovery_targets_v4_small_cool_1000_dedup.csv"),
        Path("benchmarks/corpora/tfop_disposition_corpus_v1.json"),
        Path("validation_runs/v1_injection_recovery/real_noise_v1/input/quiet_hosts.json"),
        required=100,
        seed=20260912,
    )
    assert payload["status"] == audit["status"] == "frozen"
    assert payload["selected_count"] == audit["selected_count"] == 100
    assert len(payload["cases"]) == 100
    assert len({case["target_id"] for case in payload["cases"]}) == 100
    assert payload["selection"]["detector_used_for_selection"] is False
    assert payload["selection"]["prior_injection_hosts_excluded"] is True
    labelled = MODULE.load_ids(
        Path("benchmarks/corpora/tfop_disposition_corpus_v1.json")
    )
    prior_hosts = MODULE.load_ids(
        Path("validation_runs/v1_injection_recovery/real_noise_v1/input/quiet_hosts.json")
    )
    selected = {MODULE.tic_number(case["target_id"]) for case in payload["cases"]}
    assert selected.isdisjoint(labelled)
    assert selected.isdisjoint(prior_hosts)
    assert all(case["label"] == "quiet_star" for case in payload["cases"])
    assert all(len(case["sectors"]) == 2 for case in payload["cases"])


def test_seeded_selection_is_deterministic():
    args = (
        Path("benchmarks/discovery_targets_v4_small_cool_1000_dedup.csv"),
        Path("benchmarks/corpora/tfop_disposition_corpus_v1.json"),
        Path("validation_runs/v1_injection_recovery/real_noise_v1/input/quiet_hosts.json"),
    )
    first, first_audit = MODULE.build(*args, required=100, seed=20260912)
    second, second_audit = MODULE.build(*args, required=100, seed=20260912)
    assert first == second
    assert first_audit == second_audit
