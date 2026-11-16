from astrotransit.validation.release_gate import evaluate_release_gates


def test_release_gate_does_not_pass_without_corpus():
    report = evaluate_release_gates(known_targets=9, false_positives=0, quiet_controls=0)
    assert not report.passed
    assert report.gates[0].status == "PENDING_DATA"
    assert report.gates[-1].status == "PENDING_RUN"


def test_release_gate_requires_all_evidence():
    report = evaluate_release_gates(
        known_targets=50, false_positives=100, quiet_controls=100,
        has_injection_report=True, has_blind_report=True,
        has_baseline_report=True, has_robustness_report=True,
        has_provenance=True,
        l1_pool={"targets": []},
    )
    assert report.passed


def test_release_gate_pending_without_robustness_evidence():
    report = evaluate_release_gates(
        known_targets=50, false_positives=100, quiet_controls=100,
        has_injection_report=True, has_blind_report=True,
        has_baseline_report=True, has_provenance=True,
    )
    assert not report.passed
    robustness_gate = next(gate for gate in report.gates if gate.name == "cadence_robustness")
    assert robustness_gate.status == "PENDING_RUN"


def test_l1_claim_gate_pending_without_pool():
    report = evaluate_release_gates(
        known_targets=50, false_positives=100, quiet_controls=100,
        has_injection_report=True, has_blind_report=True,
        has_baseline_report=True, has_robustness_report=True,
        has_provenance=True,
    )
    l1_gate = next(gate for gate in report.gates if gate.name == "l1_claim_firewall")
    assert l1_gate.status == "PENDING_RUN"
    assert not report.passed


def test_l1_claim_gate_passes_with_consistent_pool():
    pool = {"targets": [
        {"target_id": "TIC 1", "l1_assessed": True, "l1_claim_label": "L1_REGION_ASSESSED"},
        {"target_id": "TIC 2", "l1_assessed": False, "l1_claim_label": None},
    ]}
    report = evaluate_release_gates(
        known_targets=50, false_positives=100, quiet_controls=100,
        has_injection_report=True, has_blind_report=True,
        has_baseline_report=True, has_robustness_report=True,
        has_provenance=True, l1_pool=pool,
    )
    l1_gate = next(gate for gate in report.gates if gate.name == "l1_claim_firewall")
    assert l1_gate.status == "PASS"
    assert report.passed


def test_l1_claim_gate_fails_on_inconsistent_label():
    pool = {"targets": [
        {"target_id": "TIC 1", "l1_assessed": True, "l1_claim_label": "L1_CONTROLLED_STRUCTURE_CANDIDATE"},
    ]}
    report = evaluate_release_gates(
        known_targets=50, false_positives=100, quiet_controls=100,
        has_injection_report=True, has_blind_report=True,
        has_baseline_report=True, has_robustness_report=True,
        has_provenance=True, l1_pool=pool,
    )
    l1_gate = next(gate for gate in report.gates if gate.name == "l1_claim_firewall")
    assert l1_gate.status == "FAIL"
    assert not report.passed
