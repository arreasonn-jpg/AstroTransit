"""Typer CLI'nin gerçek runtime sözleşmesi."""

from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.parametrize("args", [("--help",), ("migrate", "--help"), ("target-pool", "--help")])
def test_cli_help_contract(args: tuple[str, ...]) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Usage:" in completed.stdout


def test_cli_version_contract() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "cli.main", "version"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "AstroTransit" in completed.stdout
