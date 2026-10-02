"""Adversarial FP corpus'u, sınıflandırması ve rapor sözleşmesinin testleri.

Bu testler ölçüm **sonucunu** değil, ölçüm **aletini** doğrular: sentetik
eclipse morfolojisi ilan edildiği yerde/derinlikte olmalı, kademeli red
sınıflaması yanlış sınıfa düşmemeli ve rapor bloke edici koşulları görmeli.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from astrotransit.validation.adversarial_fp import (
    ADVERSARIAL_FAMILIES,
    CADENCE_DAYS,
    REJECTION_OUTCOMES,
    AdversarialScenario,
    build_adversarial_report,
    classify_outcome,
    grid_sha256,
    synthetic_lightcurve,
    wilson_interval,
)
from scripts.validation.run_adversarial_fp_controls import (
    CORPUS_MANIFEST,
    ROOT as PROJECT_ROOT,
    build_grid,
    corpus_payload,
)

ROOT = Path(CORPUS_MANIFEST)


def _scenario(**overrides) -> AdversarialScenario:
    base = {
        "family": "eclipsing_binary_v",
        "index": 0,
        "seed": 7,
        "period_days": 2.0,
        "depth": 0.02,
        "duration_days": 0.12,
        "t0_days": 0.7,
        "noise_ppm": 1.0,  # neredeyse gürültüsüz: şekil testi için
    }
    base.update(overrides)
    return AdversarialScenario(**base)


def _depth_at(time: np.ndarray, flux: np.ndarray, instant: float, half_width: float) -> float:
    """``instant`` civarındaki minimumun baseline'dan farkı (pozitif derinlik)."""

    window = np.abs(time - instant) <= half_width
    if not window.any():
        return 0.0
    return float(np.median(flux[~window]) - np.min(flux[window]))


# ---------------------------------------------------------------- ızgara


def test_grid_is_deterministic_and_hash_stable() -> None:
    first, second = build_grid(), build_grid()
    assert grid_sha256(first) == grid_sha256(second)
    assert len(first) == 8 * len(ADVERSARIAL_FAMILIES)
    assert len({scenario.scenario_id for scenario in first}) == len(first)


