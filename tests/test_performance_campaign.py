"""run_performance_campaign koşucusu entegrasyon testleri (hafif operasyonlar)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.validation import run_performance_campaign as runner


def test_noop_operates_and_declares(tmp_path: Path):
    out = tmp_path / "performance" / "report.json"
    code = runner.main(
        [
            "--op", "noop",
            "--repeat", "2",
            "--declared-max-seconds-per-1k-rows", "10",
            "--output", str(out),
        ]
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0  # noop her zaman hızlıdır
    assert payload["gate"] == "performance"
    assert payload["status"] == "measured"
    assert payload["declared"]["declared_max_seconds_per_1k_rows"] == 10
    assert payload["result"]["median_seconds"] >= 0
    assert len(payload["result"]["measurements"]) == 2


def test_csv_read_runs_and_writes_artifact(tmp_path: Path):
    csv = tmp_path / "rows.csv"
    csv.write_text("a,b\n" + "".join(f"{i},{i * 2}\n" for i in range(50)), encoding="utf-8")
    out = tmp_path / "performance" / "report.json"
    code = runner.main(
        [
            "--op", "csv-read",
            "--input", str(csv),
            "--repeat", "1",
            "--declared-max-seconds-per-1k-rows", "1000",
            "--output", str(out),
        ]
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["result"]["rows_operated"] == 51  # halter + 50 satır


def test_missing_input_rejected(tmp_path: Path):
    out = tmp_path / "performance" / "report.json"
    code = runner.main(
        ["--op", "csv-read", "--input", str(tmp_path / "yok.csv"), "--output", str(out)]
    )
    assert code == 2
    assert not out.exists()
