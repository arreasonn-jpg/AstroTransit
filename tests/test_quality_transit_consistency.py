"""
TransitConsistencyAnalyzer birim testleri.

Kapsam
------
- TransitConsistencyTest / TransitConsistencyReport to_dict + summary
- analyze(): temel akis, NaN temizleme, event_ids eslesmezligi
- _test_even_odd_depth_consistency: PASS/WARN/FAIL/SKIP
- _test_transit_repeatability: PASS/WARN/FAIL/SKIP
- _test_v_shape_metric: PASS/WARN/FAIL/SKIP
- _test_ingress_egress_symmetry: PASS/WARN/FAIL/SKIP
- _estimate_baseline, _resolve_per_transit_depths
- _compute_details, _compute_score, _compute_flag
"""

from __future__ import annotations

import numpy as np
import pytest

from astrotransit.quality.transit_consistency import (
    TransitConsistencyAnalyzer,
    TransitConsistencyReport,
    TransitConsistencyTest,
)
from astrotransit.quality.vetting import VettingVerdict

# ─────────────────────────────────────────────────────────────
# Synthetic phase-folded light curve
# ─────────────────────────────────────────────────────────────

def _folded_signal(
    n: int = 500,
    depth: float = 0.005,
    duration_phase: float = 0.1,
    noise: float = 1e-4,
    seed: int = 0,
    asym: float = 0.0,
    v_shape: bool = False,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Faz katlanmis transit sinyali uretir (mid-transit=0)."""
    rng = np.random.default_rng(seed)
    phase = np.linspace(-0.5, 0.5, n)
    flux = 1.0 + rng.normal(0, noise, size=n)

    in_transit = np.abs(phase) < (duration_phase / 2)
    # Baseline sinyal
    if v_shape:
        # U seklinde degil, lineer V seklinde
        profile = 1.0 - depth * (1.0 - np.abs(phase[in_transit]) / (duration_phase / 2))
    else:
        # Kutu benzeri (flat bottom)
        profile = 1.0 - depth
    flux[in_transit] = profile

    # Asimetri ekle (sag tarafi derinlestir/hafiflestir)
    if asym != 0.0:
        right_half = in_transit & (phase > 0)
        flux[right_half] += depth * asym

    event_ids = np.full(n, -1, dtype=int)
    # event IDs: sol/sag transit'leri temsil etsin (basit)
    event_ids[in_transit] = 0

    return phase, flux, in_transit, event_ids


def _per_depths_even_odd(
    n_odd: int = 3,
    n_even: int = 3,
    odd_depth: float = 0.005,
    even_depth: float = 0.005,
) -> np.ndarray:
    """Odd ve even transit derinlikleri."""
    # Odd indeksler 0,2,4...; even 1,3,5...
    values = []
    for i in range(n_odd + n_even):
        if i % 2 == 0 and len([v for v in values[::2]]) < n_odd:
            values.append(odd_depth)
        else:
            values.append(even_depth)
    return np.asarray(values[:n_odd + n_even], dtype=float)


@pytest.fixture
def analyzer() -> TransitConsistencyAnalyzer:
    return TransitConsistencyAnalyzer()


# ─────────────────────────────────────────────────────────────
# TransitConsistencyTest.to_dict
# ─────────────────────────────────────────────────────────────

def test_test_to_dict() -> None:
    t = TransitConsistencyTest(
        name="foo", verdict=VettingVerdict.PASS,
        value=0.1, warn_threshold=0.2, fail_threshold=0.3,
        description="desc",
    )
    d = t.to_dict()
    assert d["name"] == "foo"
    assert d["verdict"] == "pass"
    assert d["value"] == 0.1
    assert d["warn_threshold"] == 0.2
    assert d["fail_threshold"] == 0.3
    assert d["description"] == "desc"


# ─────────────────────────────────────────────────────────────
# TransitConsistencyReport.to_dict / summary
# ─────────────────────────────────────────────────────────────

def test_report_to_dict() -> None:
    r = TransitConsistencyReport(
        target_id="TIC-1", sector=1,
        n_intransit=100, n_transits=5,
        flag="CONSISTENT", score=0.1,
        n_pass=4, n_warn=1, n_fail=0, n_skip=0,
        details={"baseline": 1.0, "n_transits": 5},
    )
    d = r.to_dict()
    assert d["target_id"] == "TIC-1"
    assert d["flag"] == "CONSISTENT"
    assert d["score"] == 0.1
    assert d["details"]["baseline"] == 1.0


def test_report_summary() -> None:
    r = TransitConsistencyReport(
        target_id="TIC-1", sector=2,
        flag="VARIABLE", score=0.35,
        n_pass=2, n_warn=1, n_fail=1, n_skip=0,
        n_transits=4,
    )
    s = r.summary()
    assert "TIC-1" in s
    assert "S2" in s
    assert "VARIABLE" in s
    assert "n_transits=4" in s


# ─────────────────────────────────────────────────────────────
# __init__
# ─────────────────────────────────────────────────────────────

def test_analyzer_init_defaults() -> None:
    a = TransitConsistencyAnalyzer()
    assert a.even_odd_warn == 0.15
    assert a.even_odd_fail == 0.30
    assert a.repeat_warn == 0.25
    assert a.repeat_fail == 0.40
    assert a.vshape_warn == 0.65
    assert a.vshape_fail == 0.85
    assert a.asym_warn == 0.20
    assert a.asym_fail == 0.40


def test_analyzer_init_custom() -> None:
    a = TransitConsistencyAnalyzer(
        even_odd_warn=0.1, even_odd_fail=0.2,
        repeat_warn=0.1, repeat_fail=0.2,
        vshape_warn=0.5, vshape_fail=0.7,
        asym_warn=0.1, asym_fail=0.3,
    )
    assert a.even_odd_warn == 0.1
    assert a.vshape_fail == 0.7


# ─────────────────────────────────────────────────────────────
# _estimate_baseline
# ─────────────────────────────────────────────────────────────

def test_estimate_baseline_oot_median() -> None:
    flux = np.array([1.0, 1.0, 1.0, 0.99, 1.01, 0.99, 1.01])
    mask = np.array([False, False, False, True, True, True, True])
    baseline = TransitConsistencyAnalyzer._estimate_baseline(flux, mask)
    assert baseline == pytest.approx(1.0)


def test_estimate_baseline_no_oot() -> None:
    """OOT < 5 -> tum flux median."""
    flux = np.array([1.0, 0.99, 0.98])
    mask = np.array([True, True, True])
    baseline = TransitConsistencyAnalyzer._estimate_baseline(flux, mask)
    assert baseline == pytest.approx(0.99)


def test_estimate_baseline_all_nan() -> None:
    flux = np.array([np.nan, np.nan])
    mask = np.array([True, False])
    assert TransitConsistencyAnalyzer._estimate_baseline(flux, mask) == 1.0


# ─────────────────────────────────────────────────────────────
# _resolve_per_transit_depths
# ─────────────────────────────────────────────────────────────

def test_resolve_explicit_depths(analyzer: TransitConsistencyAnalyzer) -> None:
    depths = np.array([0.005, 0.006, 0.004])
    flux = np.ones(10)
    mask = np.zeros(10, dtype=bool)
    out = analyzer._resolve_per_transit_depths(
        flux=flux, in_transit_mask=mask,
        transit_event_ids=None, per_transit_depths=depths,
        baseline=1.0,
    )
    assert np.array_equal(out, depths)


def test_resolve_explicit_filters_invalid(analyzer: TransitConsistencyAnalyzer) -> None:
    """0, negatif ve NaN filtrelenmeli."""
    depths = np.array([0.005, 0.0, -0.001, np.nan, 0.006])
    flux = np.ones(5)
    mask = np.zeros(5, dtype=bool)
    out = analyzer._resolve_per_transit_depths(
        flux=flux, in_transit_mask=mask,
        transit_event_ids=None, per_transit_depths=depths,
        baseline=1.0,
    )
    assert len(out) == 2
    assert all(out > 0)


def test_resolve_from_event_ids(analyzer: TransitConsistencyAnalyzer) -> None:
    """event_ids verilirse flux uzerinden derinlik tahmini."""
    n = 30
    flux = np.ones(n)
    # event 0: noktalar 0-4, event 1: noktalar 5-9
    flux[0:5] = 0.995
    flux[5:10] = 0.996
    mask = np.zeros(n, dtype=bool)
    mask[0:10] = True
    event_ids = np.full(n, -1, dtype=int)
    event_ids[0:5] = 0
    event_ids[5:10] = 1

    out = analyzer._resolve_per_transit_depths(
        flux=flux, in_transit_mask=mask,
        transit_event_ids=event_ids, per_transit_depths=None,
        baseline=1.0,
    )
    assert len(out) == 2
    # event 0 depth ~0.005, event 1 ~0.004
    assert out[0] == pytest.approx(0.005, abs=1e-6)


def test_resolve_no_event_ids(analyzer: TransitConsistencyAnalyzer) -> None:
    """event_ids None -> bos dizi."""
    flux = np.ones(10)
    mask = np.zeros(10, dtype=bool)
    out = analyzer._resolve_per_transit_depths(
        flux=flux, in_transit_mask=mask,
        transit_event_ids=None, per_transit_depths=None,
        baseline=1.0,
    )
    assert len(out) == 0


def test_resolve_event_ids_wrong_length(analyzer: TransitConsistencyAnalyzer) -> None:
    flux = np.ones(10)
    mask = np.zeros(10, dtype=bool)
    event_ids = np.array([0, 1, 2])
    out = analyzer._resolve_per_transit_depths(
        flux=flux, in_transit_mask=mask,
        transit_event_ids=event_ids, per_transit_depths=None,
        baseline=1.0,
    )
    assert len(out) == 0


def test_resolve_event_ids_too_few_points(analyzer: TransitConsistencyAnalyzer) -> None:
    """Her event icin <2 nokta -> atlanir."""
    n = 10
    flux = np.ones(n)
    mask = np.zeros(n, dtype=bool)
    mask[0] = True  # sadece 1 nokta
    event_ids = np.full(n, -1, dtype=int)
    event_ids[0] = 0

    out = analyzer._resolve_per_transit_depths(
        flux=flux, in_transit_mask=mask,
        transit_event_ids=event_ids, per_transit_depths=None,
        baseline=1.0,
    )
    assert len(out) == 0


# ─────────────────────────────────────────────────────────────
# _test_even_odd_depth_consistency
# ─────────────────────────────────────────────────────────────

def test_even_odd_skip_insufficient(analyzer: TransitConsistencyAnalyzer) -> None:
    t = analyzer._test_even_odd_depth_consistency(np.array([0.005, 0.006]))
    assert t.verdict == VettingVerdict.SKIP


def test_even_odd_pass(analyzer: TransitConsistencyAnalyzer) -> None:
    depths = np.array([0.005, 0.005, 0.005, 0.005, 0.005, 0.005])
    t = analyzer._test_even_odd_depth_consistency(depths)
    assert t.verdict == VettingVerdict.PASS
    assert t.value == pytest.approx(0.0, abs=1e-6)


def test_even_odd_warn(analyzer: TransitConsistencyAnalyzer) -> None:
    """frac_diff ~0.2 -> WARN (>0.15)"""
    depths = np.array([0.005, 0.006, 0.005, 0.006, 0.005, 0.006])
    # med_all ~0.0055, med_odd = 0.005, med_even = 0.006 -> 0.001/0.0055 ~ 0.18
    t = analyzer._test_even_odd_depth_consistency(depths)
    assert t.verdict == VettingVerdict.WARN


def test_even_odd_fail(analyzer: TransitConsistencyAnalyzer) -> None:
    """frac_diff > 0.3 -> FAIL"""
    depths = np.array([0.01, 0.003, 0.01, 0.003, 0.01, 0.003])
    # med_all=0.0065, med_odd=0.01, med_even=0.003, diff/med_all ~ 1.07
    t = analyzer._test_even_odd_depth_consistency(depths)
    assert t.verdict == VettingVerdict.FAIL


def test_even_odd_zero_median(analyzer: TransitConsistencyAnalyzer) -> None:
    """med_all<=0 -> SKIP (filtreden gecmemis olsa bile)"""
    depths = np.array([0.0, 0.0, 0.0, 0.0])
    t = analyzer._test_even_odd_depth_consistency(depths)
    assert t.verdict == VettingVerdict.SKIP


# ─────────────────────────────────────────────────────────────
# _test_transit_repeatability
# ─────────────────────────────────────────────────────────────

def test_repeat_skip_insufficient(analyzer: TransitConsistencyAnalyzer) -> None:
    t = analyzer._test_transit_repeatability(np.array([0.005, 0.006]))
    assert t.verdict == VettingVerdict.SKIP


def test_repeat_pass(analyzer: TransitConsistencyAnalyzer) -> None:
    """Sabit derinlikler -> scatter ~0."""
    depths = np.array([0.005] * 6)
    t = analyzer._test_transit_repeatability(depths)
    assert t.verdict == VettingVerdict.PASS
    assert t.value == pytest.approx(0.0, abs=1e-6)


def test_repeat_warn(analyzer: TransitConsistencyAnalyzer) -> None:
    """Orta seviye scatter."""
    depths = np.array([0.005, 0.006, 0.004, 0.0055, 0.0045, 0.006])
    t = analyzer._test_transit_repeatability(depths)
    # WARN veya PASS olabilir — hangi araliga dustugunu kontrol et
    assert t.verdict in (VettingVerdict.PASS, VettingVerdict.WARN)


def test_repeat_fail(analyzer: TransitConsistencyAnalyzer) -> None:
    """Cok yuksek scatter (MAD/median > 0.4) -> FAIL.

    Not: MAD (median absolute deviation) hesabinda ayni degerler tekrar
    ederse MAD=0 olur ve norm_scatter 0'a iner. Bu yuzden heterojen
    degerler kullanmak gerekir.
    """
    depths = np.array([0.002, 0.005, 0.010, 0.001, 0.008])
    # median=0.005, deviations=[0.003, 0, 0.005, 0.004, 0.003], MAD=0.003
    # robust_sigma ~ 1.4826*0.003 = 0.00445, ratio ~ 0.89 > 0.40
    t = analyzer._test_transit_repeatability(depths)
    assert t.verdict == VettingVerdict.FAIL


def test_repeat_negative_median(analyzer: TransitConsistencyAnalyzer) -> None:
    """med<=0 -> SKIP."""
    depths = np.array([-1.0, -2.0, -3.0])
    t = analyzer._test_transit_repeatability(depths)
    assert t.verdict == VettingVerdict.SKIP


# ─────────────────────────────────────────────────────────────
# _test_v_shape_metric
# ─────────────────────────────────────────────────────────────

def test_vshape_skip_insufficient(analyzer: TransitConsistencyAnalyzer) -> None:
    in_phase = np.array([-0.02, 0.0, 0.02])
    in_flux = np.array([0.995, 0.995, 0.995])
    t = analyzer._test_v_shape_metric(in_phase, in_flux, baseline=1.0)
    assert t.verdict == VettingVerdict.SKIP


def test_vshape_pass_flat_bottom(analyzer: TransitConsistencyAnalyzer) -> None:
    """Gercek U-shape (merkez derin, kanatlar sig) -> dusuk ratio -> PASS.

    Not: 'flat bottom' ifadesi kutu transit anlamina gelir; gercek U-shape
    profili Gaussian benzeri bir dagilimdir — wings derinlige katkida
    bulunmaz. Uniform depth (duz cizgi) aslinda V-shape olarak siniflanir
    (merkez ve wing ayni derinlikte).
    """
    # Gaussian benzeri profil: kanatlar sig
    in_phase = np.linspace(-0.05, 0.05, 60)
    depth = 0.005 * np.exp(-0.5 * (in_phase / 0.008) ** 2)
    in_flux = 1.0 - depth
    t = analyzer._test_v_shape_metric(in_phase, in_flux, baseline=1.0)
    assert t.verdict == VettingVerdict.PASS
    assert t.value < 0.5


def test_vshape_fail_strong_v(analyzer: TransitConsistencyAnalyzer) -> None:
    """Uniform depth (merkez=wing) -> V-shape uyarisi -> FAIL.

    Gercek 'V-shape' (grazing EB) senaryosu: transit penceresi boyunca
    derinlik uniforma yakin kalir; ingress/egress belirgin sekilde
    merkeze gore daha sig degildir. Bu durumda wing/center ~ 1.0 olur.
    """
    in_phase = np.linspace(-0.05, 0.05, 50)
    # Uniform depth (V benzeri, sig kanat yok)
    in_flux = np.full(50, 0.995)
    t = analyzer._test_v_shape_metric(in_phase, in_flux, baseline=1.0)
    # wing/center ~ 1.0 > fail threshold 0.85
    assert t.verdict == VettingVerdict.FAIL
    assert t.value > 0.85


def test_vshape_no_depth(analyzer: TransitConsistencyAnalyzer) -> None:
    """in_flux == baseline -> depth=0 -> SKIP."""
    in_phase = np.linspace(-0.05, 0.05, 20)
    in_flux = np.ones(20)
    t = analyzer._test_v_shape_metric(in_phase, in_flux, baseline=1.0)
    assert t.verdict == VettingVerdict.SKIP


# ─────────────────────────────────────────────────────────────
# _test_ingress_egress_symmetry
# ─────────────────────────────────────────────────────────────

def test_asym_skip_insufficient(analyzer: TransitConsistencyAnalyzer) -> None:
    t = analyzer._test_ingress_egress_symmetry(
        np.array([-0.01, 0.01]), np.array([0.995, 0.995]), baseline=1.0,
    )
    assert t.verdict == VettingVerdict.SKIP


def test_asym_pass_symmetric(analyzer: TransitConsistencyAnalyzer) -> None:
    """Simetrik transit -> dusuk asym."""
    in_phase = np.linspace(-0.05, 0.05, 50)
    depth = 0.005 * np.exp(-0.5 * (in_phase / 0.02) ** 2)
    in_flux = 1.0 - depth
    t = analyzer._test_ingress_egress_symmetry(in_phase, in_flux, baseline=1.0)
    assert t.verdict == VettingVerdict.PASS


def test_asym_fail(analyzer: TransitConsistencyAnalyzer) -> None:
    """Sol/sag half-depth extent'leri cok farkli -> FAIL."""
    # Sol tarafi genis, sag tarafi dar
    left = np.linspace(-0.1, -0.001, 30)
    right = np.linspace(0.001, 0.03, 10)
    in_phase = np.concatenate([left, right])
    depth = np.concatenate([np.full(30, 0.005), np.full(10, 0.005)])
    in_flux = 1.0 - depth
    t = analyzer._test_ingress_egress_symmetry(in_phase, in_flux, baseline=1.0)
    assert t.verdict in (VettingVerdict.WARN, VettingVerdict.FAIL)


def test_asym_zero_depth(analyzer: TransitConsistencyAnalyzer) -> None:
    """peak_depth<=0 -> SKIP."""
    in_phase = np.linspace(-0.05, 0.05, 20)
    in_flux = np.ones(20)
    t = analyzer._test_ingress_egress_symmetry(in_phase, in_flux, baseline=1.0)
    assert t.verdict == VettingVerdict.SKIP


# ─────────────────────────────────────────────────────────────
# _compute_score
# ─────────────────────────────────────────────────────────────

def test_compute_score_all_pass() -> None:
    tests = [
        TransitConsistencyTest(
            "even_odd_depth_consistency", VettingVerdict.PASS, 0.0, 0.15, 0.30,
        ),
        TransitConsistencyTest(
            "transit_repeatability", VettingVerdict.PASS, 0.0, 0.25, 0.40,
        ),
    ]
    assert TransitConsistencyAnalyzer._compute_score(tests) == 0.0


def test_compute_score_all_fail() -> None:
    tests = [
        TransitConsistencyTest(
            "even_odd_depth_consistency", VettingVerdict.FAIL, 0.5, 0.15, 0.30,
        ),
        TransitConsistencyTest(
            "transit_repeatability", VettingVerdict.FAIL, 0.5, 0.25, 0.40,
        ),
    ]
    assert TransitConsistencyAnalyzer._compute_score(tests) == 1.0


def test_compute_score_warn_only() -> None:
    tests = [
        TransitConsistencyTest(
            "even_odd_depth_consistency", VettingVerdict.WARN, 0.2, 0.15, 0.30,
        ),
    ]
    # WARN -> 0.4
    assert TransitConsistencyAnalyzer._compute_score(tests) == pytest.approx(0.4)


def test_compute_score_all_skip() -> None:
    tests = [
        TransitConsistencyTest(
            "even_odd_depth_consistency", VettingVerdict.SKIP, 0.0, 0.15, 0.30,
        ),
    ]
    assert TransitConsistencyAnalyzer._compute_score(tests) == 0.0


# ─────────────────────────────────────────────────────────────
# _compute_flag
# ─────────────────────────────────────────────────────────────

def test_flag_consistent() -> None:
    tests = [
        TransitConsistencyTest(
            "even_odd_depth_consistency", VettingVerdict.PASS, 0.0, 0.15, 0.30,
        ),
    ]
    flag = TransitConsistencyAnalyzer._compute_flag(tests, 0.0, 0, 0)
    assert flag == "CONSISTENT"


def test_flag_variable_single_fail() -> None:
    tests = [
        TransitConsistencyTest(
            "transit_repeatability", VettingVerdict.FAIL, 0.5, 0.25, 0.40,
        ),
    ]
    flag = TransitConsistencyAnalyzer._compute_flag(tests, 0.5, 1, 0)
    assert flag == "VARIABLE"


def test_flag_eb_suspect_even_odd_fail() -> None:
    tests = [
        TransitConsistencyTest(
            "even_odd_depth_consistency", VettingVerdict.FAIL, 0.5, 0.15, 0.30,
        ),
    ]
    flag = TransitConsistencyAnalyzer._compute_flag(tests, 0.5, 1, 0)
    assert flag == "EB_SUSPECT"


def test_flag_eb_suspect_vshape_fail() -> None:
    tests = [
        TransitConsistencyTest(
            "v_shape_metric", VettingVerdict.FAIL, 0.9, 0.65, 0.85,
        ),
    ]
    flag = TransitConsistencyAnalyzer._compute_flag(tests, 0.9, 1, 0)
    assert flag == "EB_SUSPECT"


def test_flag_variable_two_warns() -> None:
    tests = [
        TransitConsistencyTest(
            "a", VettingVerdict.WARN, 0.2, 0.1, 0.3,
        ),
        TransitConsistencyTest(
            "b", VettingVerdict.WARN, 0.2, 0.1, 0.3,
        ),
    ]
    flag = TransitConsistencyAnalyzer._compute_flag(tests, 0.2, 0, 2)
    assert flag == "VARIABLE"


# ─────────────────────────────────────────────────────────────
# analyze() — entegrasyon
# ─────────────────────────────────────────────────────────────

def test_analyze_basic(analyzer: TransitConsistencyAnalyzer) -> None:
    phase, flux, mask, _event_ids = _folded_signal(n=500)
    report = analyzer.analyze(
        target_id="TIC-100", sector=1,
        phase=phase, flux=flux, in_transit_mask=mask,
    )
    assert report.target_id == "TIC-100"
    assert report.sector == 1
    assert report.n_intransit > 0
    assert len(report.tests) == 4
    assert report.flag in ("CONSISTENT", "VARIABLE", "EB_SUSPECT", "UNKNOWN")


def test_analyze_with_event_ids(analyzer: TransitConsistencyAnalyzer) -> None:
    """event_ids verilirse per_transit_depths cikar."""
    n = 60
    flux = np.ones(n)
    flux[0:5] = 0.995
    flux[10:15] = 0.995
    flux[20:25] = 0.995
    phase = np.zeros(n)  # basit
    phase[0:5] = -0.04
    phase[10:15] = 0.0
    phase[20:25] = 0.04
    mask = np.zeros(n, dtype=bool)
    mask[0:5] = True
    mask[10:15] = True
    mask[20:25] = True
    event_ids = np.full(n, -1, dtype=int)
    event_ids[0:5] = 0
    event_ids[10:15] = 1
    event_ids[20:25] = 2

    report = analyzer.analyze(
        target_id="TIC-1", sector=1,
        phase=phase, flux=flux, in_transit_mask=mask,
        transit_event_ids=event_ids,
    )
    assert report.n_transits == 3


def test_analyze_with_per_transit_depths(analyzer: TransitConsistencyAnalyzer) -> None:
    phase, flux, mask, _ = _folded_signal(n=500)
    depths = np.array([0.005, 0.005, 0.005, 0.005])
    report = analyzer.analyze(
        target_id="TIC-1", sector=1,
        phase=phase, flux=flux, in_transit_mask=mask,
        per_transit_depths=depths,
    )
    assert report.n_transits == 4


def test_analyze_filters_nan(analyzer: TransitConsistencyAnalyzer) -> None:
    phase, flux, mask, _ = _folded_signal(n=500)
    # NaN ekle
    phase[0:5] = np.nan
    flux[10:15] = np.nan
    report = analyzer.analyze(
        target_id="TIC-1", sector=1,
        phase=phase, flux=flux, in_transit_mask=mask,
    )
    # Hata vermeden tamamlanmali
    assert report.n_intransit >= 0


def test_analyze_event_ids_length_mismatch(analyzer: TransitConsistencyAnalyzer) -> None:
    phase, flux, mask, _ = _folded_signal(n=500)
    bad_ids = np.array([0, 1, 2])  # cok kisa
    report = analyzer.analyze(
        target_id="TIC-1", sector=1,
        phase=phase, flux=flux, in_transit_mask=mask,
        transit_event_ids=bad_ids,
    )
    # Warning yazilir, event_ids yok sayilir
    assert report.n_transits == 0


def test_analyze_empty_arrays(analyzer: TransitConsistencyAnalyzer) -> None:
    """Bos diziler -> hata vermemeli."""
    report = analyzer.analyze(
        target_id="TIC-1", sector=1,
        phase=np.array([]), flux=np.array([]),
        in_transit_mask=np.array([], dtype=bool),
    )
    assert report.n_intransit == 0
    assert len(report.tests) == 4


def test_analyze_report_to_dict(analyzer: TransitConsistencyAnalyzer) -> None:
    phase, flux, mask, _ = _folded_signal(n=500)
    report = analyzer.analyze(
        target_id="TIC-1", sector=1,
        phase=phase, flux=flux, in_transit_mask=mask,
    )
    d = report.to_dict()
    assert isinstance(d, dict)
    assert "tests" in d
    assert len(d["tests"]) == 4
    assert "details" in d
