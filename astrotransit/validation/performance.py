"""Runtime and resource benchmark helpers."""
from __future__ import annotations

from dataclasses import dataclass
import os
import time
from typing import Any, Callable


@dataclass(frozen=True)
class RuntimeMeasurement:
    name: str
    n_targets: int
    seconds: float
    seconds_per_target: float | None
    peak_memory_mb: float | None
    cpu_count: int

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def measure_runtime(name: str, operation: Callable[[], Any], *, n_targets: int = 1) -> RuntimeMeasurement:
    """Measure wall time and best-effort peak RSS without changing operation output."""
    if n_targets < 1:
        raise ValueError("n_targets en az 1 olmalıdır.")
    try:
        import resource
        before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (ImportError, AttributeError):
        before = None
    start = time.perf_counter()
    operation()
    elapsed = time.perf_counter() - start
    try:
        import resource
        after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports KiB; macOS reports bytes.
        peak = (after / 1024 if after < 10_000_000 else after / 1024 / 1024)
        if before is not None:
            peak = max(0.0, peak - (before / 1024 if before < 10_000_000 else before / 1024 / 1024))
    except (ImportError, AttributeError):
        peak = None
    return RuntimeMeasurement(name, n_targets, elapsed, elapsed / n_targets, peak, os.cpu_count() or 1)


__all__ = ["RuntimeMeasurement", "measure_runtime"]
