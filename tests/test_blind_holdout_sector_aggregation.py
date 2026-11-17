from __future__ import annotations

import pytest

from scripts.validation.run_blind_holdout import _aggregate_sector_signals
from scripts.validation.run_dev_vetting_eval import _reaggregate_rows


def test_majority_veto_aggregation_rejects_repeated_secondary_eclipse_fails() -> None:
    accepted, details = _aggregate_sector_signals(
        [
            {
                "has_candidate": True,
                "candidate_confirmed": True,
                "vetting_is_false_positive": False,
                "failed_tests": [],
                "candidate_period_days": 1.0,
            },
            {
                "has_candidate": True,
                "candidate_confirmed": True,
                "vetting_is_false_positive": True,
                "failed_tests": ["secondary_eclipse"],
                "candidate_period_days": 1.0,
            },
        ]
    )

    assert accepted is False
    assert details == {
        "rule": "majority_veto_plus_period_consistency",
        "n_candidate_sectors": 2,
        "n_hard_fail_sectors": 1,
        "n_secondary_eclipse_fail_sectors": 1,
        "frac_modal_period": 1.0,
    }


def test_period_inconsistency_vetoes_four_candidate_sectors() -> None:
    signals = [
        {
            "has_candidate": True,
            "candidate_confirmed": True,
            "vetting_is_false_positive": False,
            "failed_tests": [],
            "candidate_period_days": period,
        }
        for period in (1.0, 2.0, 3.0, 4.0)
    ]

    accepted, details = _aggregate_sector_signals(signals)

    assert accepted is False
    assert details["frac_modal_period"] == 0.25


def test_dev_row_reaggregation_requires_exact_manifest_membership() -> None:
    cases = [{"target_id": "100", "label": "planet"}]
    rows = [
        {
            "target_id": "100",
            "label": "planet",
            "error": "",
            "per_sector": [
                {
                    "has_candidate": False,
                    "candidate_confirmed": False,
                    "vetting_tests": [],
                    "candidate_period_days": None,
                }
            ],
        }
    ]

    result = _reaggregate_rows(rows, cases)

    assert result[0]["accepted_candidate"] is False
    assert result[0]["aggregation"] == {"rule": "no_candidate_sectors_fallback"}
    with pytest.raises(ValueError, match="missing targets"):
        _reaggregate_rows([], cases)
