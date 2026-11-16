"""Kol 2 (L1 kontrollü yapı) skorlayıcı testleri."""

from __future__ import annotations

import pytest

from astrotransit.discovery.l1_structure import L1StructureCandidate, L1StructureScorer
from astrotransit.dynamics.lagrange import M_JUP_KG, M_SUN_KG


@pytest.fixture()
def scorer() -> L1StructureScorer:
    return L1StructureScorer(min_review_score=70.0, max_budget_delta_v_m_per_s=100.0)


def _base_kwargs(**overrides):
    kwargs = dict(
        m_star_kg=1.0 * M_SUN_KG,
        m_planet_kg=1.0 * M_JUP_KG,
        separation_au=5.2,
    )
    kwargs.update(overrides)
    return kwargs


def _strong_stationkeeping_signals(**overrides):
    # lagrange review = 0.45*trojan + 0.20*pp + 0.15*shoulder + 0.10*multi + 0.10*ttv
    kwargs = dict(
        timing_rms_min=45.0,      # ttv = 80
        transit_symmetry=1.0,
        residual_rms_ppm=10.0,
        pre_post_dip_score=95.0,
        shoulder_score=90.0,
        folded_multipeak_score=85.0,
        trojan_signal_score=95.0,
        n_transits=10,
    )
    kwargs.update(overrides)
    return kwargs


def test_controllable_candidate_with_strong_signals(scorer: L1StructureScorer):
    result = scorer.evaluate("TIC 1", **_base_kwargs(), **_strong_stationkeeping_signals())
    assert isinstance(result, L1StructureCandidate)
    assert result.l1_distance_from_planet_au is not None
    assert result.l1_distance_from_planet_au > 0.0
    assert result.stationkeeping_review_score is not None
    assert result.stationkeeping_review_score >= 70.0
    assert result.station_keeping_total_delta_v_m_per_s is not None
    assert result.station_keeping_total_delta_v_m_per_s <= 100.0
    assert result.controllable_candidate is True
    assert any("kontrol kanıtı değil" in note or "follow-up" in note for note in result.rationale)


def test_review_below_threshold_not_controllable(scorer: L1StructureScorer):
    result = scorer.evaluate(
        "TIC 2",
        **_base_kwargs(),
        **_strong_stationkeeping_signals(trojan_signal_score=10.0, pre_post_dip_score=10.0, shoulder_score=10.0, folded_multipeak_score=10.0, timing_rms_min=1.0),
    )
    assert result.stationkeeping_review_score is not None
    assert result.stationkeeping_review_score < 70.0
    assert result.controllable_candidate is False
    assert any("kontrol kanıtı değildir" in note for note in result.rationale)


def test_budget_over_max_not_controllable():
    scorer = L1StructureScorer(min_review_score=70.0, max_budget_delta_v_m_per_s=1e-9)
    result = scorer.evaluate("TIC 3", **_base_kwargs(), **_strong_stationkeeping_signals())
    assert result.station_keeping_total_delta_v_m_per_s is not None
    assert result.station_keeping_total_delta_v_m_per_s > 1e-9
    assert result.controllable_candidate is False
    assert any("bütçe" in note for note in result.rationale)


def test_missing_masses_none_not_zero(scorer: L1StructureScorer):
    result = scorer.evaluate(
        "TIC 4",
        m_star_kg=None,
        m_planet_kg=None,
        separation_au=None,
        **_strong_stationkeeping_signals(),
    )
    assert result.l1_distance_from_planet_au is None
    assert result.station_keeping_total_delta_v_m_per_s is None
    assert result.controllable_candidate is False
    data = result.to_dict()
    assert data["l1_distance_from_planet_au"] is None
    assert data["station_keeping_total_delta_v_m_per_s"] is None


def test_no_signals_not_controllable(scorer: L1StructureScorer):
    result = scorer.evaluate("TIC 5", **_base_kwargs())
    assert result.stationkeeping_review_score is not None
    assert result.stationkeeping_review_score < 70.0
    assert result.controllable_candidate is False


def test_stability_note_present(scorer: L1StructureScorer):
    result = scorer.evaluate("TIC 6", **_base_kwargs(), **_strong_stationkeeping_signals())
    assert result.l1_stability_e_folding_days is not None
    assert any("kararsız" in note for note in result.rationale)


def test_invalid_params_raise():
    with pytest.raises(ValueError):
        L1StructureScorer(min_review_score=150.0)
    with pytest.raises(ValueError):
        L1StructureScorer(max_budget_delta_v_m_per_s=0.0)
