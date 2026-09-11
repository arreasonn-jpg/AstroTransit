"""Scientific contracts for real-noise injection-recovery v1."""
from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

CONTRACT_PATH = Path("validation_runs/v1_injection_recovery/real_noise_v1/contract.json")
EXPECTED_GRID_HASH = "a741396df50d6340bb73b4b09c874b32d08b149c8eb67ebe0799853a656ebb21"


def _contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_grid_identity_and_trial_count_are_frozen() -> None:
    contract = _contract()
    axes = contract["grid"]["axes"]
    rows = []
    for period, depth, duration, phase in itertools.product(
        axes["period_days"], axes["depth_ppm"], axes["duration_days"], axes["phase_fraction"]
    ):
        rows.append({
            "period_days": period,
            "depth": depth / 1e6,
            "depth_ppm": depth,
            "duration_days": duration,
            "phase_fraction": phase,
            "period_bin": "short" if period < 5 else ("mid" if period <= 20 else "long"),
            "execution_lane": "cascade_single_sector" if period <= 20 else "long_period_stitched",
        })
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(canonical).hexdigest() == EXPECTED_GRID_HASH
    assert contract["grid"]["scenarios_per_host"] == len(rows) == 96
    assert contract["grid"]["planned_total_trials"] == 960
    assert contract["host_corpus"]["required_host_count"] == 10


def test_period_bins_and_execution_lanes_do_not_overlap() -> None:
    contract = _contract()
    bins = contract["period_bins"]
    assert bins["short"]["periods_days"] == [0.75, 2.0]
    assert bins["mid"]["periods_days"] == [5.0, 10.0, 20.0]
    assert bins["long"]["periods_days"] == [50.0]
    lanes = contract["execution_lanes"]
    cascade = set(lanes["cascade_single_sector"]["periods_days"])
    long_period = set(lanes["long_period_stitched"]["periods_days"])
    assert not cascade & long_period
    assert cascade | long_period == set(contract["grid"]["axes"]["period_days"])


def test_pending_data_cannot_be_presented_as_completeness() -> None:
    contract = _contract()
    assert contract["status"] == "pending_data"
    assert contract["host_corpus"]["status"] == "pending_data"
    assert contract["injection_stage"] == "post_detrending_real_residual"
    assert contract["claim_scope"] == "detection_stage_completeness_on_selected_real_noise_hosts"
    assert contract["recovery_contract"]["primary_metric"] == "strict_period_recovery"
    assert contract["recovery_contract"]["secondary_metric"] == "harmonic_aware_period_recovery"
    boundaries = " ".join(contract["claim_boundaries"])
    assert "No numeric completeness claim" in boundaries
    assert "PENDING DATA and PENDING RUN are not numeric scores" in boundaries


def test_quiet_host_shortcuts_are_forbidden() -> None:
    host = _contract()["host_corpus"]
    forbidden = set(host["forbidden_substitutions"])
    assert "synthetic_white_noise" in forbidden
    assert "known_planet_host_without_transit_masking" in forbidden
    assert "unknown_as_quiet_control" in forbidden
    assert "no_pipeline_candidate_before_injection" in host["selection_requirements"]
