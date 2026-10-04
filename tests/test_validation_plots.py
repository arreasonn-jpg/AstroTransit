"""
generate_validation_figures birim testleri.

Kapsam
------
- Sadece period_rows -> 1 PNG
- Sadece calibration -> 1 PNG
- Ikisi birlikte -> 2 PNG
- Hicbiri yok -> 0 PNG (bos liste)
- Manifest dosyasi her zaman yazilir
- Cikis dizini olusturulur
- metadata manifest'e tasinir
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import pytest

from astrotransit.validation.plots import generate_validation_figures


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


# ─────────────────────────────────────────────────────────────
# Bos rapor
# ─────────────────────────────────────────────────────────────

def test_empty_report_creates_only_manifest(tmp_path: Path) -> None:
    paths = generate_validation_figures({}, tmp_path)
    assert paths == []
    manifest = tmp_path / "figure_manifest.json"
    assert manifest.exists()


def test_empty_report_no_output_dir_created_yet(tmp_path: Path) -> None:
    nested = tmp_path / "sub" / "deep"
    paths = generate_validation_figures({}, nested)
    assert paths == []
    assert nested.exists()


def test_metadata_in_manifest(tmp_path: Path) -> None:
    report = {"metadata": {"version": "1.0", "run_id": "abc123"}}
    generate_validation_figures(report, tmp_path)
    manifest = json.loads((tmp_path / "figure_manifest.json").read_text())
    assert manifest["source_metadata"] == {"version": "1.0", "run_id": "abc123"}
    assert manifest["figures"] == []


# ─────────────────────────────────────────────────────────────
# Period recovery figuru
# ─────────────────────────────────────────────────────────────

def test_period_recovery_generates_figure(tmp_path: Path) -> None:
    report = {
        "targets": [
            {"expected_period_days": 5.0, "recovered_period_days": 5.01},
            {"expected_period_days": 10.0, "recovered_period_days": 9.98},
        ],
        "metadata": {},
    }
    paths = generate_validation_figures(report, tmp_path)
    assert len(paths) == 1
    assert paths[0].name == "period_recovery.png"
    assert paths[0].exists()


def test_period_recovery_skips_missing_columns(tmp_path: Path) -> None:
    """rows'da expected/recovered yoksa figur uretilmez."""
    report = {"targets": [{"foo": "bar"}, {"expected_period_days": 5.0}]}
    paths = generate_validation_figures(report, tmp_path)
    assert paths == []


def test_period_recovery_skips_none_values(tmp_path: Path) -> None:
    report = {
        "targets": [
            {"expected_period_days": None, "recovered_period_days": 5.0},
            {"expected_period_days": 5.0, "recovered_period_days": None},
        ],
    }
    paths = generate_validation_figures(report, tmp_path)
    assert paths == []


def test_period_recovery_manifest_lists_figure(tmp_path: Path) -> None:
    report = {
        "targets": [{"expected_period_days": 5.0, "recovered_period_days": 5.01}],
    }
    generate_validation_figures(report, tmp_path)
    manifest = json.loads((tmp_path / "figure_manifest.json").read_text())
    assert "period_recovery.png" in manifest["figures"]


# ─────────────────────────────────────────────────────────────
# Calibration figuru
# ─────────────────────────────────────────────────────────────

def test_calibration_generates_figure(tmp_path: Path) -> None:
    report = {
        "calibration_curve": [
            {"mean_predicted": 0.1, "observed_rate": 0.12},
            {"mean_predicted": 0.3, "observed_rate": 0.28},
            {"mean_predicted": 0.5, "observed_rate": 0.55},
        ],
    }
    paths = generate_validation_figures(report, tmp_path)
    assert len(paths) == 1
    assert paths[0].name == "fpp_reliability.png"
    assert paths[0].exists()


def test_calibration_empty_skips(tmp_path: Path) -> None:
    report = {"calibration_curve": []}
    paths = generate_validation_figures(report, tmp_path)
    assert paths == []


# ─────────────────────────────────────────────────────────────
# Her ikisi birlikte
# ─────────────────────────────────────────────────────────────

def test_both_figures_generated(tmp_path: Path) -> None:
    report = {
        "targets": [
            {"expected_period_days": 5.0, "recovered_period_days": 5.01},
            {"expected_period_days": 10.0, "recovered_period_days": 9.98},
        ],
        "calibration_curve": [
            {"mean_predicted": 0.1, "observed_rate": 0.12},
            {"mean_predicted": 0.5, "observed_rate": 0.55},
        ],
    }
    paths = generate_validation_figures(report, tmp_path)
    assert len(paths) == 2
    names = {p.name for p in paths}
    assert names == {"period_recovery.png", "fpp_reliability.png"}

    manifest = json.loads((tmp_path / "figure_manifest.json").read_text())
    assert len(manifest["figures"]) == 2


def test_accepts_str_output_dir(tmp_path: Path) -> None:
    report = {
        "targets": [{"expected_period_days": 5.0, "recovered_period_days": 5.01}],
    }
    paths = generate_validation_figures(report, str(tmp_path))
    assert len(paths) == 1
    assert paths[0].exists()


def test_metadata_default_empty(tmp_path: Path) -> None:
    generate_validation_figures({}, tmp_path)
    manifest = json.loads((tmp_path / "figure_manifest.json").read_text())
    assert manifest["source_metadata"] == {}
