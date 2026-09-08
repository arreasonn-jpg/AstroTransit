from astrotransit.validation.baselines import compare_baselines
from astrotransit.validation.determinism import assert_deterministic
from astrotransit.validation.failures import FailureCode, classify_failure
from astrotransit.validation.performance import measure_runtime


def test_baselines_use_same_cases_and_report_delta():
    cases = [{"label": "planet"}, {"label": "quiet_star"}]
    report = compare_baselines(cases, {
        "astrotransit": lambda case: case["label"] == "planet",
        "tls-only": lambda case: True,
    })
    assert report.delta("recall", "astrotransit", "tls-only") == 0
    assert report.measurements[1].false_positive_rate == 0.5


def test_failure_taxonomy_is_structured():
    codes = classify_failure({"n_points": 0, "mcmc_quality": "MCMC_FAILED_DIAGNOSTICS"})
    assert FailureCode.NO_DATA in codes
    assert FailureCode.MCMC_DIAGNOSTIC_FAILURE in codes


def test_deterministic_hash_ignores_timestamps_only():
    first = {"value": 1, "created_at": "a"}
    second = {"value": 1, "created_at": "b"}
    assert len(assert_deterministic(first, second)) == 64


def test_runtime_measurement_has_per_target_cost():
    result = measure_runtime("noop", lambda: None, n_targets=2)
    assert result.seconds >= 0
    assert result.seconds_per_target is not None
