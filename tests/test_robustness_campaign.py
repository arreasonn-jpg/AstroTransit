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
    _build_task_list,
    _cached_detector_factory,
    _precomputed_detector,
    _run_fingerprint,
    _task_key,
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


# ── paralel görev planlama + önceden hesaplanmış detector testleri ──


def test_task_key_override_vs_all(tmp_path: Path):
    assert _task_key({"target_id": "TIC 1001"}) == "1001|ALL"
    assert _task_key({"target_id": "TIC 1001", "sectors": [14, 15]}) == "1001|ALL"
    assert _task_key({"target_id": "TIC 1001", "sectors_override": [14]}) == "1001|14"
    assert _task_key({"target_id": "TIC 1001", "sectors_override": [14, 15]}) == "1001|14,15"


def test_build_task_list_dedupes_and_orders_variants():
    cases = [
        {"target_id": "TIC 1", "label": "planet", "sectors": [14, 15, 16, 17]},
        {"target_id": "TIC 2", "label": "false_positive", "sectors": []},
    ]
    tasks = _build_task_list(cases, runner._perturbations())
    keys = [key for key, _ in tasks]
    # 4-sektörlü vaka: baseline + 2 farklı alt küme = 3 tekil görev
    assert keys[:3] == ["1|ALL", "1|14,15", "1|14"]
    # 1-sektörlü vaka: tüm varyantlar aynı anahtara çöker → tek görev
    assert keys[3:] == ["2|ALL"]
    assert len(tasks) == 4


def test_precomputed_detector_uses_cache_and_rejects_missing():
    results = {"1|ALL": True, "1|14,15": False}
    detector = _precomputed_detector(results)
    assert detector({"target_id": "TIC 1"}) is True
    assert detector({"target_id": "TIC 1", "sectors_override": [14, 15]}) is False
    import pytest

    with pytest.raises(RuntimeError):
        detector({"target_id": "TIC 9"})


def test_parallel_path_with_mock_detector_end_to_end(tmp_path: Path):
    """Paralel yol küçük görev kümesiyle uçtan uca (çalışan işçiler fork)."""

    import pytest  # noqa: F401

    cases = [
        {
            "target_id": f"TIC {3000 + i}",
            "label": "planet" if i % 2 == 0 else "false_positive",
            "reference": f"reference-{i}",
            "sectors": [14, 15, 16, 17],
        }
        for i in range(3)
    ]
    corpus = tmp_path / "corpus.json"
    corpus.write_text(json.dumps({"cases": cases}), encoding="utf-8")
    out = tmp_path / "robustness" / "report.json"
    code = runner.main(
        [
            "--corpus", str(corpus),
            "--max-cases", "3",
            "--detector", "mock",
            "--min-cases", "3",
            "--workers", "2",
            "--mp-method", "fork",
            "--output", str(out),
        ]
    )
    assert code in (0, 1)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] in {"measured", "measured_fail"}
    assert payload["declared"]["workers"] == 2
    # 3 vaka × 3 varyant (sektörler dolu → 9 tekil görev) — hepsi önbellekte
    # mock için paralel yol, _build_task_list + önceden hesaplanmış detector
    # kullanır; ölçüm sonuçları seri yolla birebir aynı olmalı:
    assert payload["result"]["campaign"]["baseline"]["n_cases"] == 3
