"""validation/performance ölçüm doğruluk testleri.

linux KiB / macOS bayt birim ayrımı ve ru_maxrss yorumu (high-water
mark) için sözleşme testleri — eski sezgisel yöntemin ve 'delta'
hesabın regresyon önlenmesi amaçlanır.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from astrotransit.validation.performance import (
    _rss_unit_to_mb,
    measure_runtime,
    rss_highwater_mb,
)


def test_rss_unit_is_kb_on_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert _rss_unit_to_mb() == 1024


def test_rss_unit_is_bytes_on_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert _rss_unit_to_mb() == 1024 * 1024


def test_large_linux_rss_is_not_double_divided(monkeypatch):
    """50 GiB'ın KiB karşılığı → 51200.0 MB; eski yöntem iki kez bölüyordu."""

    import resource

    monkeypatch.setattr(sys, "platform", "linux")
    value_kiB = 50 * 1024 * 1024  # 50 GiB = 52428800 KiB
    fake = SimpleNamespace(ru_maxrss=value_kiB)
    monkeypatch.setattr(
        resource, "getrusage", lambda who: fake, raising=True
    )
    mb = rss_highwater_mb()
    assert mb == pytest.approx(51200.0)


def test_rss_highwater_none_without_resource(monkeypatch):
    monkeypatch.setitem(sys.modules, "resource", None)  # import → ImportError
    assert rss_highwater_mb() is None


def test_measure_runtime_rejects_zero_targets():
    with pytest.raises(ValueError, match="n_targets en az 1"):
        measure_runtime("x", lambda: None, n_targets=0)


def test_measure_runtime_reports_time_and_optional_peak():
    seen: list[str] = []
    result = measure_runtime("hedefler", lambda: seen.append("a"), n_targets=3)
    assert result.name == "hedefler"
    assert result.n_targets == 3
    assert result.seconds_per_target == pytest.approx(result.seconds / 3)
    assert result.cpu_count >= 1
    # Linux CI'da resource mevcut; peak ya ölçümü ya None'dır ve negatif olamaz.
    assert result.peak_memory_mb is None or result.peak_memory_mb >= 0
