"""FPP'nin bilinmeyeni sıfır risk olarak göstermediğini doğrular."""

from astrotransit.quality.fpp.beb_test import BEBScenarioEvaluator
from astrotransit.quality.fpp.calculator import SimpleFPPCalculator
from astrotransit.quality.fpp.eb_test import EBScenarioEvaluator
from astrotransit.quality.fpp.neb_test import NEBScenarioEvaluator
from astrotransit.quality.fpp.report import FPPReportWriter
from astrotransit.validation.fpp_benchmark import evaluate_fpp_benchmark


def test_missing_scenario_evidence_is_not_zero_fpp() -> None:
    report = SimpleFPPCalculator().calculate(target_id="TIC 1", sector=1)
    assert report.fpp is None
    assert report.p_planet is None
    assert report.to_dict()["fpp"] is None
    assert "not_available" in FPPReportWriter().render_text(report)


def test_empty_scenario_reports_are_not_zero_risk() -> None:
    reports = [
        EBScenarioEvaluator().evaluate(target_id="TIC 1", sector=1),
        BEBScenarioEvaluator().evaluate(target_id="TIC 1", sector=1),
        NEBScenarioEvaluator().evaluate(target_id="TIC 1", sector=1),
    ]
    assert all(report.n_available == 0 for report in reports)
    assert all(report.to_dict()[key] is None for report, key in zip(
        reports, ("p_eb", "p_beb", "p_neb")
    ))


def test_empty_calibration_set_is_not_a_zero_score() -> None:
    report = evaluate_fpp_benchmark([])
    assert report.brier_score is None
    assert report.false_positive_recall is None
    assert report.planet_precision is None
