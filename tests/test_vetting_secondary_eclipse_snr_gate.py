"""Regression guard: secondary_eclipse is HARD *and* SNR-gated; the SNR test
is corroboration-only (FAZ 2b.5, blind-recall Bulgu 1).

Phase 1C v2: the ratio test alone misfires on shallow transits because
secondary_eclipse_depth ~600-730 ppm is a white-noise floor. The veto
requires both the ratio crossing and secondary_eclipse_snr >= 2.0.

FAZ 2b.5: ``secondary_eclipse_snr`` was removed from the solo HARD_FAIL set —
a single-sector SNR crossing (1.5 < SNR) fires on real planets too. The veto
now requires corroboration between the two secondary-eclipse tests.
"""

from astrotransit.quality.vetting import (
    HARD_FAIL_TESTS,
    SECONDARY_CORROBORATION_TESTS,
    SOFT_FAIL_TESTS,
)


def test_secondary_eclipse_is_hard_fail():
    assert "secondary_eclipse" in HARD_FAIL_TESTS


def test_secondary_eclipse_not_in_soft():
    assert "secondary_eclipse" not in SOFT_FAIL_TESTS


def test_secondary_eclipse_snr_not_solo_hard():
    """FAZ 2b.5: solo SNR FAIL must not veto (recall fix)."""
    assert "secondary_eclipse_snr" not in HARD_FAIL_TESTS


def test_secondary_pair_in_corroboration_set():
    assert SECONDARY_CORROBORATION_TESTS == frozenset(
        {"secondary_eclipse", "secondary_eclipse_snr"}
    )
