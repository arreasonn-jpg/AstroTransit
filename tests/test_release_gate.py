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
        has_baseline_report=True, has_provenance=True,
    )
    assert report.passed
