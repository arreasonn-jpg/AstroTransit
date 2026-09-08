"""Deterministic development/validation/blind dataset partitioning."""
from __future__ import annotations

import hashlib
from typing import Iterable


def assign_split(target_id: str, *, seed: int = 0, fractions: tuple[float, float, float] = (.6, .2, .2)) -> str:
    """Assign an ID without using labels or iteration order.

    The blind partition is deterministic but independent from the pipeline's
    scores, preventing accidental re-shuffling during repeated runs.
    """
    if len(fractions) != 3 or any(value <= 0 for value in fractions) or abs(sum(fractions) - 1) > 1e-9:
        raise ValueError("fractions development/validation/blind toplamı 1 olmalıdır.")
    digest = hashlib.sha256(f"{seed}:{target_id}".encode()).digest()
    value = int.from_bytes(digest[:8], "big") / 2**64
    if value < fractions[0]:
        return "development"
    if value < fractions[0] + fractions[1]:
        return "validation"
    return "blind_test"


def partition_target_ids(target_ids: Iterable[str], *, seed: int = 0) -> dict[str, list[str]]:
    result = {"development": [], "validation": [], "blind_test": []}
    for target_id in target_ids:
        result[assign_split(str(target_id), seed=seed)].append(str(target_id))
    return result


__all__ = ["assign_split", "partition_target_ids"]
