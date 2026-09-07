"""Earth-like aday keşfi ve önceliklendirme testleri."""

from types import SimpleNamespace

from astrotransit.discovery.earth_search import EarthCandidateRanker


def _record(
    target_id: str,
    status: str,
    similarity: float,
    *,
    completeness: float = 1.0,
    confidence: str = "UNKNOWN",
    fpp: float | None = None,
    search_channel: str = "sector_cascade",
    source_sectors: str = "[]",
):
    return SimpleNamespace(
        source_id=target_id,
        earth_twin_status=status,
        earth_similarity_score=similarity,
        earth_similarity_completeness=completeness,
        detection_confidence=confidence,
        false_positive_probability=fpp,
        search_channel=search_channel,
        source_sectors=source_sectors,
        candidate_class="",
        long_period_identifiability="",
    )


def test_ranker_keeps_similarity_confidence_and_fpp_separate():
    records = [
        _record(
            "TIC 1",
            "photometric_earth_like_candidate",
            95.0,
            completeness=0.7,
            confidence="HIGH",
            fpp=0.02,
        ),
        _record(
            "TIC 2",
            "earth_twin_candidate",
            91.0,
            confidence="MEDIUM",
            fpp=0.10,
        ),
    ]

    ranked = EarthCandidateRanker().rank(records)

    assert len(ranked) == 2
    assert ranked[0].target_id == "TIC 1"
    assert ranked[0].similarity_score == 95.0
    assert ranked[0].detection_confidence == "HIGH"
    assert ranked[0].false_positive_probability == 0.02
    assert ranked[0].category_label == "Photometric Earth-like candidate"
    assert ranked[0].priority_score != ranked[0].similarity_score


def test_ranker_deduplicates_target_using_best_record():
    records = [
        _record("TIC 1", "photometric_earth_like_candidate", 94.0, confidence="LOW"),
        _record("TIC 1", "earth_twin_candidate", 90.5, confidence="HIGH"),
        _record("TIC 3", "photometric_earth_like_candidate", 89.9),
    ]

    ranked = EarthCandidateRanker().rank(records)

    assert [item.target_id for item in ranked] == ["TIC 1"]
    assert ranked[0].candidate_category == "earth_twin_candidate"


def test_ranker_supports_legacy_class_and_long_period_provenance():
    record = SimpleNamespace(
        source_id="TIC 40",
        earth_analog_class="PHOTOMETRIC_EARTH_ANALOG",
        earth_twin_status="",
        earth_similarity_score=92.0,
        earth_similarity_completeness=0.75,
        detection_confidence="UNKNOWN",
        false_positive_probability=None,
        search_channel="long_period",
        source_sectors="[14, 40]",
        candidate_class="LONG_PERIOD_SINGLE_TRANSIT",
        long_period_identifiability="single_transit_ambiguous",
    )

    ranked = EarthCandidateRanker().rank([record])

    assert ranked[0].candidate_category == "photometric_earth_like_candidate"
    assert ranked[0].search_channel == "long_period"
    assert ranked[0].source_sectors == (14, 40)
    assert ranked[0].long_period_identifiability == "single_transit_ambiguous"
