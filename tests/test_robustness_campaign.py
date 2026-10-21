"""run_robustness_campaign koşucusu entegrasyon testleri (mock detector).

Gerçek pipeline kampanyası TESS verisi indirir; burada yalnızca
sözleşme + artefakt şeması doğrulanır. Koşum-bazlı checkpoint sarmalayıcı
(cache / resume) ünite düzeyinde test edilir.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.validation import run_robustness_campaign as runner
from scripts.validation.run_robustness_campaign import (
    _cached_detector_factory,
    _run_fingerprint,
)


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
    assert payload["status"] in {"measured", "measured_fail"}
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


# ── checkpoint sarmalayıcı ünite testleri ──


def test_cached_detector_reuses_result_within_and_across_runs(tmp_path: Path):
    cache_path = tmp_path / "robustness" / "runs_cache.jsonl"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    fingerprint = _run_fingerprint("corpus.json", "pipeline", True)
    calls = {"n": 0}

    def base(case):
        calls["n"] += 1
        return True

    det1 = _cached_detector_factory(base, cache_path=cache_path, fingerprint=fingerprint)
    case_a = {"target_id": "TIC 1001", "sectors": [14, 15], "label": "planet"}
    case_b = {"target_id": "TIC 1001", "sectors": [14, 15], "sectors_override": [14],
              "label": "planet"}
    assert det1(case_a) is True
    assert det1(case_b) is True
    # aynı sektör kümesi → önbellek; farklı → yeni koşum
    assert det1(case_a) is True
    assert calls["n"] == 2
    assert det1(case_b) is True
    assert calls["n"] == 2

    # ikinci fabrika örneği diskten yüklemeli (resume)
    det2 = _cached_detector_factory(base, cache_path=cache_path, fingerprint=fingerprint)
    assert det2(case_a) is True
    assert det2(case_b) is True
    assert calls["n"] == 2  # hiç yeni koşum yok


def test_cached_detector_fingerprint_mismatch_ignored(tmp_path: Path):
    cache_path = tmp_path / "runs_cache.jsonl"
    fp_old = _run_fingerprint("corpus_v1.json", "pipeline", True)
    det1 = _cached_detector_factory(lambda case: False, cache_path=cache_path,
                                    fingerprint=fp_old)
    det1({"target_id": "TIC 2002"})
    fp_new = _run_fingerprint("corpus_v2.json", "pipeline", True)
    calls = {"n": 0}

    def base(case):
        calls["n"] += 1
        return True

    det2 = _cached_detector_factory(base, cache_path=cache_path, fingerprint=fp_new)
    assert det2({"target_id": "TIC 2002"}) is True  # eski kayıt yok sayılır
    assert calls["n"] == 1
