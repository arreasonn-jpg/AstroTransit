"""Regression guard: secondary_eclipse is HARD *and* SNR-gated.

Phase 1C v2: the ratio test alone misfires on shallow transits because
secondary_eclipse_depth ~600-730 ppm is a white-noise floor. The veto
requires both the ratio crossing and secondary_eclipse_snr >= 2.0.
"""

from astrotransit.quality.vetting import HARD_FAIL_TESTS, SOFT_FAIL_TESTS


def test_secondary_eclipse_is_hard_fail():
    assert "secondary_eclipse" in HARD_FAIL_TESTS


def test_secondary_eclipse_not_in_soft():
    assert "secondary_eclipse" not in SOFT_FAIL_TESTS


def test_secondary_eclipse_snr_still_hard():
    assert "secondary_eclipse_snr" in HARD_FAIL_TESTS
