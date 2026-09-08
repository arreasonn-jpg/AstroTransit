"""Canonical output hashing and determinism checks."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def output_hash(value: Any, *, exclude_keys: Iterable[str] = ("created_at", "run_timestamp_utc")) -> str:
    excluded = set(exclude_keys)
    def clean(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {key: clean(val) for key, val in item.items() if key not in excluded}
        if isinstance(item, (list, tuple)):
            return [clean(val) for val in item]
        return item
    return hashlib.sha256(canonical_json(clean(value)).encode()).hexdigest()


def assert_deterministic(first: Any, second: Any) -> str:
    left, right = output_hash(first), output_hash(second)
    if left != right:
        raise AssertionError(f"Non-deterministic output: {left} != {right}")
    return left


__all__ = ["assert_deterministic", "canonical_json", "output_hash"]
