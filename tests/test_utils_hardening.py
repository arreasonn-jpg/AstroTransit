"""Tanımlayıcı ve çıktı yolu güvenlik regresyon testleri."""

from pathlib import Path

import pytest

from astrotransit.utils.identifiers import normalize_tic_id, normalize_toi_id
from astrotransit.utils.paths import ProjectPaths


@pytest.mark.parametrize("raw", [True, 0, -1, "abc123", "TIC 12x", ""])
def test_tic_id_rejects_ambiguous_or_invalid_values(raw):
    with pytest.raises((TypeError, ValueError)):
        normalize_tic_id(raw)


@pytest.mark.parametrize(
    "raw",
    [True, 0, -1, float("nan"), float("inf"), "abc123", "TOI-12x", ""],
)
def test_toi_id_rejects_ambiguous_or_invalid_values(raw):
    with pytest.raises((TypeError, ValueError)):
        normalize_toi_id(raw)


def test_identifier_normalization_keeps_supported_forms():
    assert normalize_tic_id("tic123") == "TIC 123"
    assert normalize_tic_id("TIC-00123") == "TIC 123"
    assert normalize_toi_id("toi 1234.01") == "TOI-1234.01"
    assert normalize_toi_id(1234.01) == "TOI-1234.01"


@pytest.mark.parametrize(
    "target_id",
    ["../../outside", "../outside", "/tmp/outside", r"..\\outside", "TIC/123"],
)
def test_target_dir_cannot_escape_outputs(monkeypatch, tmp_path: Path, target_id: str):
    monkeypatch.setattr("astrotransit.utils.paths.get_project_root", lambda: tmp_path)
    paths = ProjectPaths()

    target = paths.target_dir(target_id)
    targets_root = (tmp_path / "outputs" / "targets").resolve()

    assert target.is_relative_to(targets_root)
    assert target != targets_root


def test_target_dir_rejects_empty_or_dot_only_ids(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("astrotransit.utils.paths.get_project_root", lambda: tmp_path)
    paths = ProjectPaths()

    for target_id in ("", " ", ".", "..", "___"):
        with pytest.raises(ValueError):
            paths.target_dir(target_id)
