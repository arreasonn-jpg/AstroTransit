from __future__ import annotations

import json
from pathlib import Path

from scripts.validation.run_false_positive_controls import aggregate_shards


def _row(index: int, label: str) -> dict:
    return {
        "target_id": f"TIC {index}",
        "label": label,
        "reference": "independent label",
        "requested_sectors": [1],
        "sector_source": "test",
        "processed_sectors": [1],
        "successful_sector_count": 1,
        "evaluated": True,
        "accepted_candidate": index % 2 == 0,
        "candidate_count": int(index % 2 == 0),
        "error": "",
        "sector_results": [],
    }


def _write_shards(tmp_path: Path, rows: list[dict]) -> None:
    metadata = {
        "false_positive_count": 100,
        "quiet_control_count": 100,
        "quiet_control_sha256": "a59e245487fc80e440fb9481734cf1f95e8778433de2b2ab9abe58f258974aea",
        "quiet_detector_used_for_selection": False,
        "quiet_eligible_count": 283,
    }
    for shard_index in range(20):
        selected = [
            row for index, row in enumerate(rows) if index % 20 == shard_index
        ]
        payload = {
            "schema_version": "1.0",
            "campaign": "labelled_fp_quiet_controls_v1",
            "shard_index": shard_index,
            "shard_count": 20,
            "case_count": len(selected),
            "metadata": metadata,
            "rows": selected,
        }
        (tmp_path / f"shard-{shard_index:02d}.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )


def _complete_rows() -> list[dict]:
    return [
        *[_row(i, "false_positive") for i in range(100)],
        *[_row(100 + i, "quiet_star") for i in range(100)],
    ]


def test_aggregate_requires_complete_unique_measured_rows(tmp_path: Path) -> None:
    _write_shards(tmp_path, _complete_rows())

    report, combined = aggregate_shards(tmp_path, 20)

    assert len(combined) == 200
    assert report["corpora"]["false_positives"]["labelled_count"] == 100
    assert report["corpora"]["quiet_controls"]["labelled_count"] == 100
    assert report["corpora"]["quiet_controls"]["detector_used_for_selection"] is False
    assert report["evaluation"]["false_positives"]["evaluated_count"] == 100
    assert report["evaluation"]["quiet_controls"]["evaluated_count"] == 100
    assert report["evaluation"]["total_errors"] == 0
    assert report["evaluation"]["acceptance_ready"] is True


def test_aggregate_keeps_unevaluated_case_out_of_denominator(tmp_path: Path) -> None:
    rows = _complete_rows()
    rows[0]["evaluated"] = False
    rows[0]["accepted_candidate"] = None
    rows[0]["candidate_count"] = None
    rows[0]["error"] = "no data"
    _write_shards(tmp_path, rows)

    report, _ = aggregate_shards(tmp_path, 20)

    assert report["evaluation"]["false_positives"]["evaluated_count"] == 99
    assert report["evaluation"]["total_errors"] == 1
    assert report["evaluation"]["acceptance_ready"] is False
