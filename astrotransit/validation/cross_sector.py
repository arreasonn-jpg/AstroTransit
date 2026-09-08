"""Formal consistency checks for independently processed sectors."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Iterable, Optional


@dataclass(frozen=True)
class CrossSectorReport:
    n_sectors: int
    period_consistent: Optional[bool]
    depth_consistent: Optional[bool]
    duration_consistent: Optional[bool]
    epoch_consistent: Optional[bool]
    period_scatter_fraction: Optional[float]
    depth_scatter_fraction: Optional[float]
    classification: str

    @property
    def multi_sector_consistent(self) -> bool:
        return self.classification == "multi_sector_consistent"

    def to_dict(self) -> dict[str, object]:
        return self.__dict__ | {"multi_sector_consistent": self.multi_sector_consistent}


def assess_cross_sector_consistency(
    sectors: Iterable[dict[str, float]],
    *,
    period_tolerance: float = 0.02,
    depth_tolerance: float = 0.20,
    duration_tolerance: float = 0.20,
    epoch_tolerance_days: float = 0.1,
) -> CrossSectorReport:
    """Classify a candidate without treating a single sector as confirmation."""
    rows = list(sectors)
    n = len(rows)
    if n < 2:
        return CrossSectorReport(n, None, None, None, None, None, None, "single_sector_candidate")

    def values(name: str) -> list[float]:
        return [float(row[name]) for row in rows if row.get(name) is not None]

    periods, depths, durations, epochs = (values(name) for name in ("period", "depth", "duration", "epoch"))
    p_scatter = _relative_scatter(periods)
    d_scatter = _relative_scatter(depths)
    period_ok = _within(periods, period_tolerance)
    depth_ok = _within(depths, depth_tolerance)
    duration_ok = _within(durations, duration_tolerance)
    epoch_ok = _within_absolute(epochs, epoch_tolerance_days)
    checks = (period_ok, depth_ok, duration_ok, epoch_ok)
    if any(item is None for item in checks):
        classification = "multi_sector_incomplete"
    elif all(checks):
        classification = "multi_sector_consistent"
    else:
        classification = "multi_sector_inconsistent"
    return CrossSectorReport(n, period_ok, depth_ok, duration_ok, epoch_ok, p_scatter, d_scatter,
                             classification)


def _within(values: list[float], tolerance: float) -> Optional[bool]:
    if len(values) < 2:
        return None
    center = median(values)
    return center > 0 and all(abs(value - center) / center <= tolerance for value in values)


def _within_absolute(values: list[float], tolerance: float) -> Optional[bool]:
    if len(values) < 2:
        return None
    center = median(values)
    return all(abs(value - center) <= tolerance for value in values)


def _relative_scatter(values: list[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    center = median(values)
    return abs(max(values) - min(values)) / center if center else None


__all__ = ["CrossSectorReport", "assess_cross_sector_consistency"]
