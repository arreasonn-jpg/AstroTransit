"""
ArchitectureAnomalyScorer birim testleri.

Kapsam
------
- _bound0_100: None, NaN, inf, negatif, >100, normal
- _ttv_score: tum esik bantlari + n_transits<3 ozel dal
- _asymmetry_score: symmetry, ratio, ikisi birlikte
- _residual_score: rms bantlari, anomaly_flag REJECT/REVIEW
- evaluate(): lagrange turetme vs explicit, tum flag dallari
"""

from __future__ import annotations

import math

import pytest

from astrotransit.quality.architecture_anomalies import (
    ArchitectureAnomalyScorer,
    ArchitectureAssessment,
)


@pytest.fixture
def scorer() -> ArchitectureAnomalyScorer:
    return ArchitectureAnomalyScorer()


# ─────────────────────────────────────────────────────────────
# _bound0_100
# ─────────────────────────────────────────────────────────────

def test_bound_none(scorer) -> None:
    assert scorer._bound0_100(None) == 0.0


def test_bound_nonconvertible(scorer) -> None:
    assert scorer._bound0_100("abc") == 0.0  # type: ignore[arg-type]


def test_bound_nan(scorer) -> None:
    assert scorer._bound0_100(float("nan")) == 0.0


def test_bound_inf(scorer) -> None:
    assert scorer._bound0_100(float("inf")) == 0.0
    assert scorer._bound0_100(float("-inf")) == 0.0


def test_bound_negative(scorer) -> None:
    assert scorer._bound0_100(-5.0) == 0.0


def test_bound_above_100(scorer) -> None:
    assert scorer._bound0_100(150.0) == 100.0


def test_bound_normal(scorer) -> None:
    assert scorer._bound0_100(42.5) == pytest.approx(42.5)
    assert scorer._bound0_100(0.0) == 0.0
    assert scorer._bound0_100(100.0) == 100.0


# ─────────────────────────────────────────────────────────────
# _ttv_score
# ─────────────────────────────────────────────────────────────

def test_ttv_none(scorer) -> None:
    assert scorer._ttv_score(None, 10) == 0.0


def test_ttv_nonpositive(scorer) -> None:
    assert scorer._ttv_score(0.0, 10) == 0.0
    assert scorer._ttv_score(-1.0, 10) == 0.0


def test_ttv_low_transits_high_rms(scorer) -> None:
    """n_transits<3 ve rms>10 → 20."""
    assert scorer._ttv_score(15.0, 2) == 20.0


def test_ttv_low_transits_low_rms(scorer) -> None:
    """n_transits<3 ve rms<=10 → 0."""
    assert scorer._ttv_score(5.0, 2) == 0.0


def test_ttv_very_tight(scorer) -> None:
    assert scorer._ttv_score(3.0, 10) == 0.0


def test_ttv_small(scorer) -> None:
    assert scorer._ttv_score(10.0, 10) == 25.0


def test_ttv_moderate(scorer) -> None:
    assert scorer._ttv_score(20.0, 10) == 55.0


def test_ttv_large(scorer) -> None:
    assert scorer._ttv_score(45.0, 10) == 80.0


def test_ttv_extreme(scorer) -> None:
    assert scorer._ttv_score(80.0, 10) == 100.0


def test_ttv_none_n_transits(scorer) -> None:
    """n_transits None → normal bant."""
    assert scorer._ttv_score(20.0, None) == 55.0


# ─────────────────────────────────────────────────────────────
# _asymmetry_score
# ─────────────────────────────────────────────────────────────

def test_asym_both_none(scorer) -> None:
    assert scorer._asymmetry_score(None, None) == 0.0


def test_asym_symmetry_only(scorer) -> None:
    """Symmetric transit (symmetry=1.0) → 0 skor."""
    assert scorer._asymmetry_score(1.0, None) == 0.0


def test_asym_symmetry_degraded(scorer) -> None:
    """symmetry=0.5 → (1-0.5)*120 = 60."""
    s = scorer._asymmetry_score(0.5, None)
    assert s == pytest.approx(60.0)


def test_asym_symmetry_negative(scorer) -> None:
    """symmetry=0 → 120 clip 100."""
    s = scorer._asymmetry_score(0.0, None)
    assert s == 0.0  # 0 kabul edilmez (<=0)


def test_asym_ratio_only(scorer) -> None:
    """ratio=1.0 → |log(1)|=0."""
    assert scorer._asymmetry_score(None, 1.0) == 0.0


def test_asym_ratio_large(scorer) -> None:
    """ratio=2.0 → |log(2)|*90 ≈ 62.4."""
    s = scorer._asymmetry_score(None, 2.0)
    assert 0.0 < s <= 100.0
    assert s == pytest.approx(abs(math.log(2.0)) * 90.0, rel=1e-6)


def test_asym_ratio_extreme_clips(scorer) -> None:
    """ratio=e^2 → 2*90=180 clip 100."""
    s = scorer._asymmetry_score(None, math.e ** 2)
    assert s == 100.0


