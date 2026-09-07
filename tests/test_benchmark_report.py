"""Known-target benchmark raporunun ground-truth/ölçüm ayrımı testleri."""

from types import SimpleNamespace

import pytest

from astrotransit.validation.benchmark_report import (
    VerifiedTarget,
    evaluate_benchmark_results,
    load_verified_targets,
)


def _result(target_id: str, periods: list[float], radii: list[float]):
    sectors = [
        SimpleNamespace(
            sector=index + 1,
            candidate_confirmed=True,
            candidate=SimpleNamespace(period=period),
            fit_result=SimpleNamespace(
                derived=SimpleNamespace(planet_radius_rearth=radius),
                planet_radius_rearth=radius,
            ),
            record=SimpleNamespace(period=period, planet_radius_rearth=radius),
        )
        for index, (period, radius) in enumerate(zip(periods, radii))
    ]
    return SimpleNamespace(
        target_id=target_id,
        candidates_confirmed=len(sectors),
        sector_results=sectors,
    )


def test_known_target_report_contains_expected_and_recovered_parameters() -> None:
    target = VerifiedTarget(
        tic_id="123",
        name="Example b",
        expected_period_days=3.0,
        expected_radius_rearth=2.0,
        difficulty="medium",
    )
    report = evaluate_benchmark_results(
        [target],
        [_result("TIC 123", [3.003, 3.004], [2.02, 1.98])],
    )

    measurement = report.targets[0]
    assert measurement.detected is True
    assert measurement.correct is True
    assert measurement.sector_consistent is True
    assert report.metrics["detection_recall"] == pytest.approx(1.0)
    assert report.metrics["false_positive_rejection"] is None


def test_missing_pipeline_result_is_not_reported_as_zero_recovery() -> None:
    target = VerifiedTarget("123", "Example b", 3.0, 2.0, "hard")
    report = evaluate_benchmark_results([target], [])

    measurement = report.targets[0]
    assert measurement.detected is False
    assert measurement.recovered_period_days is None
    assert measurement.recovered_radius_rearth is None
    assert report.metrics["period_recovery_error_median_fraction"] is None
    assert report.metrics["radius_recovery_error_median_fraction"] is None


def test_verified_target_json_is_loadable() -> None:
    targets = load_verified_targets("benchmarks/verified_targets.json")
    assert targets
    assert targets[0].target_id.startswith("TIC ")
    assert targets[0].expected_period_days > 0
