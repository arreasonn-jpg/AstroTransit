"""Sade TLS/BLS kural ünite testleri (sentetik geçişler)."""

from __future__ import annotations

import json
import time
from http.client import RemoteDisconnected
from pathlib import Path

import numpy as np
import pytest
from astropy import units as u
from astropy.timeseries import BoxLeastSquares

from scripts.validation import run_baselines_ablations as runner


def _synthetic_lc(period: float, depth: float = 0.02, n: int = 2000, span: float = 30.0,
                  noise: float = 1e-4, dur_frac: float = 0.04, rng_seed: int = 7):
    rng = np.random.default_rng(rng_seed)
    t = np.sort(rng.uniform(0.0, span, n))
    flux = np.ones(n)
    phase = (t / period) - np.floor(t / period)
    mask = phase < dur_frac
    flux[mask] = 1.0 - depth
    err = np.full(n, noise)
    flux = flux + rng.normal(0.0, noise, n)
    return type("LC", (), {"time": t * u.day, "flux": flux * u.dimensionless_unscaled,
                           "flux_err": err * u.dimensionless_unscaled})()


def test_bls_rule_detects_synthetic_transit():
    lc = _synthetic_lc(period=2.0)
    assert runner._bls_detect(lc) is True


def test_bls_rule_ignores_flat_noise():
    lc = _synthetic_lc(period=2.0, depth=0.0)
    assert runner._bls_detect(lc) is False


def test_bls_period_chunks_match_astropy_autoperiod():
    time = np.linspace(0.0, 30.0, 500)
    durations = np.array([1.0, 2.0, 3.0, 4.0]) / 24.0
    bls = BoxLeastSquares(time, np.ones_like(time))
    expected = bls.autoperiod(
        durations,
        minimum_period=runner.BLS_RULE["period_min"],
        maximum_period=runner.BLS_RULE["period_max"],
    )

    chunks = list(
        runner._iter_bls_period_chunks(
            time,
            durations,
            runner.BLS_RULE["period_min"],
            runner.BLS_RULE["period_max"],
            chunk_size=8192,
        )
    )

    assert len(chunks) > 1
    np.testing.assert_allclose(
        np.concatenate([periods for _, periods in chunks]),
        expected,
        rtol=1e-14,
    )


def test_bls_checkpoint_resumes_without_reusing_another_run(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "BLS_PERIOD_CHUNK_SIZE", 8192)
    checkpoint = tmp_path / "bls_progress.json"
    lc = _synthetic_lc(period=2.0)

    with pytest.raises(runner.BaselineBatchPaused):
        runner._bls_detect(
            lc,
            checkpoint_path=checkpoint,
            checkpoint_fingerprint="fingerprint-a",
            checkpoint_key="bls|100|ALL",
            deadline=time.monotonic() - 1,
        )

    assert checkpoint.exists()
    with pytest.raises(ValueError, match="does not match"):
        runner._bls_detect(
            lc,
            checkpoint_path=checkpoint,
            checkpoint_fingerprint="fingerprint-b",
            checkpoint_key="bls|100|ALL",
        )

    assert runner._bls_detect(
        lc,
        checkpoint_path=checkpoint,
        checkpoint_fingerprint="fingerprint-a",
        checkpoint_key="bls|100|ALL",
    )
    assert not checkpoint.exists()


def test_tls_rule_detects_synthetic_transit(monkeypatch):
    rule = dict(runner.TLS_RULE)
    rule["period_max"] = 6.0  # test: daraltılmış pencere ürünü değil, kural parametresi
    monkeypatch.setattr(runner, "TLS_RULE", rule)
    lc = _synthetic_lc(period=2.0, noise=5e-5)
    assert runner._tls_detect(lc) is True


def test_robustness_cache_filtering(tmp_path: Path):
    cache = tmp_path / "runs_cache.jsonl"
    rows = [
        {"fingerprint": "aaa", "key": "100|ALL", "detected": True},
        {"fingerprint": "bbb", "key": "100|ALL", "detected": False},
        {"fingerprint": "aaa", "key": "200|ALL", "detected": False},
        {"fingerprint": "aaa", "key": "200|1,2", "detected": True},
    ]
    cache.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(runner, "ROBUSTNESS_CACHE", cache)
        results = runner._load_robustness_cache("aaa")
    assert results == {"100": True, "200": False}  # ALL anahtarları, yanlış fingerprint filtreli


