"""Immutable validation artifact manifests."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from astrotransit.validation.determinism import output_hash
from astrotransit.validation.provenance import build_manifest, sha256_file


def write_artifact(payload: Mapping[str, Any], path: str | Path, *, provenance: Mapping[str, Any] | None = None) -> Path:
    """Write canonical JSON and a sibling manifest containing its output hash."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    canonical = dict(payload)
    canonical.setdefault("provenance", dict(provenance or build_manifest()))
    canonical["provenance"] = dict(canonical["provenance"])
    canonical["provenance"]["output_hash"] = output_hash(canonical)
    destination.write_text(json.dumps(canonical, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest = destination.with_name(f"{destination.stem}.manifest.json")
    manifest.write_text(json.dumps({"artifact": destination.name, "sha256": sha256_file(destination),
                                    "output_hash": canonical["provenance"]["output_hash"]}, indent=2) + "\n", encoding="utf-8")
    return destination


__all__ = ["write_artifact"]
