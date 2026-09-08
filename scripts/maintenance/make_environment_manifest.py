"""Bir çalıştırma/kapanış paketi için ortam manifesti üretir.

Provenance kapısı #8'in (docs/validation.md) temel aracıdır: Python sürümü,
çözümlenmiş bağımlılık listesi (pip freeze), git commit bilgisi ve config
dosyasının SHA-256'sı tek bir JSON dosyasında toplanır. Kanıt paketlerinin
`environment/` klasörüne konulması önerilir.

Kullanım:
    python scripts/maintenance/make_environment_manifest.py \
        --output release/<paket>/environment/env_manifest.json \
        --config configs/default.toml
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import subprocess


def _pip_freeze() -> list[str]:
    """Çözümlenmiş bağımlılık listesini döndürür."""

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # Editable/paketin kendisi yeniden üretim için ayrı satırda tutulur.
    return [line for line in lines if not line.startswith("astrotransit ")]


def _git_info(repo_root: Path) -> dict:
    def _run(*args: str) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return ""
        return result.stdout.strip()

    return {
        "commit": _run("rev-parse", "HEAD"),
        "branch": _run("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(_run("status", "--porcelain")),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(repo_root: Path, config_path: Path | None) -> dict:
    """Manifest içeriğini üretir (disk'e yazmaz)."""

    try:
        package_version = version("astrotransit")
    except PackageNotFoundError:
        package_version = "unknown"

    lock_path = repo_root / "envs" / "requirements.lock"
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "dependency_lock": {
            "path": str(lock_path),
            "sha256": _sha256(lock_path) if lock_path.is_file() else None,
        },
        "platform": platform.platform(),
        "package": {
            "name": "astrotransit",
            "version": package_version,
        },
        "git": _git_info(repo_root),
        "dependencies": _pip_freeze(),
    }

    if config_path is not None:
        config = config_path.resolve()
        if config.is_file():
            manifest["config"] = {
                "path": str(config),
                "sha256": _sha256(config),
            }
        else:
            manifest["config"] = {"path": str(config), "error": "config dosyası bulunamadı"}

    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("env_manifest.json"),
        help="Manifest çıktısı (varsayılan: env_manifest.json)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="İsteğe bağlı config dosyası (SHA-256 ile manifeste işlenir)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Git repo kökü (varsayılan: script konumuna göre)",
    )
    args = parser.parse_args(argv)

    manifest = build_manifest(args.repo_root, args.config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Ortam manifesti yazıldı: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