def test_pipeline_rows_match_targets_labels_and_decisions(tmp_path: Path):
    rows_path = tmp_path / "pipeline_rows.json"
    rows_path.write_text(
        json.dumps(
            {
                "rows": [
                    {"target_id": "100", "label": "planet", "accepted_candidate": True, "error": ""},
                    {
                        "target_id": "200",
                        "label": "false_positive",
                        "accepted_candidate": False,
                        "error": "",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    cases = [
        {"target_id": "100", "label": "planet"},
        {"target_id": "200", "label": "false_positive"},
    ]

    assert runner._load_pipeline_rows(rows_path, cases) == {"100": True, "200": False}


@pytest.mark.parametrize(
    "rows, message",
    [
        ([{"target_id": "100", "label": "planet", "accepted_candidate": True}], "missing targets"),
        (
            [
                {"target_id": "100", "label": "planet", "accepted_candidate": True},
                {
                    "target_id": "200",
                    "label": "false_positive",
                    "accepted_candidate": True,
                    "error": "failed",
                },
            ],
            "evaluation failed",
        ),
        (
            [
                {"target_id": "100", "label": "planet", "accepted_candidate": True},
                {"target_id": "200", "label": "planet", "accepted_candidate": False},
            ],
            "label mismatch",
        ),
    ],
)
def test_pipeline_rows_reject_incomplete_or_invalid_evidence(
    tmp_path: Path, rows: list[dict], message: str
):
    rows_path = tmp_path / "pipeline_rows.json"
    rows_path.write_text(json.dumps({"rows": rows}), encoding="utf-8")
    cases = [
        {"target_id": "100", "label": "planet"},
        {"target_id": "200", "label": "false_positive"},
    ]

    with pytest.raises(ValueError, match=message):
        runner._load_pipeline_rows(rows_path, cases)


def test_baseline_fingerprint_depends_on_rules(tmp_path):
    corpus = tmp_path / "corpus.json"
    corpus.write_text('{"cases": []}', encoding="utf-8")
    a = runner.baseline_fingerprint(str(corpus), "v1")
    b = runner.baseline_fingerprint(str(corpus), "v2")
    assert a != b
    assert runner.baseline_fingerprint(str(corpus), "v1") == a  # deterministik


def test_baseline_fingerprint_depends_on_oversampling_factor(tmp_path):
    corpus = tmp_path / "corpus.json"
    corpus.write_text('{"cases": []}', encoding="utf-8")
    a = runner.baseline_fingerprint(str(corpus), "v1", 3.0)
    b = runner.baseline_fingerprint(str(corpus), "v1", 1.0)
    assert a != b  # coarse-scan farklı kanıt alanıdır
    c = runner.baseline_fingerprint(str(corpus), "v1", 3.0)
    assert a == c  # deterministik


def test_baseline_fingerprint_is_path_independent(tmp_path):
    """Aynı içerik farklı path'te aynı parmak izi: Colab/Windows uyumu."""

    a_dir = tmp_path / "windows_style"
    b_dir = tmp_path / "colab_mount"
    a_dir.mkdir()
    b_dir.mkdir()
    (a_dir / "corpus.json").write_text('{"cases": [1]}', encoding="utf-8")
    (b_dir / "corpus.json").write_text('{"cases": [1]}', encoding="utf-8")
    fp_a = runner.baseline_fingerprint(str(a_dir / "corpus.json"), "v1")
    fp_b = runner.baseline_fingerprint(str(b_dir / "corpus.json"), "v1")
    assert fp_a == fp_b
    (b_dir / "corpus.json").write_text('{"cases": [2]}', encoding="utf-8")
    assert runner.baseline_fingerprint(str(b_dir / "corpus.json"), "v1") != fp_a


def test_runner_alive_does_not_require_procfs_on_windows(monkeypatch):
    monkeypatch.setattr(runner.sys, "platform", "win32")
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: type("Result", (), {"stdout": '"python.exe","123","Console","1","1,000 K"\n'})(),
    )
    assert runner._runner_alive(123)


def test_runner_alive_recognizes_missing_windows_process(monkeypatch):
    monkeypatch.setattr(runner.sys, "platform", "win32")
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: type(
            "Result", (), {"stdout": "INFO: No tasks are running which match the specified criteria.\n"}
        )(),
    )
    assert not runner._runner_alive(123)


def test_read_cache_skips_incomplete_rows(tmp_path: Path):
    cache = tmp_path / "runs_cache.jsonl"
    rows = [
        {"fingerprint": "fp", "key": "tls|100|ALL", "detected": True},
        {"fingerprint": "fp", "key": "tls|200|ALL", "detected": False, "status": "timed_out"},
        {"fingerprint": "fp", "key": "tls|300|ALL", "detected": False, "status": "error"},
        {"fingerprint": "fp", "key": "tls|400|ALL", "detected": False},
    ]
    cache.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert runner._read_cache(cache, "fp") == {"tls|100|ALL": True, "tls|400|ALL": False}


def test_download_network_retry_recovers(monkeypatch):
    """Ağ bölmesi ilk iki denemede düşer, üçüncüde toparlanır — zehirsiz."""

    import scripts.validation.run_baselines_ablations as mod

    calls: list[int] = []

    def flaky(_search, _idx):
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError(("Connection aborted.", RemoteDisconnected()))
        return "ok"

    monkeypatch.setattr(mod, "_download_with_corrupt_retry", flaky)
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)  # bekleme yok (test)
    assert mod._download_with_network_retry(None, 0) == "ok"
    assert len(calls) == 3


def test_download_network_retry_exhausts(monkeypatch):
    """Tükenen ağ zehri hâlâ 'error' görevine yol açar (çift katman kanıt)."""

    import scripts.validation.run_baselines_ablations as mod

    def always_down(_search, _idx):
        raise ConnectionError("RemoteDisconnected")

    monkeypatch.setattr(mod, "_download_with_corrupt_retry", always_down)
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    with pytest.raises(ConnectionError):
        mod._download_with_network_retry(None, 0)