def test_every_scenario_validates_and_carries_expected_label() -> None:
    for scenario in build_grid():
        scenario.validate()
        expected = "planet" if scenario.family == "planetary_control" else "false_positive"
        assert scenario.expected == expected
        assert 0.0 < scenario.depth * scenario.dilution <= 0.5


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"depth": 0.9}, "depth"),
        ({"period_days": 40.0}, "period_days"),
        ({"duration_days": 1.5}, "duration"),
        ({"steepness": 0.0}, "steepness"),
        ({"dilution": 1.5}, "dilution"),
        ({"secondary_fraction": 1.0}, "secondary_fraction"),
        ({"noise_ppm": 0.0}, "noise_ppm"),
    ],
)
def test_invalid_scenario_definitions_raise(overrides: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _scenario(**overrides).validate()


def test_unknown_family_is_rejected() -> None:
    with pytest.raises(ValueError, match="bilinmeyen adversarial aile"):
        AdversarialScenario(
            family="not_a_family", index=0, seed=1, period_days=1.0, depth=0.01, duration_days=0.1
        ).validate()


# ------------------------------------------------------ üretecin doğrulanması


def test_transit_lands_at_declared_epoch_and_depth() -> None:
    scenario = _scenario(steepness=0.05)
    time, flux, flux_err = synthetic_lightcurve(scenario)
    half_width = 0.5 * scenario.duration_days
    depth = _depth_at(time, flux, scenario.t0_days, half_width)
    assert depth == pytest.approx(scenario.depth, rel=0.15)
    assert np.all(flux_err > 0)


def test_secondary_eclipse_sits_at_half_period_not_on_primary() -> None:
    """Regresyon testi: ikincil, birincilin üstüne binmemeli (faz hatası)."""

    scenario = _scenario(secondary_fraction=0.5, steepness=0.05)
    time, flux, _ = synthetic_lightcurve(scenario)
    half_width = 0.5 * scenario.duration_days
    primary = _depth_at(time, flux, scenario.t0_days, half_width)
    secondary = _depth_at(time, flux, scenario.t0_days + 0.5 * scenario.period_days, half_width)
    assert primary == pytest.approx(scenario.depth, rel=0.15)
    assert secondary == pytest.approx(0.5 * scenario.depth, rel=0.2)
    assert secondary < 0.8 * primary  # aynı yerde değil


def test_alternation_depths_follow_declared_ratio() -> None:
    scenario = _scenario(alternate_ratio=0.4, steepness=0.05)
    time, flux, _ = synthetic_lightcurve(scenario)
    half_width = 0.5 * scenario.duration_days
    depths = [
        _depth_at(time, flux, scenario.t0_days + n * scenario.period_days, half_width) for n in range(1, 6)
    ]
    even, odd = depths[0], depths[1]
    assert min(even, odd) / max(even, odd) == pytest.approx(0.4, abs=0.25)
    assert max(even, odd) > 1.5 * min(even, odd)


def test_steepness_changes_shape_not_center_depth() -> None:
    """Aile sözü: steepness V/kutu arasını seçer, merkez derinliğini değiştirmez."""

    areas = {}
    for steepness in (1.0, 0.05):
        scenario = _scenario(steepness=steepness, noise_ppm=1e-3)
        time, flux, _ = synthetic_lightcurve(scenario)
        centre_index = int(round(scenario.t0_days / CADENCE_DAYS))
        assert 1.0 - float(flux[centre_index]) == pytest.approx(scenario.depth, rel=0.05)
        areas[steepness] = float(np.sum(1.0 - flux))
    # Üçgen (V) altındaki alan, kutununkinin yaklaşık yarısı kadardır.
    assert areas[1.0] < 0.7 * areas[0.05]


def test_dilution_scales_observed_depth_only() -> None:
    undiluted = synthetic_lightcurve(_scenario(dilution=1.0))
    diluted = synthetic_lightcurve(_scenario(dilution=0.1))
    time, flux, _ = diluted
    depth = _depth_at(time, flux, 0.7, 0.5 * 0.12)
    assert depth == pytest.approx(0.1 * 0.02, rel=0.3)
    assert undiluted[1].shape == flux.shape


def test_seed_controls_noise_reproducibility() -> None:
    a = synthetic_lightcurve(_scenario(seed=11))[1]
    b = synthetic_lightcurve(_scenario(seed=11))[1]
    c = synthetic_lightcurve(_scenario(seed=12))[1]
    np.testing.assert_array_equal(a, b)
    assert not np.array_equal(a, c)
    assert float(np.max(np.abs(a - c))) > 0.0


def test_variability_family_actually_modulates_flux() -> None:
    scenario = _scenario(variability_amplitude=0.004, variability_period_days=9.0, depth=0.0001)
    time, flux, _ = synthetic_lightcurve(scenario)
    outside = np.abs(np.mod(time - scenario.t0_days + 1.0, scenario.period_days) - 1.0) > 0.4
    assert float(np.std(flux[outside])) > 1e-3


# ------------------------------------------------------------ sınıflandırma


def _fake_candidate(*, has=True, confirmed=True, status="confirmed"):
    return SimpleNamespace(
        has_candidate=has,
        confirmed=confirmed,
        status=SimpleNamespace(value=status),
        period=2.0,
        depth=0.02,
        detected_period=2.0,
    )


def _fake_quality(
    *,
    is_fp=False,
    fpp=None,
    flags=(),
    anomaly_flag="",
    anomaly_score=None,
    n_severe=0,
    candidate_class="B",
    secondary_ppm=0.0,
):
    vetting = SimpleNamespace(
        is_false_positive=is_fp,
        false_positive_probability=fpp,
        fpp_method="heuristic_vetting_vote_v1",
        fp_flags=list(flags),
        n_fail=1 if is_fp else 0,
        n_warn=0,
    )
    metrics = SimpleNamespace(
        transit=SimpleNamespace(odd_even_mismatch=0.05, depth_variance=0.02, transit_symmetry=0.99),
        stellar=SimpleNamespace(secondary_eclipse_depth=secondary_ppm * 1e-6, variability_amplitude=100.0),
    )
    return SimpleNamespace(
        vetting=vetting,
        metrics=metrics,
        score=SimpleNamespace(quality_score=80.0, candidate_class=candidate_class),
        anomaly=SimpleNamespace(anomaly_flag=anomaly_flag, anomaly_score=anomaly_score, n_severe=n_severe),
        anomaly_residual=None,
        anomaly_transit=None,
        anomaly_timing=None,
    )


def test_missing_bls_peak_counts_as_detection_stage_rejection() -> None:
    result = classify_outcome(_fake_candidate(has=False, status="bls_failed"), None)
    assert result["outcome"] == "rejected_at_detection"
    assert result["cascade_status"] == "bls_failed"


def test_none_candidate_is_detection_rejection_not_error() -> None:
    assert classify_outcome(None, None)["outcome"] == "rejected_at_detection"


def test_unconfirmed_candidate_is_cascade_stage_rejection() -> None:
    result = classify_outcome(_fake_candidate(confirmed=False, status="period_mismatch"), None)
    assert result["outcome"] == "rejected_at_cascade"


def test_vetting_fp_flag_is_vetting_stage_rejection() -> None:
    result = classify_outcome(
        _fake_candidate(),
        _fake_quality(is_fp=True, fpp=0.77, flags=["secondary_eclipse"]),
        reject_threshold=0.5,
    )
    assert result["outcome"] == "rejected_at_vetting"
    assert result["fpp"] == 0.77
    assert result["fp_flags"] == ["secondary_eclipse"]


def test_fpp_at_threshold_rejects_and_is_inclusive() -> None:
    at_threshold = classify_outcome(_fake_candidate(), _fake_quality(fpp=0.5), reject_threshold=0.5)
    below = classify_outcome(_fake_candidate(), _fake_quality(fpp=0.4999), reject_threshold=0.5)
    assert at_threshold["outcome"] == "rejected_at_vetting"
    assert below["outcome"] == "leaked_as_candidate"


def test_unknown_fpp_is_never_read_as_rejection() -> None:
    """FPP None ise 'sıfır risk' de 'risk' de sayılmaz; veto yoksa sızar."""

    result = classify_outcome(_fake_candidate(), _fake_quality(fpp=None, is_fp=False))
    assert result["outcome"] == "leaked_as_candidate"
    assert result["fpp"] is None


def test_missing_vetting_block_does_not_claim_rejection() -> None:
    no_vetting = SimpleNamespace(vetting=None, metrics=None, score=None, anomaly=None)
    assert classify_outcome(_fake_candidate(), no_vetting)["outcome"] == "leaked_as_candidate"


def test_anomaly_reject_flag_is_separate_stage() -> None:
    result = classify_outcome(
        _fake_candidate(),
        _fake_quality(fpp=0.1, anomaly_flag="REJECT", anomaly_score=0.72, n_severe=2),
    )
    assert result["outcome"] == "rejected_at_anomaly"
    assert result["anomaly_flags"] == {"combined": "REJECT"}
    assert result["anomaly_n_severe"] == 2
    assert result["candidate_class"] == "B"
    assert result["secondary_eclipse_depth_ppm"] == 0.0


def test_vetting_rejection_wins_over_anomaly_for_reporting() -> None:
    result = classify_outcome(
        _fake_candidate(), _fake_quality(is_fp=True, fpp=0.9, anomaly_flag="REJECT", anomaly_score=0.8)
    )
    assert result["outcome"] == "rejected_at_vetting"


def test_diagnostics_are_carried_for_leaks_too() -> None:
    result = classify_outcome(_fake_candidate(), _fake_quality(fpp=0.0, secondary_ppm=1792.3))
    assert result["outcome"] == "leaked_as_candidate"
    assert result["secondary_eclipse_depth_ppm"] == 1792.3
    assert result["odd_even_mismatch"] == 0.05


# ------------------------------------------------------------------- rapor


def _rows(**overrides) -> list[dict]:
    rows = []
    for family in ADVERSARIAL_FAMILIES:
        expected = ADVERSARIAL_FAMILIES[family]["expected"]
        for index in range(8):
            rows.append(
                {
                    "scenario_id": f"{family}:{index:03d}",
                    "family": family,
                    "expected": expected,
                    "outcome": "leaked_as_candidate" if expected == "planet" else "rejected_at_vetting",
                    "fpp": 0.0 if expected == "planet" else 0.8,
                    "cascade_status": "confirmed",
                    **overrides,
                }
            )
    return rows


def test_report_uses_declared_floors_and_wilson_intervals() -> None:
    report = build_adversarial_report(_rows(), scenarios=None)
    assert report["status"] == "measured"
    assert report["blocking_reasons"] == []
    overall = report["overall"]
    assert overall["adversarial_scenarios"] == 48
    assert overall["adversarial_rejection_rate"] == 1.0
    assert overall["control_acceptance_rate"] == 1.0
    assert overall["adversarial_rejected_by_stage"] == {"rejected_at_vetting": 48}
    low = report["families"]["eclipsing_binary_v"]["wilson_interval_95"]
    assert 0.6 < low[0] < 1.0 and low[1] == 1.0  # n=8: aralık geniş olmalı


def test_error_rows_block_and_are_counted() -> None:
    rows = _rows()
    rows[0]["outcome"] = "error"
    report = build_adversarial_report(rows)
    assert report["status"] == "pending_run"
    assert "error_rows:1" in report["blocking_reasons"]
    assert report["families"]["eclipsing_binary_v"]["n_error"] == 1


def test_leaking_family_below_floor_blocks_the_gate() -> None:
    rows = _rows()
    for row in rows:
        if row["family"] == "blended_diluted_eb":
            row["outcome"] = "leaked_as_candidate"
    report = build_adversarial_report(rows, minimum_rejection_rate=0.99)
    assert report["status"] == "pending_run"
    assert any(reason.startswith("overall_rejection_below_declared_floor") for reason in report["blocking_reasons"])


def test_a_family_that_always_leaks_is_named_in_blockers() -> None:
    rows = _rows()
    for row in rows:
        if row["family"] == "spot_modulated_dip":
            row["outcome"] = "leaked_as_candidate"
    report = build_adversarial_report(rows)
    assert any(
        reason.startswith("family_rejection_below_floor:spot_modulated_dip")
        for reason in report["blocking_reasons"]
    )


def test_control_family_is_mandatory() -> None:
    """Kontrol ailesi yoksa 'her şeyi reddet' ayarı metriği geçemez."""

    rows = [row for row in _rows() if row["family"] != "planetary_control"]
    report = build_adversarial_report(rows)
    assert report["status"] == "pending_run"
    assert "no_positive_control_family" in report["blocking_reasons"]


def test_leaking_control_blocks_even_with_perfect_rejection() -> None:
    rows = _rows()
    for row in rows:
        if row["family"] == "planetary_control":
            row["outcome"] = "rejected_at_vetting"
    report = build_adversarial_report(rows)
    assert report["status"] == "pending_run"
    assert any(
        reason.startswith("positive_control_acceptance_below_floor") for reason in report["blocking_reasons"]
    )


def test_missing_and_undersampled_families_are_named() -> None:
    """Korpusun bir ailesi hiç çalışmadıysa kapı kapalı kalmalıdır."""

    rows = [row for row in _rows() if row["family"] != "grazing_eclipsing_binary"]
    report = build_adversarial_report(rows)
    assert "family_missing_from_run:grazing_eclipsing_binary" in report["blocking_reasons"]
    assert report["corpus"]["families_missing_from_run"] == ["grazing_eclipsing_binary"]
    thin = [row for row in _rows() if row["family"] != "grazing_eclipsing_binary" or int(row["scenario_id"][-3:]) < 2]
    thin_report = build_adversarial_report(thin)
    assert any(reason.startswith("family_below_minimum:") for reason in thin_report["blocking_reasons"])


def test_empty_rows_and_unknown_family_raise() -> None:
    with pytest.raises(ValueError, match="en az bir"):
        build_adversarial_report([])
    with pytest.raises(ValueError, match="bilinmeyen adversarial aile"):
        build_adversarial_report([{"family": "mystery", "outcome": "leaked_as_candidate"}])


def test_rejection_outcome_labels_are_consistent_with_report() -> None:
    rows = _rows()
    for row in rows:
        row["outcome"] = "rejected_at_anomaly"
    report = build_adversarial_report(rows)
    assert report["overall"]["adversarial_rejection_rate"] == 1.0
    assert set(REJECTION_OUTCOMES) >= {
        "rejected_at_detection",
        "rejected_at_cascade",
        "rejected_at_vetting",
        "rejected_at_anomaly",
    }


# ------------------------------------------------------------ yardımcıları


def test_wilson_interval_semantics() -> None:
    assert wilson_interval(0, 0) is None
    low, high = wilson_interval(1, 1)
    assert 0.0 < low < 1.0 and high == 1.0
    assert wilson_interval(1, 2)[0] < 0.5 < wilson_interval(1, 2)[1]


# ------------------------------------------------- donmuş korpus sözleşmesi


def test_committed_corpus_manifest_matches_rebuilt_grid() -> None:
    assert ROOT.is_file(), "frozen corpus manifest must be committed with the contract"
    manifest = json.loads(ROOT.read_text(encoding="utf-8"))
    rebuilt = build_grid()
    assert manifest["grid_sha256"] == grid_sha256(rebuilt)
    assert manifest["n_scenarios"] == len(rebuilt)
    assert manifest["status"] == "frozen"
    assert manifest["materialization"] == "deterministic_rebuild_from_frozen_grid"
    assert manifest["counts"] == {family: 8 for family in sorted(ADVERSARIAL_FAMILIES)}
    assert manifest["design"]["families"]["planetary_control"]["expected"] == "planet"
    assert "Synthetic" in manifest["claim_boundary"]
    assert len(manifest["cases"]) == manifest["n_scenarios"]
    assert [case["scenario_id"] for case in manifest["cases"]] == [s.scenario_id for s in rebuilt]
    assert manifest["cases"] == [s.to_dict() for s in rebuilt]


def test_case_payloads_are_canonical_and_round_trip() -> None:
    scenarios = build_grid()
    payload = corpus_payload(scenarios)
    assert grid_sha256(scenarios) == payload["grid_sha256"]
    canonical = json.dumps(payload["cases"], sort_keys=True, separators=(",", ":"))
    first = payload["cases"][0]
    assert json.loads(canonical)[0]["observed_depth_ppm"] == pytest.approx(
        first["depth_ppm"] * first["dilution"], rel=1e-6
    )


def test_program_json_declares_the_gate_contract() -> None:
    program = json.loads((PROJECT_ROOT / "validation_runs/final_acceptance_v1/program.json").read_text())
    gate = next(item for item in program["gates"] if item.get("id") == "adversarial_false_positives")
    checks = {item["path"]: item for item in gate["acceptance_checks"]}
    assert gate["status"] == "pending_run"
    assert checks["corpus.grid_sha256"]["value"] == grid_sha256(build_grid())
    assert checks["overall.adversarial_rejection_rate"] == {"path": "overall.adversarial_rejection_rate", "operator": "gte", "value": 0.8}
    assert checks["overall.control_acceptance_rate"]["value"] == 0.5
    assert checks["overall.total_errors"]["value"] == 0
    for family in ADVERSARIAL_FAMILIES:
        if ADVERSARIAL_FAMILIES[family]["expected"] == "false_positive":
            assert checks[f"families.{family}.rejection_rate"]["operator"] == "gte"
    # Rapor, esikleri kendi icinde de tasiyacak ki sonradan kaydirilamasin.
    report = build_adversarial_report(_rows())
    assert report["status"] == "measured"
    assert report["method"]["declared_floor_rejection_rate"] == checks["overall.adversarial_rejection_rate"]["value"]
    assert report["method"]["declared_floor_control_acceptance"] == checks["overall.control_acceptance_rate"]["value"]
    assert report["method"]["declared_floor_per_family_rejection_rate"] == 0.5
    assert report["method"]["fpp_reject_threshold"] == checks["method.fpp_reject_threshold"]["value"]
    assert report["method"]["data"] == "synthetic"
    assert report["method"]["missing_fpp_treatment"] == checks["method.missing_fpp_treatment"]["value"]
    assert report["campaign"] == checks["campaign"]["value"]
