"""run_robustness_campaign koşucusu entegrasyon testleri (mock detector).

Gerçek pipeline kampanyası TESS verisi indirir; burada yalnızca
sözleşme + artefakt şeması doğrulanır.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.validation import run_robustness_campaign as runner


def _write_corpus(tmp_path: Path, n: int) -> Path:
    cases = [
        {
            "target_id": f"TIC {1000 + i}",
            "label": "planet" if i % 2 == 0 else "false_positive",
            "reference": f"reference-{i}",
            "sectors": [14, 15, 16],
        }
        for i in range(n)
    ]
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps({"cases": cases}), encoding="utf-8")
    return path


def test_dry_run_prints_declared_thresholds_without_writing(tmp_path: Path):
    corpus = _write_corpus(tmp_path, 4)
    out = tmp_path / "robustness" / "report.json"
    code = runner.main(
        ["--corpus", str(corpus), "--detector", "mock", "--dry-run", "--output", str(out)]
    )
    assert code == 0
    assert not out.exists()


def test_mock_campaign_writes_measured_artifact(tmp_path: Path):
    corpus = _write_corpus(tmp_path, 6)
    out = tmp_path / "robustness" / "report.json"
    code = runner.main(
        [
            "--corpus", str(corpus),
            "--max-cases", "6",
            "--detector", "mock",
            "--min-cases", "5",
            "--declared-max-recall-drop", "0.05",
            "--output", str(out),
        ]
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert code in (0, 1)  # mock sonucuna göre pass/fail; artefakt her koşuda yazılır
    assert payload["gate"] == "detrending_cadence_impact_robustness"
    assert payload["declared"]["min_cases"] == 5
    assert payload["declared"]["declared_max_recall_drop"] == 0.05
    assert payload["status"] in {"measured_pass", "measured_fail"}
    assert payload["result"]["campaign"]["baseline"]["n_cases"] == 6
    assert len(payload["result"]["campaign"]["measurements"]) == 2
    names = [m["name"] for m in payload["result"]["campaign"]["measurements"]]
    assert names == ["cadence_50pct", "cadence_25pct"]


def test_unsupported_detector_rejected(tmp_path: Path):
    import pytest

    corpus = _write_corpus(tmp_path, 2)
    with pytest.raises(SystemExit) as excinfo:
        runner.main(["--corpus", str(corpus), "--detector", "yok_bir_detector"])
    assert excinfo.value.code == 2  # argparse hata kodu
