"""Contract test for the known-planet ground truth (Gate 2 input).

``benchmarks/verified_targets.json`` is the ground-truth corpus consumed by
``astrotransit benchmark``. The release-acceptance gate requires >=50
labelled targets; entries are ground truth, never performance claims.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from astrotransit.validation.benchmark_report import load_verified_targets

GROUND_TRUTH = Path(__file__).resolve().parents[1] / "benchmarks" / "verified_targets.json"
LEGACY_TICS = {
    "100100827",  # WASP-18b
    "25155310",  # WASP-126b
    "38846515",  # TOI-125b
    "279741379",  # WASP-100b
    "281541555",  # HATS-24b
    "29857954",  # TOI-402.01
    "219338557",  # TOI-561b
    "142090065",  # WASP-19b
    "183985250",  # WASP-77Ab
}


def test_ground_truth_meets_gate_size_and_contract():
    specs = load_verified_targets(GROUND_TRUTH)
    assert len(specs) >= 50, "release-acceptance gate requires >=50 labelled targets"
    tics = [spec.tic_id for spec in specs]
    assert len(tics) == len(set(tics)), "duplicate tic_id in ground truth"
    for spec in specs:
        assert spec.expected_period_days > 0
        if spec.expected_radius_rearth is not None:
            assert spec.expected_radius_rearth > 0
        assert spec.difficulty in {"easy", "medium", "hard"}


def test_legacy_entries_are_preserved():
    payload = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    rows = payload["targets"] if isinstance(payload, dict) else payload
    by_tic = {str(row["tic_id"]): row for row in rows}
    assert LEGACY_TICS <= set(by_tic), "legacy hand-curated targets must stay in the corpus"
    assert by_tic["100100827"]["name"] == "WASP-18b"


def test_catalog_derived_entries_cite_the_independent_source():
    payload = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    rows = payload["targets"] if isinstance(payload, dict) else payload
    derived = [row for row in rows if str(row["tic_id"]) not in LEGACY_TICS]
    assert derived, "expansion produced no new targets"
    for row in derived:
        assert "TESS FOP Working Group disposition" in row.get("reference", ""), (
            "catalog-derived ground truth must cite its independent label source"
        )
        assert 0.3 <= row["period"] <= 30.0, "new entries must stay inside the BLS search range"
    # Round-robin stratification: the set must not collapse onto a single tier.
    tiers = Counter(row["difficulty"] for row in derived)
    assert len(tiers) >= 2, f"difficulty stratification lost; tiers={dict(tiers)}"
