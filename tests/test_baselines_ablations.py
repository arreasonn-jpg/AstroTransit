"""Sade TLS/BLS kural ünite testleri (sentetik geçişler)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from astropy import units as u

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


def test_baseline_fingerprint_depends_on_rules():
    a = runner.baseline_fingerprint("corpus.json", "v1")
    b = runner.baseline_fingerprint("corpus.json", "v2")
    assert a != b
    assert runner.baseline_fingerprint("corpus.json", "v1") == a  # deterministik
