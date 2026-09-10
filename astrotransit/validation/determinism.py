"""Canonical output hashing and deterministic benchmark rerun checks."""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_EXCLUDED_KEYS = frozenset(
    {
        "created_at",
        "generated_at_utc",
        "run_timestamp_utc",
        "output_hash",
        "sha256",
    }
)


def _json_default(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Canonical JSON desteklenmeyen tip: {type(value).__name__}")


def _clean(value: Any, excluded: set[str]) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _clean(item, excluded)
            for key, item in value.items()
            if str(key) not in excluded
        }
    if isinstance(value, (list, tuple)):
        return [_clean(item, excluded) for item in value]
    return value


def canonical_json(
    value: Any,
    *,
    exclude_keys: Iterable[str] = DEFAULT_EXCLUDED_KEYS,
) -> str:
    """Serialize JSON deterministically after removing volatile metadata."""

    return json.dumps(
        _clean(value, set(exclude_keys)),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=_json_default,
    )


def output_hash(
    value: Any,
    *,
    exclude_keys: Iterable[str] = DEFAULT_EXCLUDED_KEYS,
) -> str:
    """Return a SHA-256 hash of canonical, non-volatile output content."""

    return hashlib.sha256(
        canonical_json(value, exclude_keys=exclude_keys).encode("utf-8")
    ).hexdigest()


def assert_deterministic(first: Any, second: Any) -> str:
    """Assert semantic equality after volatile metadata is removed."""

    left, right = output_hash(first), output_hash(second)
    if left != right:
        raise AssertionError(f"Non-deterministic output: {left} != {right}")
    return left


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: str | Path) -> Mapping[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Benchmark JSON nesne olmalıdır: {path}")
    return payload


def _json_target_order(payload: Mapping[str, Any]) -> tuple[str, ...]:
    targets = payload.get("targets", [])
    if not isinstance(targets, list):
        raise ValueError("Benchmark JSON targets alanı liste olmalıdır")
    return tuple(
        str(item.get("target_id", ""))
        for item in targets
        if isinstance(item, Mapping)
    )


def _csv_target_order(path: str | Path) -> tuple[str, ...]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "target_id" not in reader.fieldnames:
            raise ValueError(f"Benchmark CSV target_id sütunu içermelidir: {path}")
        return tuple(str(row.get("target_id", "")) for row in reader)


@dataclass(frozen=True)
class DeterminismReport:
    """Machine-readable result of comparing two benchmark runs."""

    json_hash_a: str
    json_hash_b: str
    csv_hash_a: str
    csv_hash_b: str
    metrics_hash_a: str
    metrics_hash_b: str
    json_equal: bool
    csv_equal: bool
    metrics_equal: bool
    target_order_equal: bool
    differences: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.differences

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["differences"] = list(self.differences)
        result["status"] = "PASS" if self.passed else "FAIL"
        return result


def compare_benchmark_artifacts(
    json_a: str | Path,
    csv_a: str | Path,
    json_b: str | Path,
    csv_b: str | Path,
) -> DeterminismReport:
    """Compare JSON, CSV, metrics and target ordering for two benchmark runs."""

    payload_a, payload_b = _load_json(json_a), _load_json(json_b)
    json_hash_a, json_hash_b = output_hash(payload_a), output_hash(payload_b)
    csv_hash_a, csv_hash_b = _sha256_file(csv_a), _sha256_file(csv_b)
    metrics_hash_a = output_hash(payload_a.get("metrics", {}))
    metrics_hash_b = output_hash(payload_b.get("metrics", {}))

    json_order_a, json_order_b = _json_target_order(payload_a), _json_target_order(payload_b)
    csv_order_a, csv_order_b = _csv_target_order(csv_a), _csv_target_order(csv_b)
    target_order_equal = (
        json_order_a == json_order_b
        and csv_order_a == csv_order_b
        and json_order_a == csv_order_a
        and json_order_b == csv_order_b
    )

    checks = {
        "json_hash_mismatch": json_hash_a == json_hash_b,
        "csv_hash_mismatch": csv_hash_a == csv_hash_b,
        "metrics_mismatch": metrics_hash_a == metrics_hash_b,
        "target_order_mismatch": target_order_equal,
    }
    differences = tuple(name for name, ok in checks.items() if not ok)
    return DeterminismReport(
        json_hash_a=json_hash_a,
        json_hash_b=json_hash_b,
        csv_hash_a=csv_hash_a,
        csv_hash_b=csv_hash_b,
        metrics_hash_a=metrics_hash_a,
        metrics_hash_b=metrics_hash_b,
        json_equal=checks["json_hash_mismatch"],
        csv_equal=checks["csv_hash_mismatch"],
        metrics_equal=checks["metrics_mismatch"],
        target_order_equal=target_order_equal,
        differences=differences,
    )


__all__ = [
    "DEFAULT_EXCLUDED_KEYS",
    "DeterminismReport",
    "assert_deterministic",
    "canonical_json",
    "compare_benchmark_artifacts",
    "output_hash",
]
