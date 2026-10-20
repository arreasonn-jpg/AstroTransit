"""Runtime and resource benchmark helpers."""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable

__all__ = ["RuntimeMeasurement", "measure_runtime", "rss_highwater_mb"]


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


def _rss_unit_to_mb() -> float:
    """Platforma göre ``ru_maxrss`` birimini MB'a çeviren katsayı.

    ``getrusage`` sözleşmesi platforma göre değişir:
    Linux ``ru_maxrss`` değerini **kilobayt** (KiB) olarak bildirir;
    macOS **bayt** olarak bildirir. Değerin büyüklüğüne göre tahmin
    yürüten eski sezgisel yöntem, 10 GB üzeri RSS'lerde birimi iki kez
    bölerek yanlış ölçüm üretiyordu; platforma göre sabit katsayı kullanılır.
    Windows'ta ``resource`` modülü bulunmuyorken çağrılmaz.
    """

    if sys.platform == "darwin":
        return 1024 * 1024
    return 1024


def rss_highwater_mb() -> float | None:
    """Sürecin anlık yüksek-su-işareti RSS değerini MB cinsinden döndürür.

    Dönen değer geçerli işlemi değil, sürecin tamamı için tepe değeri
    olduğundan ``ru_maxrss`` tekdüze artar (monotonic). Operation
    kapsamındaki gerçek tepe, bu değer için alt sınırdır.
    ``resource`` yoksa None döndürür.
    """

    try:
        import resource
    except (ImportError, AttributeError):
        return None
    try:
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / _rss_unit_to_mb()
    except (OSError, AttributeError, ValueError):
        return None


def measure_runtime(name: str, operation: Callable[[], Any], *, n_targets: int = 1) -> RuntimeMeasurement:
    """Measure wall time and best-effort peak RSS without changing operation output."""

    if n_targets < 1:
        raise ValueError("n_targets en az 1 olmalıdır.")
    before = rss_highwater_mb()
    start = time.perf_counter()
    operation()
    elapsed = time.perf_counter() - start
    after = rss_highwater_mb()
    # ru_maxrss bir yüksek-su-işareti (high-water mark) olduğundan "before"
    # ile farkı işlem bazlı delta DEĞİLDİR; sadece işlemden sonra ölçülen
    # tepe değer raporlanır (İşlem tepe kullanımının alt sınırı).
    peak = after if after is not None else (before if before is not None else None)
    return RuntimeMeasurement(name, n_targets, elapsed, elapsed / n_targets, peak, os.cpu_count() or 1)
