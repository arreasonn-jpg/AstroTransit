"""desktop.discovery birim testleri (ağ yok; saf mantık)."""

from __future__ import annotations

import pytest

from desktop.discovery import (
    DiscoveryError,
    discover_targets,
    pick_targets,
    unique_targets_from_rows,
)


def _rows(*tics: int) -> list[dict[str, object]]:
    """MAST gözlem satırı benzeri kayıtlar (target_name biçimi korunur)."""

    return [{"target_name": f"{tic} (TIC)"} for tic in tics]


class TestUniqueTargets:
    def test_parses_target_name_and_dedups(self):
        rows = _rows(1001, 1002, 1001)
        assert unique_targets_from_rows(rows) == ["TIC 1001", "TIC 1002"]

    def test_non_numeric_names_dropped(self):
        rows = [{"target_name": "TICFid1"}, {"target_name": "9002 (TIC)"}, {}]
        assert unique_targets_from_rows(rows) == ["TIC 9002"]

    def test_empty(self):
        assert unique_targets_from_rows([]) == []


class TestPickTargets:
    def test_deterministic_with_seed(self):
        rows = _rows(1001, 1002, 1003, 1004, 1005)
        first = pick_targets(rows, 3, seed=42)
        second = pick_targets(rows, 3, seed=42)
        assert first == second
        assert len(first) == 3
        assert len(set(first)) == 3

    def test_insufficient_pool_raises(self):
        with pytest.raises(DiscoveryError, match="yetersiz"):
            pick_targets(_rows(1001), 3)

    def test_invalid_count_raises(self):
        with pytest.raises(DiscoveryError, match="en az"):
            pick_targets(_rows(1001), 0)

    def test_log_sink_receives_messages(self):
        lines: list[str] = []
        pick_targets(_rows(1001, 1002), 2, log_sink=lines.append)
        assert any("keşif havuzu" in line for line in lines)
        assert sum(line.startswith("keşif hedefi") for line in lines) == 2


class TestDiscoverTargets:
    def test_invalid_count_raises_before_network(self):
        # astroquery importundan önce sayı doğrulanmalı
        with pytest.raises(DiscoveryError, match="en az 1"):
            discover_targets(0)
