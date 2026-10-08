"""Tests for the adversarial FP leakage taxonomy."""

from astrotransit.validation.leakage_taxonomy import (
    LEAKAGE_CATEGORIES,
    classify_leak,
    summarize_leaks,
)


def test_categories_are_stable():
    assert "LOW_TRANSIT_COUNT" in LEAKAGE_CATEGORIES
    assert "V_SHAPE" in LEAKAGE_CATEGORIES
    assert "OTHER" in LEAKAGE_CATEGORIES


def test_low_transit_count():
    row = {"n_transits": 3, "secondary_eclipse_depth_ppm": 50, "odd_even_mismatch": 0.5}
    cat, reasons = classify_leak(row)
    assert cat == "LOW_TRANSIT_COUNT"
    assert any("n_transits" in r for r in reasons)


def test_v_shape():
    row = {"n_transits": 15, "steepness": 1.0}
    cat, _ = classify_leak(row)
    assert cat == "V_SHAPE"


def test_harmonic():
    row = {"harmonic_confusion": True}
    cat, _ = classify_leak(row)
    assert cat == "HARMONIC_CONFUSION"


def test_blending():
    row = {"n_transits": 15, "dilution": 0.3, "steepness": 0.5}
    cat, _ = classify_leak(row)
    assert cat == "BLENDING"


def test_summarize():
    rows = [
        {"outcome": "leaked_as_candidate", "n_transits": 3, "family": "f1",
         "secondary_eclipse_depth_ppm": 50, "odd_even_mismatch": 0.5},
        {"outcome": "leaked_as_candidate", "n_transits": 15, "steepness": 1.0, "family": "f2"},
        {"outcome": "rejected_at_vetting", "family": "f1"},
    ]
    summary = summarize_leaks(rows)
    assert summary["total"] == 2
    assert summary["by_category"]["LOW_TRANSIT_COUNT"] == 1
    assert summary["by_category"]["V_SHAPE"] == 1
    assert summary["by_family"]["f1"] == 1
    assert summary["by_family"]["f2"] == 1


def test_no_leaks():
    summary = summarize_leaks([{"outcome": "rejected_at_vetting"}])
    assert summary["total"] == 0
    assert summary["by_category"] == {}
