"""validation/robustness kapı kontrat testleri.

``detrending_cadence_impact_robustness`` kapısı (program.json'da
contract_missing) için ölçüm+kapı sözleşmesi — detector ve pertürbasyonlar
injektif kalır, pipeline'dan bağımsızdır.
"""

from __future__ import annotations

import pytest

from astrotransit.validation.robustness import (
    evaluate_cadence_robustness_gate,
    measure_cadence_robustness,
)


def _cases(n: int) -> list[dict]:
    return [{"target_id": f"TIC-{i}", "label": "planet"} for i in range(n)]


def test_measurement_reduces_to_recall_math():
    cases = _cases(4)
    campaign = measure_cadence_robustness(
        cases,
        detector=lambda case: int(case["target_id"].split("-")[1]) % 2 == 0,
        perturbations={"cadence_half": lambda case: dict(case)},
    )
    assert campaign.baseline.detected == 2
    assert campaign.baseline.recall == 0.5
    assert campaign.measurements[0].recall == 0.5
    assert campaign.max_recall_drop == 0.0


def test_recall_drop_zero_for_invariant_perturbation():
    cases = [
        {"target_id": "strong-1", "snr": 40.0},
        {"target_id": "strong-2", "snr": 12.0},
        {"target_id": "weak-1", "snr": 7.0},
        {"target_id": "weak-2", "snr": 6.5},
    ]

    def detector(case) -> bool:
        # Pertürbasyon yoksa SNR eşiği 5.0 etkin; hafif ~%10 kayıp
        # pertürbasyon ayrımı almaz: invariant kontrol.
        return case.get("snr", 0) >= 5.0

    def perturb_half(case):
        degraded = dict(case)
        degraded["snr"] = case["snr"] * 0.9  # hafif kayıp
        return degraded

    campaign = measure_cadence_robustness(
        cases, detector, {"cadence_x0.9": perturb_half}
    )
    assert campaign.baseline.recall == 1.0
    assert campaign.max_recall_drop == pytest.approx(0.0)


def test_gate_pass_declared_floor_and_pending_below_floor():
    cases = _cases(120)

    def detector(case) -> bool:
        return True

    def perturb(case):
        return dict(case)

    campaign = measure_cadence_robustness(cases, detector, {"cadence_50": perturb})
    gate = evaluate_cadence_robustness_gate(campaign, min_cases=100, declared_max_recall_drop=0.05)
    assert gate.status == "measured"
    assert gate.blocking_reasons == ()


def test_gate_fails_on_excess_recall_drop():
    cases = _cases(20)

    def detector(case) -> bool:
        return not case.get("degraded", False)

    def perturb(case):
        perturbed = dict(case)
        perturbed["degraded"] = True
        return perturbed

    campaign = measure_cadence_robustness(cases, detector, {"cadence_worst": perturb})
    gate = evaluate_cadence_robustness_gate(
        campaign, min_cases=10, declared_max_recall_drop=0.05
    )
    assert gate.status == "measured_fail"
    assert gate.blocking_reasons and "exceeds declared floor" in gate.blocking_reasons[0]


def test_gate_pending_without_campaign_or_below_floor():
    gate = evaluate_cadence_robustness_gate(None, min_cases=100)
    assert gate.status == "pending_run"
    assert gate.blocking_reasons

    cases = _cases(9)
    campaign = measure_cadence_robustness(cases, lambda case: True, {"p": lambda case: dict(case)})
    gate2 = evaluate_cadence_robustness_gate(campaign, min_cases=100)
    assert gate2.status == "pending_run"


def test_measure_rejects_empty_cases():
    with pytest.raises(ValueError, match="cases boş"):
        measure_cadence_robustness([], lambda case: True, {"p": lambda case: dict(case)})


def test_to_dict_roundtrip_keys():
    cases = _cases(5)
    campaign = measure_cadence_robustness(cases, lambda case: True, {"p": lambda case: dict(case)})
    payload = campaign.to_dict()
    assert set(payload) == {"baseline", "measurements", "max_recall_drop"}
    gate = evaluate_cadence_robustness_gate(campaign, min_cases=5).to_dict()
    assert set(gate) == {
        "campaign", "min_cases", "declared_max_recall_drop", "status", "blocking_reasons",
    }