def test_asym_ratio_nonpositive(scorer) -> None:
    assert scorer._asymmetry_score(None, 0.0) == 0.0
    assert scorer._asymmetry_score(None, -1.0) == 0.0


def test_asym_both_combined(scorer) -> None:
    """Ikisi birlikte → ortalama."""
    s = scorer._asymmetry_score(0.5, 2.0)
    expected = (60.0 + abs(math.log(2.0)) * 90.0) / 2.0
    assert s == pytest.approx(expected, rel=1e-6)


# ─────────────────────────────────────────────────────────────
# _residual_score
# ─────────────────────────────────────────────────────────────

def test_resid_both_none(scorer) -> None:
    assert scorer._residual_score(None, None) == 0.0


def test_resid_low(scorer) -> None:
    """rms <= 200 → 0."""
    assert scorer._residual_score(150.0, None) == 0.0


def test_resid_moderate(scorer) -> None:
    """200 < rms <= 500 → 20."""
    assert scorer._residual_score(300.0, None) == 20.0


def test_resid_high(scorer) -> None:
    """500 < rms <= 1000 → 40."""
    assert scorer._residual_score(700.0, None) == 40.0


def test_resid_very_high(scorer) -> None:
    """rms > 1000 → 70."""
    assert scorer._residual_score(2000.0, None) == 70.0


def test_resid_nonpositive(scorer) -> None:
    assert scorer._residual_score(0.0, None) == 0.0
    assert scorer._residual_score(-100.0, None) == 0.0


def test_resid_flag_reject(scorer) -> None:
    assert scorer._residual_score(None, "REJECT") == 50.0


def test_resid_flag_review(scorer) -> None:
    assert scorer._residual_score(None, "REVIEW") == 25.0


def test_resid_flag_case_insensitive(scorer) -> None:
    assert scorer._residual_score(None, "reject") == 50.0


def test_resid_flag_unknown(scorer) -> None:
    assert scorer._residual_score(None, "OTHER") == 0.0


def test_resid_takes_max(scorer) -> None:
    """rms=2000 (70) + REJECT (50) → max 70."""
    assert scorer._residual_score(2000.0, "REJECT") == 70.0


# ─────────────────────────────────────────────────────────────
# evaluate() — temel akis
# ─────────────────────────────────────────────────────────────

def test_evaluate_no_inputs(scorer) -> None:
    result = scorer.evaluate()
    assert isinstance(result, ArchitectureAssessment)
    assert result.architecture_flag == "NONE"
    assert result.summary_label == "STANDARD_ARCHITECTURE"
    assert result.architecture_anomaly_score == 0.0


def test_evaluate_quiet_planet(scorer) -> None:
    """Tum dusuk skorlar → STANDARD."""
    result = scorer.evaluate(
        timing_rms_min=2.0,
        transit_symmetry=1.0,
        ingress_egress_ratio=1.0,
        residual_rms_ppm=50.0,
        n_transits=10,
    )
    assert result.architecture_flag == "NONE"
    assert result.summary_label == "STANDARD_ARCHITECTURE"


def test_evaluate_review_worthy(scorer) -> None:
    """Orta skorlar → REVIEW_WORTHY."""
    result = scorer.evaluate(
        timing_rms_min=20.0,             # ttv=55
        transit_symmetry=0.7,            # asym ~36
        residual_rms_ppm=600.0,          # resid=40
        pre_post_dip_score=60.0,
        shoulder_score=50.0,
        folded_multipeak_score=40.0,
        trojan_signal_score=50.0,
        exomoon_signal_score=40.0,
    )
    # ~45-70 arasi bekleniyor
    assert result.architecture_anomaly_score >= 45
    assert result.architecture_flag in {"ARCHITECTURE_REVIEW", "ARCHITECTURE_ANOMALY"}
    assert result.summary_label in {"REVIEW_WORTHY_ARCHITECTURE", "EXOTIC_ARCHITECTURE"}


def test_evaluate_exotic_architecture(scorer) -> None:
    """Cok yuksek skorlar → EXOTIC_ARCHITECTURE (lagrange dusuk)."""
    result = scorer.evaluate(
        timing_rms_min=80.0,             # ttv=100
        transit_symmetry=0.3,            # asym=84
        ingress_egress_ratio=2.5,
        residual_rms_ppm=1500.0,         # resid=70
        pre_post_dip_score=90.0,
        shoulder_score=90.0,
        folded_multipeak_score=90.0,
        trojan_signal_score=50.0,        # lagrange dusuk kalsin
        exomoon_signal_score=90.0,
    )
    assert result.architecture_anomaly_score >= 70
    # lagrange yuksek olabilir ama trojan dusuk → 70 altinda kalmali
    assert result.architecture_flag in {"ARCHITECTURE_ANOMALY", "UNSTABLE_COORBITAL_REVIEW"}


