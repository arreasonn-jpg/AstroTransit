from astrotransit.validation.cross_sector import assess_cross_sector_consistency
from astrotransit.validation.metrics import interval_coverage, parameter_recovery


def _sector(period, depth, duration=.1, epoch=1.0):
    return {"period": period, "depth": depth, "duration": duration, "epoch": epoch}


def test_cross_sector_consistency_is_evidence_based():
    report = assess_cross_sector_consistency([_sector(3.0, .01), _sector(3.01, .0105)])
    assert report.multi_sector_consistent
    assert report.classification == "multi_sector_consistent"


def test_single_sector_is_not_confirmed():
    report = assess_cross_sector_consistency([_sector(3.0, .01)])
    assert report.classification == "single_sector_candidate"
    assert not report.multi_sector_consistent


def test_parameter_recovery_and_coverage_preserve_measurement_semantics():
    metric = parameter_recovery([1, 2, 3], [1.1, 1.9, 3.0])
    assert metric.n == 3
    assert metric.bias == 0.0
    assert interval_coverage([1, 2, 3], [(0.9, 1.1), (1.8, 2.2), (2.5, 2.9)]) == 2 / 3
