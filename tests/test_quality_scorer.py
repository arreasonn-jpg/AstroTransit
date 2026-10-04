"""
CandidateScorer ve ilgili dataclass birim testleri.

Kapsam
------
- CandidateClass / CLASS_DESCRIPTIONS
- ScoreComponent.to_dict
- QualityScore.to_dict / summary
- CandidateScorer.score: cesitli skor seviyeleri, FP, anomali
- _assign_class: X/FP/A/B/C/D
- _compute_transit_quality_score
- _compute_vetting_score
- _detect_anomaly
- _compute_period_relative_diff / _compute_period_consistency_score
- _compute_physical_consistency_score
- _normalize_linear / _normalize_linear_inverse
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from astrotransit.detection.cascade import CascadeStatus
from astrotransit.quality.metrics import (
    PhotometricMetrics,
    QualityMetrics,
    StellarMetrics,
    TransitMetrics,
)
from astrotransit.quality.scorer import (
    CLASS_DESCRIPTIONS,
    CandidateClass,
    CandidateScorer,
    QualityScore,
    ScoreComponent,
)
from astrotransit.quality.snr import SNRBreakdown
from astrotransit.quality.vetting import (
    FPP_METHOD,
    VettingReport,
    VettingTest,
    VettingVerdict,
)

# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

def _candidate(
    target: str = "TIC-100",
    sector: int = 1,
    confirmed: bool = True,
    period: float = 5.0,
    duration: float = 0.15,
    depth: float = 0.005,
    rp_rs: float = 0.08,
    status: CascadeStatus = CascadeStatus.CONFIRMED,
    bls_result=None,
    tls_result=None,
):
    """Test aday nesnesi uretir.

    Default olarak bls_result ve tls_result MagicMock olur; testler bunlar
    uzerinde attribute atayabilir. None verilirse testlerin atama yapmasi
    AttributeError uretir; bu nedenle None yerine MagicMock kullaniyoruz.
    """
    if bls_result is None:
        bls_result = MagicMock()
        bls_result.best = MagicMock(period=5.0, snr=15.0)
    if tls_result is None:
        tls_result = MagicMock(period=5.0, sde=9.0)

    return MagicMock(
        target_id=target,
        sector=sector,
        confirmed=confirmed,
        period=period,
        duration=duration,
        depth=depth,
        rp_rs=rp_rs,
        status=status,
        bls_result=bls_result,
        tls_result=tls_result,
    )


def _metrics(
    snr: float = 12.0,
    data_completeness: float = 0.95,
    transit_symmetry: float = 0.9,
    odd_even_mismatch: float = 0.5,
    n_transits: int = 4,
    residual_rms: float = 5e-4,
    timing_rms: float = 0.0,
    ls_peak: float = 0.0,
    ls_period: float = 0.0,
) -> QualityMetrics:
    return QualityMetrics(
        target_id="TIC-100",
        sector=1,
        photometric=PhotometricMetrics(
            data_completeness=data_completeness,
            n_points=1000,
        ),
        transit=TransitMetrics(
            snr=snr,
            transit_symmetry=transit_symmetry,
            odd_even_mismatch=odd_even_mismatch,
            n_transits=n_transits,
            residual_rms=residual_rms,
            timing_rms=timing_rms,
        ),
        stellar=StellarMetrics(
            lomb_scargle_peak=ls_peak,
            lomb_scargle_period=ls_period,
            rotation_period_days=ls_period,
        ),
    )


def _snr(adopted: float = 12.0) -> SNRBreakdown:
    return SNRBreakdown(
        snr_simple=adopted,
        snr_dutycycle=adopted,
        snr_per_point=adopted * 2,
        snr_tls=adopted * 0.5,
        snr_adopted=adopted,
        noise_floor_ppm=500.0,
        n_in_transit_total=20,
        duty_cycle=0.03,
    )


def _vetting(
    n_pass: int = 6,
    n_warn: int = 0,
    n_fail: int = 0,
    fpp: float | None = 0.0,
    is_fp: bool = False,
) -> VettingReport:
    tests = []
    for i in range(n_pass):
        tests.append(VettingTest(f"p{i}", VettingVerdict.PASS, 1.0, 1.0))
    for i in range(n_warn):
        tests.append(VettingTest(f"w{i}", VettingVerdict.WARN, 1.0, 1.0))
    for i in range(n_fail):
        tests.append(VettingTest(f"f{i}", VettingVerdict.FAIL, 1.0, 1.0))

    return VettingReport(
        target_id="TIC-100",
        sector=1,
        tests=tests,
        n_pass=n_pass,
        n_warn=n_warn,
        n_fail=n_fail,
        false_positive_probability=fpp,
        fpp_method=FPP_METHOD,
        is_false_positive=is_fp,
    )


@pytest.fixture
def scorer() -> CandidateScorer:
    return CandidateScorer()


# ─────────────────────────────────────────────────────────────
# CandidateClass & CLASS_DESCRIPTIONS
# ─────────────────────────────────────────────────────────────

def test_candidate_class_values() -> None:
    assert CandidateClass.A.value == "A"
    assert CandidateClass.B.value == "B"
    assert CandidateClass.C.value == "C"
    assert CandidateClass.D.value == "D"
    assert CandidateClass.X.value == "X"


def test_class_descriptions_all_present() -> None:
    for cls in CandidateClass:
        assert cls in CLASS_DESCRIPTIONS
        assert isinstance(CLASS_DESCRIPTIONS[cls], str)
        assert len(CLASS_DESCRIPTIONS[cls]) > 0


# ─────────────────────────────────────────────────────────────
# ScoreComponent
# ─────────────────────────────────────────────────────────────

def test_score_component_to_dict() -> None:
    c = ScoreComponent(
        name="snr", raw_value=12.5, score=85.0,
        weight=0.20, contribution=17.0,
    )
    d = c.to_dict()
    assert d["name"] == "snr"
    assert d["raw_value"] == 12.5
    assert d["score"] == 85.0
    assert d["weight"] == 0.2
    assert d["contribution"] == 17.0


# ─────────────────────────────────────────────────────────────
# QualityScore
# ─────────────────────────────────────────────────────────────

def test_quality_score_to_dict() -> None:
    q = QualityScore(
        target_id="TIC-100", sector=1,
        total_score=72.5,
        candidate_class=CandidateClass.B,
        class_description="test",
        components=[ScoreComponent("snr", 12.0, 80.0, 0.2, 16.0)],
        is_anomalous=False, anomaly_flags=[],
        fpp=0.15, is_false_positive=False,
    )
    d = q.to_dict()
    assert d["target_id"] == "TIC-100"
    assert d["total_score"] == 72.5
    assert d["candidate_class"] == "B"
    assert d["fpp"] == 0.15
    assert len(d["components"]) == 1


def test_quality_score_to_dict_fpp_none() -> None:
    q = QualityScore(
        target_id="TIC-1", sector=1, total_score=50.0,
        candidate_class=CandidateClass.C, class_description="x",
        fpp=None,
    )
    assert q.to_dict()["fpp"] is None


def test_quality_score_summary() -> None:
    q = QualityScore(
        target_id="TIC-1", sector=2, total_score=80.0,
        candidate_class=CandidateClass.A, class_description="x",
        fpp=0.05, is_false_positive=False, is_anomalous=False,
    )
    s = q.summary()
    assert s["target_id"] == "TIC-1"
    assert s["sector"] == 2
    assert s["score"] == 80.0
    assert s["class"] == "A"
    assert s["fpp"] == 0.05
    assert s["is_fp"] is False


def test_quality_score_summary_fpp_none() -> None:
    q = QualityScore(
        target_id="TIC-1", sector=1, total_score=50.0,
        candidate_class=CandidateClass.C, class_description="x",
        fpp=None,
    )
    assert q.summary()["fpp"] is None


# ─────────────────────────────────────────────────────────────
# __init__
# ─────────────────────────────────────────────────────────────

def test_scorer_init_defaults() -> None:
    s = CandidateScorer()
    assert s.snr_min == 7.0
    assert s.snr_max == 50.0
    assert s.class_a_threshold == 90.0
    assert s.class_b_threshold == 75.0
    assert s.class_c_threshold == 55.0


def test_scorer_init_custom() -> None:
    s = CandidateScorer(snr_min=5.0, class_a_threshold=85.0)
    assert s.snr_min == 5.0
    assert s.class_a_threshold == 85.0


# ─────────────────────────────────────────────────────────────
# score() — temel skorlama
# ─────────────────────────────────────────────────────────────

def test_score_typical_case(scorer: CandidateScorer) -> None:
    result = scorer.score(
        _candidate(), _metrics(), _snr(), _vetting(),
    )
    assert isinstance(result, QualityScore)
    assert result.target_id == "TIC-100"
    assert 0.0 <= result.total_score <= 100.0
    assert result.candidate_class in CandidateClass


def test_score_components_count(scorer: CandidateScorer) -> None:
    """7 bilesen: snr, completeness, transit_quality, vetting, residual,
    period_consistency, physical_consistency."""
    result = scorer.score(_candidate(), _metrics(), _snr(), _vetting())
    names = [c.name for c in result.components]
    assert "snr" in names
    assert "completeness" in names
    assert "transit_quality" in names
    assert "vetting" in names
    assert "residual" in names
    assert "period_consistency" in names
    assert "physical_consistency" in names


def test_score_weights_sum_to_one(scorer: CandidateScorer) -> None:
    total_weight = sum(CandidateScorer.WEIGHTS.values())
    assert total_weight == pytest.approx(1.0)


def test_score_fp_penalty(scorer: CandidateScorer) -> None:
    """is_false_positive=True -> skor 0.3 ile carpilir."""
    result_normal = scorer.score(
        _candidate(), _metrics(), _snr(), _vetting(is_fp=False),
    )
    result_fp = scorer.score(
        _candidate(), _metrics(), _snr(), _vetting(is_fp=True),
    )
    assert result_fp.total_score <= result_normal.total_score


def test_score_fp_class_D(scorer: CandidateScorer) -> None:
    """FP -> Class D."""
    result = scorer.score(
        _candidate(), _metrics(), _snr(), _vetting(is_fp=True),
    )
    assert result.candidate_class == CandidateClass.D


def test_score_unconfirmed_capped_at_50(scorer: CandidateScorer) -> None:
    """confirmed=False -> skor <= 50."""
    result = scorer.score(
        _candidate(confirmed=False), _metrics(), _snr(), _vetting(),
    )
    assert result.total_score <= 50.0


def test_score_anomaly_class_X(scorer: CandidateScorer) -> None:
    """n_transits=1 -> monotransit anomalisi -> Class X."""
    result = scorer.score(
        _candidate(), _metrics(n_transits=1), _snr(), _vetting(),
    )
    assert result.is_anomalous is True
    assert result.candidate_class == CandidateClass.X
    assert any("Monotransit" in f for f in result.anomaly_flags)


def test_score_low_snr_low_score(scorer: CandidateScorer) -> None:
    """snr_min altinda -> dusuk skor."""
    result_low = scorer.score(
        _candidate(), _metrics(snr=0.5), _snr(adopted=0.5), _vetting(),
    )
    result_high = scorer.score(
        _candidate(), _metrics(snr=40.0), _snr(adopted=40.0), _vetting(),
    )
    assert result_low.total_score < result_high.total_score


def test_score_fpp_value_preserved(scorer: CandidateScorer) -> None:
    result = scorer.score(
        _candidate(), _metrics(), _snr(), _vetting(fpp=0.12),
    )
    assert result.fpp == 0.12


def test_score_fpp_none_preserved(scorer: CandidateScorer) -> None:
    result = scorer.score(
        _candidate(), _metrics(), _snr(), _vetting(fpp=None),
    )
    assert result.fpp is None


# ─────────────────────────────────────────────────────────────
# _assign_class
# ─────────────────────────────────────────────────────────────

def test_assign_class_anomalous_is_X(scorer: CandidateScorer) -> None:
    assert scorer._assign_class(95.0, _vetting(), True) == CandidateClass.X


def test_assign_class_fp_is_D(scorer: CandidateScorer) -> None:
    assert scorer._assign_class(
        95.0, _vetting(is_fp=True), False,
    ) == CandidateClass.D


def test_assign_class_A(scorer: CandidateScorer) -> None:
    assert scorer._assign_class(95.0, _vetting(), False) == CandidateClass.A


def test_assign_class_B(scorer: CandidateScorer) -> None:
    assert scorer._assign_class(80.0, _vetting(), False) == CandidateClass.B


def test_assign_class_C(scorer: CandidateScorer) -> None:
    assert scorer._assign_class(60.0, _vetting(), False) == CandidateClass.C


def test_assign_class_D(scorer: CandidateScorer) -> None:
    assert scorer._assign_class(30.0, _vetting(), False) == CandidateClass.D


# ─────────────────────────────────────────────────────────────
# _compute_transit_quality_score
# ─────────────────────────────────────────────────────────────

def test_transit_quality_with_symmetry(scorer: CandidateScorer) -> None:
    score = scorer._compute_transit_quality_score(
        _candidate(), _metrics(transit_symmetry=0.9),
    )
    assert 0.0 <= score <= 100.0


def test_transit_quality_no_symmetry(scorer: CandidateScorer) -> None:
    """symmetry=0 -> sadece n_transits kullanilir."""
    score = scorer._compute_transit_quality_score(
        _candidate(), _metrics(transit_symmetry=0.0),
    )
    assert 0.0 <= score <= 100.0


def test_transit_quality_with_odd_even(scorer: CandidateScorer) -> None:
    score = scorer._compute_transit_quality_score(
        _candidate(), _metrics(odd_even_mismatch=1.5),
    )
    assert 0.0 <= score <= 100.0


# ─────────────────────────────────────────────────────────────
# _compute_vetting_score
# ─────────────────────────────────────────────────────────────

def test_vetting_score_all_pass(scorer: CandidateScorer) -> None:
    score = scorer._compute_vetting_score(_vetting(n_pass=6))
    # 6 pass * 100 / 6 tests = 100, fpp=0 -> 100
    assert score == pytest.approx(100.0)


def test_vetting_score_no_tests(scorer: CandidateScorer) -> None:
    score = scorer._compute_vetting_score(_vetting(n_pass=0))
    assert score == 50.0


def test_vetting_score_with_warn(scorer: CandidateScorer) -> None:
    score = scorer._compute_vetting_score(_vetting(n_pass=3, n_warn=3))
    # (3*100 + 3*40) / 6 = 70
    assert score == pytest.approx(70.0)


def test_vetting_score_with_fail(scorer: CandidateScorer) -> None:
    score = scorer._compute_vetting_score(_vetting(n_pass=4, n_fail=2))
    # (4*100 + 2*0) / 6 = 66.67
    assert score == pytest.approx(66.67, abs=0.1)


def test_vetting_score_fpp_penalty(scorer: CandidateScorer) -> None:
    """fpp=0.5 -> penalty=25 -> score duser."""
    score_high_fpp = scorer._compute_vetting_score(
        _vetting(n_pass=6, fpp=0.5),
    )
    score_zero_fpp = scorer._compute_vetting_score(
        _vetting(n_pass=6, fpp=0.0),
    )
    assert score_high_fpp < score_zero_fpp


def test_vetting_score_fpp_none_no_penalty(scorer: CandidateScorer) -> None:
    """fpp=None -> penalty yok."""
    score = scorer._compute_vetting_score(_vetting(n_pass=6, fpp=None))
    assert score == pytest.approx(100.0)


# ─────────────────────────────────────────────────────────────
# _detect_anomaly
# ─────────────────────────────────────────────────────────────

def test_detect_anomaly_clean(scorer: CandidateScorer) -> None:
    is_anom, flags = scorer._detect_anomaly(
        _candidate(), _metrics(), _vetting(),
    )
    assert is_anom is False
    assert flags == []


def test_detect_anomaly_ttv(scorer: CandidateScorer) -> None:
    """timing_rms > 30 dk ve n_transits >= 5."""
    is_anom, flags = scorer._detect_anomaly(
        _candidate(), _metrics(timing_rms=0.05, n_transits=6), _vetting(),
    )
    assert is_anom is True
    assert any("TTV" in f for f in flags)


def test_detect_anomaly_ttv_few_transits_no_flag(scorer: CandidateScorer) -> None:
    """n_transits < 5 -> TTV flagi eklenmez."""
    _, flags = scorer._detect_anomaly(
        _candidate(), _metrics(timing_rms=0.05, n_transits=3), _vetting(),
    )
    assert not any("TTV" in f for f in flags)


def test_detect_anomaly_monotransit(scorer: CandidateScorer) -> None:
    is_anom, flags = scorer._detect_anomaly(
        _candidate(), _metrics(n_transits=1), _vetting(),
    )
    assert is_anom is True
    assert any("Monotransit" in f for f in flags)


def test_detect_anomaly_deep_transit(scorer: CandidateScorer) -> None:
    """depth > 0.10 ve snr > 100."""
    is_anom, flags = scorer._detect_anomaly(
        _candidate(depth=0.15), _metrics(snr=150.0), _vetting(),
    )
    assert is_anom is True
    assert any("derin transit" in f.lower() for f in flags)


def test_detect_anomaly_active_star(scorer: CandidateScorer) -> None:
    """LS peak > 0.7 ve rotation 0.1-1.5d."""
    is_anom, flags = scorer._detect_anomaly(
        _candidate(),
        _metrics(ls_peak=0.9, ls_period=0.8),
        _vetting(),
    )
    assert is_anom is True
    assert any("Aktif yıldız" in f for f in flags)


# ─────────────────────────────────────────────────────────────
# _compute_period_relative_diff
# ─────────────────────────────────────────────────────────────

def test_period_diff_bls_failed() -> None:
    cand = _candidate(status=CascadeStatus.BLS_FAILED)
    assert CandidateScorer._compute_period_relative_diff(cand) == 1.0


def test_period_diff_tls_failed() -> None:
    cand = _candidate(status=CascadeStatus.TLS_FAILED)
    assert CandidateScorer._compute_period_relative_diff(cand) == 1.0


def test_period_diff_error() -> None:
    cand = _candidate(status=CascadeStatus.ERROR)
    assert CandidateScorer._compute_period_relative_diff(cand) == 1.0


def test_period_diff_no_bls_best() -> None:
    """bls_result.best None -> 0.0."""
    cand = _candidate()
    cand.bls_result = MagicMock()
    cand.bls_result.best = None
    assert CandidateScorer._compute_period_relative_diff(cand) == 0.0


def test_period_diff_no_tls_result() -> None:
    cand = _candidate()
    cand.bls_result = MagicMock()
    cand.bls_result.best = MagicMock(period=5.0)
    cand.tls_result = None
    assert CandidateScorer._compute_period_relative_diff(cand) == 0.0


def test_period_diff_perfect_match() -> None:
    cand = _candidate()
    cand.bls_result.best.period = 5.0
    cand.tls_result.period = 5.0
    diff = CandidateScorer._compute_period_relative_diff(cand)
    assert diff == pytest.approx(0.0, abs=1e-6)


def test_period_diff_2x_harmonic() -> None:
    """BLS=5, TLS=10 -> factor=2.0 ile eslesir -> diff=0."""
    cand = _candidate()
    cand.bls_result.best.period = 5.0
    cand.tls_result.period = 10.0
    diff = CandidateScorer._compute_period_relative_diff(cand)
    assert diff == pytest.approx(0.0, abs=1e-6)


def test_period_diff_bad_values() -> None:
    cand = _candidate()
    cand.bls_result.best.period = -1.0
    cand.tls_result.period = 5.0
    assert CandidateScorer._compute_period_relative_diff(cand) == 1.0


# ─────────────────────────────────────────────────────────────
# _compute_period_consistency_score
# ─────────────────────────────────────────────────────────────

def test_period_consistency_perfect() -> None:
    cand = _candidate()
    cand.bls_result.best.period = 5.0
    cand.tls_result.period = 5.0
    score = CandidateScorer._compute_period_consistency_score(cand)
    assert score == pytest.approx(100.0, abs=1.0)


def test_period_consistency_mismatch_status() -> None:
    """PERIOD_MISMATCH -> 0.3 ile carpilir."""
    cand = _candidate(status=CascadeStatus.PERIOD_MISMATCH)
    cand.bls_result.best.period = 5.0
    cand.tls_result.period = 5.0
    score = CandidateScorer._compute_period_consistency_score(cand)
    assert score <= 30.0


def test_period_consistency_failed_status() -> None:
    """BLS_FAILED -> skor <= 20."""
    cand = _candidate(status=CascadeStatus.BLS_FAILED)
    score = CandidateScorer._compute_period_consistency_score(cand)
    assert score <= 20.0


# ─────────────────────────────────────────────────────────────
# _compute_physical_consistency_score
# ─────────────────────────────────────────────────────────────

def test_physical_consistency_clean() -> None:
    cand = _candidate(depth=0.005, rp_rs=0.08)
    # depth/rp_rs^2 = 0.005 / 0.0064 ~ 0.78 -> OK
    score, flags = CandidateScorer._compute_physical_consistency_score(cand)
    assert score > 0
    assert isinstance(flags, list)


def test_physical_consistency_depth_mismatch() -> None:
    """depth/rp_rs^2 >> 2 -> flag."""
    cand = _candidate(depth=0.05, rp_rs=0.05)
    # depth/rp_rs^2 = 0.05 / 0.0025 = 20 >> 2
    _, flags = CandidateScorer._compute_physical_consistency_score(cand)
    assert any("depth-rp_rs" in f for f in flags)


def test_physical_consistency_bad_duration_ratio() -> None:
    """duration/period > 0.15 -> flag."""
    cand = _candidate(period=1.0, duration=0.5)  # ratio = 0.5
    _, flags = CandidateScorer._compute_physical_consistency_score(cand)
    assert any("sure/periyot" in f for f in flags)


def test_physical_consistency_long_period_strict() -> None:
    """period > 10 -> max ratio 0.05."""
    cand = _candidate(period=20.0, duration=2.0)  # ratio = 0.1 > 0.05
    _, flags = CandidateScorer._compute_physical_consistency_score(cand)
    assert any("sure/periyot" in f for f in flags)


def test_physical_consistency_tiny_duration_ratio() -> None:
    """duration/period < 0.001 -> flag."""
    cand = _candidate(period=10.0, duration=0.005)  # ratio = 0.0005
    _, flags = CandidateScorer._compute_physical_consistency_score(cand)
    assert any("cok kucuk" in f for f in flags)


def test_physical_consistency_large_rp_rs() -> None:
    """rp_rs > 0.3 -> flag."""
    cand = _candidate(depth=0.1, rp_rs=0.35)
    _, flags = CandidateScorer._compute_physical_consistency_score(cand)
    assert any("> 0.3" in f for f in flags)


def test_physical_consistency_medium_rp_rs() -> None:
    """0.2 < rp_rs <= 0.3 -> flag."""
    cand = _candidate(depth=0.05, rp_rs=0.25)
    _, flags = CandidateScorer._compute_physical_consistency_score(cand)
    assert any("> 0.2" in f for f in flags)


def test_physical_consistency_with_fit_rp_too_large() -> None:
    cand = _candidate()
    fit = MagicMock()
    fit.derived.planet_radius_rearth = 35.0
    _, flags = CandidateScorer._compute_physical_consistency_score(cand, fit)
    assert any("> 30" in f for f in flags)


def test_physical_consistency_with_fit_rp_suspicious() -> None:
    cand = _candidate()
    fit = MagicMock()
    fit.derived.planet_radius_rearth = 27.0
    _, flags = CandidateScorer._compute_physical_consistency_score(cand, fit)
    assert any("> 25" in f for f in flags)


def test_physical_consistency_with_fit_rp_tiny() -> None:
    cand = _candidate()
    fit = MagicMock()
    fit.derived.planet_radius_rearth = 0.2
    _, flags = CandidateScorer._compute_physical_consistency_score(cand, fit)
    assert any("< 0.3" in f for f in flags)


def test_physical_consistency_bls_tls_mismatch() -> None:
    """BLS SNR > 100 ama TLS SDE < 10."""
    cand = _candidate()
    cand.bls_result.best.snr = 150.0
    cand.tls_result.sde = 5.0
    _, flags = CandidateScorer._compute_physical_consistency_score(cand)
    assert any("tutarsiz" in f for f in flags)


# ─────────────────────────────────────────────────────────────
# _normalize_linear
# ─────────────────────────────────────────────────────────────

def test_normalize_linear_midpoint() -> None:
    assert CandidateScorer._normalize_linear(5.0, 0.0, 10.0) == 50.0


def test_normalize_linear_below() -> None:
    assert CandidateScorer._normalize_linear(-5.0, 0.0, 10.0) == 0.0


def test_normalize_linear_above() -> None:
    assert CandidateScorer._normalize_linear(15.0, 0.0, 10.0) == 100.0


def test_normalize_linear_bad_range() -> None:
    """v_max <= v_min -> 50."""
    assert CandidateScorer._normalize_linear(5.0, 10.0, 5.0) == 50.0


# ─────────────────────────────────────────────────────────────
# _normalize_linear_inverse
# ─────────────────────────────────────────────────────────────

def test_normalize_inverse_midpoint() -> None:
    assert CandidateScorer._normalize_linear_inverse(5.0, 0.0, 10.0) == 0.5


def test_normalize_inverse_below() -> None:
    assert CandidateScorer._normalize_linear_inverse(-5.0, 0.0, 10.0) == 1.0


def test_normalize_inverse_above() -> None:
    assert CandidateScorer._normalize_linear_inverse(15.0, 0.0, 10.0) == 0.0


def test_normalize_inverse_bad_range() -> None:
    assert CandidateScorer._normalize_linear_inverse(5.0, 10.0, 5.0) == 0.5


# ─────────────────────────────────────────────────────────────
# score() — bilesen dogrulugu
# ─────────────────────────────────────────────────────────────

def test_score_total_is_clipped(scorer: CandidateScorer) -> None:
    """Cok yuksek bilesen skorlari olsa bile total <= 100."""
    result = scorer.score(
        _candidate(), _metrics(snr=50.0, data_completeness=1.0),
        _snr(adopted=50.0), _vetting(),
    )
    assert result.total_score <= 100.0
    assert result.total_score >= 0.0


def test_score_low_physical_penalty(scorer: CandidateScorer) -> None:
    """physical_consistency < 60 -> ek ceza."""
    # rp_rs=0.35 -> physical penalty 40, score ~60 threshold
    result = scorer.score(
        _candidate(depth=0.05, rp_rs=0.35), _metrics(), _snr(), _vetting(),
    )
    assert 0.0 <= result.total_score <= 100.0
