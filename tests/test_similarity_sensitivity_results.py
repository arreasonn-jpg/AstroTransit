"""Contract test for the frozen Gate-7 similarity-sensitivity result.

The report file (``benchmarks/results/similarity_sensitivity_v1.json``) is a
measured, immutable artifact produced by
``scripts/validation/run_similarity_sensitivity.py``. This test does not
re-run the (expensive) experiment; it enforces the scientific contract: the
verdicts in the report must be consistent with the stated tau rule, the
provenance block must be complete, and candidate counts must be coherent.
"""
from __future__ import annotations

import json
from pathlib import Path

REPORT_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "results" / "similarity_sensitivity_v1.json"

REQUIRED_PROFILE_KEYS = (
    "perturbation_fraction",
    "overall_verdict",
    "baseline_top_k",
    "input_limitations",
)
REQUIRED_CELL_KEYS = (
    "n_candidates",
    "n_perturbations",
    "kendall_tau_min",
    "kendall_tau_median",
    "top_k_overlap_min",
    "verdict",
)
REQUIRED_PROVENANCE_KEYS = (
    "git_commit",
    "pipeline_version",
    "input_hash",
    "config_hash",
    "report_hash",
)


def _load_report() -> dict:
    assert REPORT_PATH.is_file(), (
        "Gate-7 measured result missing; run "
        "`python scripts/validation/run_similarity_sensitivity.py` to (re)generate it."
    )
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def test_frozen_result_reports_measured_tau_consistent_with_rule():
    report = _load_report()
    assert report["report_id"] == "similarity_sensitivity_v1"
    assert report["input"]["n_candidates_used"] > 1
    assert report["input"]["n_candidates_used"] <= report["input"]["n_rows_total"]
    threshold = float(report["tau_stability_threshold"])
    for profile, block in report["profiles"].items():
        for key in REQUIRED_PROFILE_KEYS:
            assert key in block, f"{profile}: missing '{key}'"
        stable = True
        for fraction, cell in block["perturbation_fraction"].items():
            for key in REQUIRED_CELL_KEYS:
                assert key in cell, f"{profile} ±{fraction}: missing '{key}'"
            tau_min = cell["kendall_tau_min"]
            assert tau_min is not None and -1.0 <= tau_min <= 1.0
            assert 0.0 <= cell["top_k_overlap_min"] <= 1.0
            expected_verdict = "ranking_stable" if tau_min >= float(threshold) else "weight_sensitive"
            assert cell["verdict"] == expected_verdict, (
                f"{profile} ±{fraction}: verdict {cell['verdict']} contradicts tau rule "
                f"(tau_min={tau_min}, threshold={threshold})"
            )
            assert cell["n_candidates"] == report["input"]["n_candidates_used"]
            stable &= cell["verdict"] == "ranking_stable"
        assert block["overall_verdict"] == ("ranking_stable" if stable else "weight_sensitive")


def test_frozen_result_carries_complete_provenance():
    report = _load_report()
    provenance = report["provenance"]
    for key in REQUIRED_PROVENANCE_KEYS:
        assert provenance.get(key), f"provenance missing non-empty '{key}'"
    assert len(provenance["input_hash"]) == 64
    assert len(provenance["report_hash"]) == 64
    assert provenance["input_hash"] == report["input"]["sha256"]


def test_frozen_result_declares_scope_and_input_limitations():
    report = _load_report()
    # The strict profile is evaluated on a mass-less catalog: the limitation
    # must stay visible in the frozen report rather than being silently dropped.
    assert any(
        "mass" in note for note in report["profiles"]["strict_earth_twin"]["input_limitations"]
    )
    assert "not a" in report["scope_note"] or "not" in report["scope_note"]
