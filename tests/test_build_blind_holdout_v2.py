from __future__ import annotations

import pytest

from astrotransit.validation.blind_holdout import select_holdout
from scripts.validation.build_blind_holdout_v2 import _select_with_frozen_sectors


def _labelled_cases() -> list[dict[str, str]]:
    return [
        {
            "target_id": str(900000000 + index),
            "label": "planet" if index % 2 == 0 else "false_positive",
            "reference": (
                "TESS FOP WG disposition 'CP' via snapshot"
                if index % 2 == 0
                else "TESS FOP WG disposition 'FP' via snapshot"
            ),
        }
        for index in range(500)
    ]


def _select(cases: list[dict[str, str]], sector_lookup):
    return _select_with_frozen_sectors(
        cases,
        excluded_ids=set(),
        per_label=6,
        selection_seed=20261120,
        split_seed=13,
        minimum_per_stratum=1,
        max_sectors=2,
        sector_lookup=sector_lookup,
    )


def test_sector_free_targets_are_replaced_without_changing_label_quotas() -> None:
    initial = select_holdout(
        _labelled_cases(),
        per_label=6,
        seed=20261120,
        split_seed=13,
        split="blind_test",
        minimum_per_stratum=1,
    )
    unavailable_target = initial["cases"][0]["target_id"]

    def sector_lookup(target_id: str) -> list[int]:
        return [] if target_id == unavailable_target else [7, 2, 7]

    result, unavailable = _select(_labelled_cases(), sector_lookup)

    assert unavailable == {unavailable_target}
    assert result["counts"] == {"false_positive": 6, "planet": 6}
    assert unavailable_target not in {case["target_id"] for case in result["cases"]}
    assert all(case["sectors"] == [2, 7] for case in result["cases"])
    assert result["stratum_counts"] == initial["stratum_counts"]


def test_sector_lookup_errors_abort_instead_of_becoming_missing_sectors() -> None:
    def sector_lookup(_target_id: str) -> list[int]:
        raise OSError("MAST unavailable")

    with pytest.raises(RuntimeError, match="MAST sector lookup failed"):
        _select(_labelled_cases(), sector_lookup)


def test_frozen_availability_snapshot_reuses_cached_sectors() -> None:
    cases = _labelled_cases()
    initial = select_holdout(
        cases,
        per_label=6,
        seed=20261120,
        split_seed=13,
        split="blind_test",
        minimum_per_stratum=1,
    )
    unavailable_target = initial["cases"][0]["target_id"]
    cached_sectors = {
        case["target_id"]: [2, 7]
        for case in initial["cases"]
        if case["target_id"] != unavailable_target
    }
    queried: list[str] = []

    def sector_lookup(target_id: str) -> list[int]:
        queried.append(target_id)
        return [9]

    result, unavailable = _select_with_frozen_sectors(
        cases,
        excluded_ids=set(),
        per_label=6,
        selection_seed=20261120,
        split_seed=13,
        minimum_per_stratum=1,
        max_sectors=2,
        sector_lookup=sector_lookup,
        cached_sectors=cached_sectors,
        known_unavailable={unavailable_target},
    )

    assert unavailable == {unavailable_target}
    assert len(queried) == 1
    assert all(case["sectors"] for case in result["cases"])
