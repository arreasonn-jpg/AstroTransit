"""astrotransit/discovery/earth_search.py için kapsamlı testler."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from astrotransit.discovery.earth_search import (
    _CONFIDENCE_SCORE,
    _STATUS_LABELS,
    _STATUS_PRIORITY,
    EarthCandidatePriority,
    EarthCandidateRanker,
    EarthSearchSummary,
)

# ═══════════════════════════════════════════════════════
# Sabitler
# ═══════════════════════════════════════════════════════

def test_constants_keys_match():
    assert set(_STATUS_LABELS) == set(_STATUS_PRIORITY)
    assert "HIGH" in _CONFIDENCE_SCORE
    assert "UNKNOWN" in _CONFIDENCE_SCORE


# ═══════════════════════════════════════════════════════
# EarthCandidatePriority
# ═══════════════════════════════════════════════════════

def _priority(**over):
    base = dict(
        target_id="TIC 1", candidate_category="earth_twin_candidate",
        category_label="Earth-twin candidate", similarity_score=92.0,
        similarity_p05=88.0, similarity_p95=95.0,
        similarity_completeness=0.9, detection_confidence="HIGH",
        false_positive_probability=0.05, priority_score=88.5,
        search_channel="sector_cascade", source_sectors=(1, 2),
        candidate_class="A", long_period_identifiability="multi_transit",
        rationale=("similarity=92.0/100",),
    )
    base.update(over)
    return EarthCandidatePriority(**base)


def test_priority_to_dict():
    p = _priority()
    d = p.to_dict()
    assert d["target_id"] == "TIC 1"
    assert d["similarity_score"] == 92.0
    assert d["source_sectors"] == [1, 2]
    assert d["rationale"] == ["similarity=92.0/100"]


def test_priority_defaults():
    p = EarthCandidatePriority(
        target_id="T", candidate_category="c",
        category_label="l", similarity_score=90.0,
        similarity_p05=85.0, similarity_p95=95.0,
        similarity_completeness=1.0, detection_confidence="HIGH",
        false_positive_probability=None, priority_score=80.0,
        search_channel="s",
    )
    assert p.source_sectors == ()
    assert p.candidate_class == ""
    assert p.rationale == ()


# ═══════════════════════════════════════════════════════
# EarthSearchSummary
# ═══════════════════════════════════════════════════════

def test_summary_to_dict():
    s = EarthSearchSummary(
        n_targets=10, n_records=20, n_ranked_candidates=1,
        ranked_candidates=(_priority(),),
    )
    d = s.to_dict()
    assert d["n_targets"] == 10
    assert d["n_records"] == 20
    assert len(d["ranked_candidates"]) == 1


def test_summary_write_json(tmp_path):
    s = EarthSearchSummary(
        n_targets=1, n_records=1, n_ranked_candidates=1,
        ranked_candidates=(_priority(),),
    )
    out = s.write_json(tmp_path / "sub" / "s.json")
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["n_targets"] == 1


# ═══════════════════════════════════════════════════════
# __init__
# ═══════════════════════════════════════════════════════

def test_init_default():
    r = EarthCandidateRanker()
    assert r.min_similarity == 90.0
    assert r.include_incomplete is False
    assert r.deduplicate_targets is True


def test_init_custom():
    r = EarthCandidateRanker(
        min_similarity=70.0, include_incomplete=True, deduplicate_targets=False,
    )
    assert r.min_similarity == 70.0
    assert r.include_incomplete is True


def test_init_min_similarity_out_of_range():
    with pytest.raises(ValueError, match="0 ile 100"):
        EarthCandidateRanker(min_similarity=-1.0)
    with pytest.raises(ValueError, match="0 ile 100"):
        EarthCandidateRanker(min_similarity=101.0)


# ═══════════════════════════════════════════════════════
# _value / _target_id / _float / _optional_probability
# ═══════════════════════════════════════════════════════

def test_value_dict():
    assert EarthCandidateRanker._value({"a": 1}, "a") == 1
    assert EarthCandidateRanker._value({"a": 1}, "b", 99) == 99


def test_value_object():
    obj = SimpleNamespace(a=5)
    assert EarthCandidateRanker._value(obj, "a") == 5
    assert EarthCandidateRanker._value(obj, "b", 99) == 99


def test_target_id_source_id():
    r = EarthCandidateRanker()
    assert r._target_id({"source_id": "TIC 1"}) == "TIC 1"


def test_target_id_fallback():
    r = EarthCandidateRanker()
    assert r._target_id({"target_id": "TIC 2"}) == "TIC 2"


def test_target_id_empty():
    r = EarthCandidateRanker()
    assert r._target_id({}) == ""


def test_float_ok():
    r = EarthCandidateRanker()
    assert r._float({"x": 3.5}, "x", 0.0) == 3.5


def test_float_invalid():
    r = EarthCandidateRanker()
    assert r._float({"x": "bad"}, "x", 1.0) == 1.0


def test_float_nan():
    r = EarthCandidateRanker()
    assert r._float({"x": float("nan")}, "x", 1.0) == 1.0


def test_optional_probability_none():
    r = EarthCandidateRanker()
    assert r._optional_probability({}) is None


def test_optional_probability_via_fpp_field():
    r = EarthCandidateRanker()
    assert r._optional_probability({"fpp": 0.1}) == 0.1


def test_optional_probability_invalid():
    r = EarthCandidateRanker()
    assert r._optional_probability({"false_positive_probability": "bad"}) is None


def test_optional_probability_out_of_range():
    r = EarthCandidateRanker()
    assert r._optional_probability({"false_positive_probability": -0.1}) is None
    assert r._optional_probability({"false_positive_probability": 1.5}) is None


def test_source_sectors_list():
    r = EarthCandidateRanker()
    assert r._source_sectors({"source_sectors": [1, 2, 3]}) == (1, 2, 3)


def test_source_sectors_json_string():
    r = EarthCandidateRanker()
    assert r._source_sectors({"source_sectors": "[4, 5]"}) == (4, 5)


def test_source_sectors_bad_json():
    r = EarthCandidateRanker()
    assert r._source_sectors({"source_sectors": "not json"}) == ()


def test_source_sectors_invalid_types():
    r = EarthCandidateRanker()
    assert r._source_sectors({"source_sectors": ["a", "b"]}) == ()


def test_source_sectors_missing():
    r = EarthCandidateRanker()
    assert r._source_sectors({}) == ()


# ═══════════════════════════════════════════════════════
# _category
# ═══════════════════════════════════════════════════════

def test_category_direct_status():
    r = EarthCandidateRanker()
    assert r._category({"earth_twin_status": "earth_twin_candidate"}) == "earth_twin_candidate"


def test_category_legacy_earth_analog_class():
    r = EarthCandidateRanker()
    assert r._category({"earth_analog_class": "EARTH_TWIN_CANDIDATE"}) == "earth_twin_candidate"


def test_category_legacy_photometric():
    r = EarthCandidateRanker()
    assert r._category({"earth_analog_class": "PHOTOMETRIC_EARTH_ANALOG"}) == "photometric_earth_like_candidate"


def test_category_legacy_confirmed():
    r = EarthCandidateRanker()
    assert r._category({"earth_analog_class": "CONFIRMED_EARTH_TWIN"}) == "confirmed_earth_twin"


def test_category_unknown():
    r = EarthCandidateRanker()
    assert r._category({"earth_twin_status": "unknown"}) is None


def test_category_empty():
    r = EarthCandidateRanker()
    assert r._category({}) is None


def test_category_incomplete_with_include():
    r = EarthCandidateRanker(include_incomplete=True)
    assert r._category({"earth_twin_status": "incomplete_earth_twin"}) == "photometric_earth_like_candidate"


def test_category_incomplete_without_include():
    r = EarthCandidateRanker(include_incomplete=False)
    assert r._category({"earth_twin_status": "incomplete_earth_twin"}) is None


# ═══════════════════════════════════════════════════════
# _build_priority
# ═══════════════════════════════════════════════════════

def _full_record(**over):
    base = {
        "source_id": "TIC 1",
        "earth_twin_status": "earth_twin_candidate",
        "earth_similarity_score": 92.0,
        "earth_similarity_p05": 88.0,
        "earth_similarity_p95": 96.0,
        "earth_similarity_completeness": 0.9,
        "detection_confidence": "HIGH",
        "false_positive_probability": 0.05,
        "search_channel": "sector_cascade",
        "source_sectors": [1, 2],
        "candidate_class": "A",
    }
    base.update(over)
    return base


def test_build_priority_full():
    r = EarthCandidateRanker()
    p = r._build_priority(_full_record())
    assert p is not None
    assert p.target_id == "TIC 1"
    assert p.similarity_score == 92.0
    assert p.detection_confidence == "HIGH"
    assert p.false_positive_probability == 0.05
    assert p.source_sectors == (1, 2)


def test_build_priority_no_category():
    r = EarthCandidateRanker()
    assert r._build_priority({}) is None


def test_build_priority_below_similarity():
    r = EarthCandidateRanker(min_similarity=95.0)
    assert r._build_priority(_full_record(earth_similarity_score=90.0)) is None


def test_build_priority_no_fpp():
    r = EarthCandidateRanker()
    p = r._build_priority(_full_record(false_positive_probability=None))
    assert p is not None
    assert p.false_positive_probability is None
    assert any("FPP=unknown" in x for x in p.rationale)


def test_build_priority_fpp_from_alias():
    rec = _full_record()
    del rec["false_positive_probability"]
    rec["fpp"] = 0.1
    r = EarthCandidateRanker()
    p = r._build_priority(rec)
    assert p.false_positive_probability == 0.1


def test_build_priority_rationale_low_p05():
    r = EarthCandidateRanker()
    p = r._build_priority(_full_record(
        earth_similarity_score=92.0, earth_similarity_p05=85.0,
    ))
    assert any("similarity_p05" in x for x in p.rationale)


def test_build_priority_rationale_incomplete():
    r = EarthCandidateRanker()
    p = r._build_priority(_full_record(earth_similarity_completeness=0.6))
    assert any("measurement_completeness" in x for x in p.rationale)


def test_build_priority_completeness_clipped():
    r = EarthCandidateRanker()
    p = r._build_priority(_full_record(earth_similarity_completeness=1.5))
    assert p.similarity_completeness == 1.0


def test_build_priority_unknown_confidence():
    r = EarthCandidateRanker()
    p = r._build_priority(_full_record(detection_confidence="WEIRD"))
    assert p.detection_confidence == "WEIRD"


def test_build_priority_missing_confidence():
    rec = _full_record()
    del rec["detection_confidence"]
    r = EarthCandidateRanker()
    p = r._build_priority(rec)
    assert p.detection_confidence == "UNKNOWN"


def test_build_priority_priority_score_bounded():
    r = EarthCandidateRanker()
    p = r._build_priority(_full_record())
    assert 0.0 <= p.priority_score <= 100.0


# ═══════════════════════════════════════════════════════
# _sort_key
# ═══════════════════════════════════════════════════════

def test_sort_key_higher_priority_first():
    a = _priority(priority_score=90.0)
    b = _priority(priority_score=50.0)
    assert EarthCandidateRanker._sort_key(a) < EarthCandidateRanker._sort_key(b)


def test_sort_key_similarity_tiebreak():
    a = _priority(priority_score=90.0, similarity_score=95.0)
    b = _priority(priority_score=90.0, similarity_score=80.0)
    assert EarthCandidateRanker._sort_key(a) < EarthCandidateRanker._sort_key(b)


def test_sort_key_fpp_tiebreak():
    a = _priority(priority_score=90.0, similarity_score=95.0,
                  false_positive_probability=0.01)
    b = _priority(priority_score=90.0, similarity_score=95.0,
                  false_positive_probability=0.5)
    assert EarthCandidateRanker._sort_key(a) < EarthCandidateRanker._sort_key(b)


def test_sort_key_fpp_none_treated_as_1():
    a = _priority(priority_score=90.0, similarity_score=95.0,
                  false_positive_probability=0.01)
    b = _priority(priority_score=90.0, similarity_score=95.0,
                  false_positive_probability=None)
    assert EarthCandidateRanker._sort_key(a) < EarthCandidateRanker._sort_key(b)


# ═══════════════════════════════════════════════════════
# rank
# ═══════════════════════════════════════════════════════

def test_rank_empty():
    r = EarthCandidateRanker()
    assert r.rank([]) == []


def test_rank_filters_by_similarity():
    records = [
        _full_record(source_id="TIC 1", earth_similarity_score=95.0),
        _full_record(source_id="TIC 2", earth_similarity_score=50.0),
    ]
    r = EarthCandidateRanker(min_similarity=90.0)
    result = r.rank(records)
    assert len(result) == 1
    assert result[0].target_id == "TIC 1"


def test_rank_deduplicate_by_target():
    records = [
        _full_record(source_id="TIC 1", earth_similarity_score=95.0),
        _full_record(source_id="TIC 1", earth_similarity_score=91.0),
    ]
    r = EarthCandidateRanker(deduplicate_targets=True)
    result = r.rank(records)
    assert len(result) == 1
    assert result[0].similarity_score == 95.0


def test_rank_no_deduplicate():
    records = [
        _full_record(source_id="TIC 1", earth_similarity_score=95.0),
        _full_record(source_id="TIC 1", earth_similarity_score=91.0),
    ]
    r = EarthCandidateRanker(deduplicate_targets=False)
    result = r.rank(records)
    assert len(result) == 2


def test_rank_sorted_descending():
    records = [
        _full_record(source_id="TIC 1", earth_similarity_score=91.0),
        _full_record(source_id="TIC 2", earth_similarity_score=99.0),
        _full_record(source_id="TIC 3", earth_similarity_score=95.0),
    ]
    r = EarthCandidateRanker()
    result = r.rank(records)
    scores = [p.similarity_score for p in result]
    assert scores == sorted(scores, reverse=True)


# ═══════════════════════════════════════════════════════
# summarize
# ═══════════════════════════════════════════════════════

def test_summarize_defaults():
    records = [_full_record(source_id="TIC 1")]
    r = EarthCandidateRanker()
    s = r.summarize(records)
    assert isinstance(s, EarthSearchSummary)
    assert s.n_targets == 1
    assert s.n_records == 1
    assert s.n_ranked_candidates == 1


def test_summarize_n_targets_override():
    records = [_full_record(source_id="TIC 1")]
    r = EarthCandidateRanker()
    s = r.summarize(records, n_targets=99)
    assert s.n_targets == 99


# ═══════════════════════════════════════════════════════
# records_from_target_results
# ═══════════════════════════════════════════════════════

def test_records_from_target_results_empty():
    assert EarthCandidateRanker.records_from_target_results([]) == []


def test_records_from_sector_results():
    rec1 = {"source_id": "TIC 1"}
    rec2 = {"source_id": "TIC 2"}
    target = SimpleNamespace(
        sector_results=[
            SimpleNamespace(record=rec1),
            SimpleNamespace(record=rec2),
        ],
        long_period_record=None,
    )
    out = EarthCandidateRanker.records_from_target_results([target])
    assert len(out) == 2


def test_records_from_long_period():
    lp = {"source_id": "TIC LP"}
    target = SimpleNamespace(
        sector_results=[],
        long_period_record=lp,
    )
    out = EarthCandidateRanker.records_from_target_results([target])
    assert out == [lp]


def test_records_from_skips_none_record():
    target = SimpleNamespace(
        sector_results=[SimpleNamespace(record=None)],
        long_period_record=None,
    )
    out = EarthCandidateRanker.records_from_target_results([target])
    assert out == []


def test_records_from_both():
    rec = {"source_id": "TIC 1"}
    lp = {"source_id": "TIC LP"}
    target = SimpleNamespace(
        sector_results=[SimpleNamespace(record=rec)],
        long_period_record=lp,
    )
    out = EarthCandidateRanker.records_from_target_results([target])
    assert len(out) == 2


# ═══════════════════════════════════════════════════════
# rank_target_results
# ═══════════════════════════════════════════════════════

def test_rank_target_results():
    rec = _full_record(source_id="TIC 1")
    target = SimpleNamespace(
        sector_results=[SimpleNamespace(record=rec)],
        long_period_record=None,
    )
    r = EarthCandidateRanker()
    result = r.rank_target_results([target])
    assert len(result) == 1
    assert result[0].target_id == "TIC 1"


# ═══════════════════════════════════════════════════════
# p05 >= similarity (212->214 branch)
# ═══════════════════════════════════════════════════════

def test_build_priority_p05_equal_similarity():
    """p05 >= similarity ise rationale'da p05 satırı eklenmez (212->214)."""
    r = EarthCandidateRanker()
    p = r._build_priority(_full_record(
        earth_similarity_score=92.0,
        earth_similarity_p05=92.0,  # eşit → skip branch
    ))
    assert p is not None
    assert not any("similarity_p05=" in x for x in p.rationale)


def test_build_priority_p05_greater_than_similarity():
    """p05 > similarity ise de rationale'da p05 satırı eklenmez."""
    r = EarthCandidateRanker()
    p = r._build_priority(_full_record(
        earth_similarity_score=90.0,
        earth_similarity_p05=93.0,
    ))
    assert p is not None
    assert not any("similarity_p05=" in x for x in p.rationale)
