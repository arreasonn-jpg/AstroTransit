"""Small, reproducible provenance manifests for scientific validation runs."""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable, Mapping


CORE_PACKAGES = (
    "astrotransit",
    "astropy",
    "lightkurve",
    "numpy",
    "pandas",
    "pydantic",
    "scipy",
    "transitleastsquares",
    "wotan",
)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def git_revision(root: str | Path = ".") -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def installed_package_versions(
    packages: Iterable[str] = CORE_PACKAGES,
) -> dict[str, str | None]:
    """Return stable package-version evidence without importing heavy packages."""

    versions: dict[str, str | None] = {}
    for package in sorted(set(packages)):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def build_manifest(
    *,
    input_path: str | Path | None = None,
    config: Mapping[str, Any] | None = None,
    seed: int | None = None,
    pipeline_version: str = "",
    root: str | Path = ".",
    model_version: str | None = None,
    environment_manifest_path: str | Path | None = None,
    packages: Iterable[str] = CORE_PACKAGES,
) -> dict[str, Any]:
    """Create a JSON-safe provenance manifest for a scientific run."""

    input_hash = (
        sha256_file(input_path)
        if input_path is not None and Path(input_path).is_file()
        else None
    )
    environment_manifest_hash = (
        sha256_file(environment_manifest_path)
        if environment_manifest_path is not None
        and Path(environment_manifest_path).is_file()
        else None
    )
    return {
        "target_id": None,
        "sector": None,
        "data_product": None,
        "cadence": None,
        "pipeline_version": pipeline_version,
        "git_commit": git_revision(root),
        "config_hash": canonical_hash(config or {}),
        "schema_version": None,
        "model_version": model_version,
        "random_seed": seed,
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "host_platform": platform.platform(),
        "python_version": platform.python_version(),
        "package_versions": installed_package_versions(packages),
        "input_hash": input_hash,
        "environment_manifest_hash": environment_manifest_hash,
        "output_hash": None,
    }


def attach_manifest(payload: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy with a stable top-level provenance block."""

    result = dict(payload)
    result["provenance"] = dict(manifest)
    return result


__all__ = [
    "CORE_PACKAGES",
    "attach_manifest",
    "build_manifest",
    "canonical_hash",
    "git_revision",
    "installed_package_versions",
    "sha256_file",
]