def test_evaluate_stationkeeping_review_via_trojan(scorer) -> None:
    """Yuksek trojan → lagrange>=70 → STATIONKEEPING_REVIEW."""
    result = scorer.evaluate(
        trojan_signal_score=100.0,
        pre_post_dip_score=100.0,
        shoulder_score=100.0,
        folded_multipeak_score=100.0,
        timing_rms_min=80.0,
    )
    # lagrange = 0.45*100 + 0.20*100 + 0.15*100 + 0.10*100 + 0.10*100 = 100
    assert result.lagrange_stationkeeping_review_score >= 70
    assert result.architecture_flag == "UNSTABLE_COORBITAL_REVIEW"
    assert result.summary_label == "STATIONKEEPING_REVIEW"


def test_evaluate_lagrange_derived_when_none(scorer) -> None:
    """lagrange explicit verilmediginde turetilmis olmali."""
    result = scorer.evaluate(
        trojan_signal_score=50.0,
        pre_post_dip_score=50.0,
        shoulder_score=50.0,
        folded_multipeak_score=50.0,
        timing_rms_min=20.0,   # ttv=55
    )
    expected = 0.45 * 50.0 + 0.20 * 50.0 + 0.15 * 50.0 + 0.10 * 50.0 + 0.10 * 55.0
    assert result.lagrange_stationkeeping_review_score == pytest.approx(expected, rel=1e-6)


def test_evaluate_lagrange_explicit_override(scorer) -> None:
    """Explicit lagrange verilirse turetme atlanmali."""
    result = scorer.evaluate(
        trojan_signal_score=100.0,
        lagrange_stationkeeping_review_score=30.0,
    )
    assert result.lagrange_stationkeeping_review_score == 30.0
    # 30 < 70 → flag lagrange yuzunden STATIONKEEPING olmamali
    assert result.architecture_flag != "UNSTABLE_COORBITAL_REVIEW"


def test_evaluate_lagrange_explicit_clipped(scorer) -> None:
    """Explicit lagrange 0-100 arasina kirpilmali."""
    result = scorer.evaluate(lagrange_stationkeeping_review_score=250.0)
    assert result.lagrange_stationkeeping_review_score == 100.0
    assert result.architecture_flag == "UNSTABLE_COORBITAL_REVIEW"


def test_evaluate_lagrange_explicit_negative(scorer) -> None:
    result = scorer.evaluate(lagrange_stationkeeping_review_score=-10.0)
    assert result.lagrange_stationkeeping_review_score == 0.0


def test_evaluate_score_decomposition(scorer) -> None:
    """architecture_anomaly_score agirlikli ortalama olmali."""
    result = scorer.evaluate(
        timing_rms_min=20.0,
        transit_symmetry=0.7,
        residual_rms_ppm=600.0,
        pre_post_dip_score=60.0,
        shoulder_score=50.0,
        folded_multipeak_score=40.0,
        trojan_signal_score=50.0,
        exomoon_signal_score=40.0,
    )
    expected = (
        0.22 * result.ttv_score
        + 0.16 * result.asymmetry_score
        + 0.10 * result.residual_structure_score
        + 0.12 * result.pre_post_dip_score
        + 0.10 * result.shoulder_score
        + 0.10 * result.folded_multipeak_score
        + 0.10 * result.trojan_signal_score
        + 0.10 * result.exomoon_signal_score
    )
    expected_clipped = float(min(max(expected, 0.0), 100.0))
    assert result.architecture_anomaly_score == pytest.approx(expected_clipped, rel=1e-6)


def test_evaluate_individual_scores_clipped(scorer) -> None:
    """Disaridan verilen 0-100 disi skorlar kirpilmali."""
    result = scorer.evaluate(
        pre_post_dip_score=150.0,
        shoulder_score=-10.0,
        folded_multipeak_score=200.0,
        trojan_signal_score=-5.0,
        exomoon_signal_score=999.0,
    )
    assert result.pre_post_dip_score == 100.0
    assert result.shoulder_score == 0.0
    assert result.folded_multipeak_score == 100.0
    assert result.trojan_signal_score == 0.0
    assert result.exomoon_signal_score == 100.0


def test_evaluate_assessment_to_dict(scorer) -> None:
    result = scorer.evaluate(timing_rms_min=20.0, pre_post_dip_score=50.0)
    d = result.to_dict()
    assert isinstance(d, dict)
    assert "architecture_anomaly_score" in d
    assert "architecture_flag" in d
    assert "summary_label" in d
    assert d["architecture_anomaly_score"] == round(d["architecture_anomaly_score"], 4)
    # Tum skor alanlari float ve 4 hane
    for key in ("ttv_score", "asymmetry_score", "residual_structure_score"):
        assert isinstance(d[key], float)


def test_evaluate_partial_inputs(scorer) -> None:
    """Sadece bazi girdiler verilse de hata vermemeli."""
    result = scorer.evaluate(timing_rms_min=25.0)
    assert result.ttv_score == 55.0
    assert result.asymmetry_score == 0.0
    assert result.residual_structure_score == 0.0


def test_evaluate_logger_init() -> None:
    s2 = ArchitectureAnomalyScorer()
    assert s2 is not None
