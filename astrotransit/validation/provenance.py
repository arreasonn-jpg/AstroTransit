"""Small, reproducible provenance manifests for scientific validation runs."""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def git_revision(root: str | Path = ".") -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build_manifest(
    *,
    input_path: str | Path | None = None,
    config: Mapping[str, Any] | None = None,
    seed: int | None = None,
    pipeline_version: str = "",
    root: str | Path = ".",
    model_version: str | None = None,
) -> dict[str, Any]:
    """Create a JSON-safe manifest; absent measurements remain ``None``."""
    input_hash = sha256_file(input_path) if input_path is not None and Path(input_path).is_file() else None
    config_hash = canonical_hash(config or {})
    return {
        "target_id": None,
        "sector": None,
        "data_product": None,
        "cadence": None,
        "pipeline_version": pipeline_version,
        "git_commit": git_revision(root),
        "config_hash": config_hash,
        "schema_version": None,
        "model_version": model_version,
        "random_seed": seed,
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "host_platform": platform.platform(),
        "input_hash": input_hash,
        "output_hash": None,
    }


def attach_manifest(payload: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy with a stable top-level provenance block."""
    result = dict(payload)
    result["provenance"] = dict(manifest)
    return result


__all__ = ["attach_manifest", "build_manifest", "canonical_hash", "git_revision", "sha256_file"]
