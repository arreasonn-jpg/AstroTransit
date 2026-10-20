"""Masaüstü uygulama yardımcı katmanı testleri (Qt olmadan).

Kapsam
------
- desktop.helpers: output_roots / list_json_results / find_figures
- sector_rows ve run_summary_row: eksik alanlara dayanıklılık
- rows_from_json_files: JSON → tablo satırı
- parse_sectors: girdi doğrulama
- desktop.analysis: _forward_log + boş hedef validasyonu
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from desktop.analysis import AnalysisConfig, AnalysisError, _forward_log
from desktop.helpers import (
    find_figures,
    list_json_results,
    output_roots,
    parse_sectors,
    rows_from_json_files,
    run_summary_row,
    safe_target_component,
    sector_rows,
)

# ─────────────────────────────────────────────────────────────
# helpers: yollar ve listeler
# ─────────────────────────────────────────────────────────────

def test_safe_target_component_normalizes_spaces():
    assert safe_target_component("TIC 123/456") == "TIC_123_456"


def test_output_roots_returns_only_existing(tmp_path: Path):
    (tmp_path / "outputs").mkdir()
    roots = output_roots(tmp_path)
    assert roots == [tmp_path / "outputs"]


def test_json_root_and_list_json_results(tmp_path: Path):
    (tmp_path / "outputs" / "json").mkdir(parents=True)
    (tmp_path / "outputs_top10" / "json").mkdir(parents=True)
    a = tmp_path / "outputs" / "json" / "TIC_1.json"
    b = tmp_path / "outputs_top10" / "json" / "TIC_2.json"
    a.write_text("{}", encoding="utf-8")
    b.write_text("{}", encoding="utf-8")
    (tmp_path / "outputs" / "json" / "all_candidates.jsonl").write_text("", encoding="utf-8")

    roots = output_roots(tmp_path)
    files = list_json_results(roots)
    names = [f.name for f in files]
    assert names == ["TIC_1.json", "TIC_2.json"]


def test_find_figures_orders_by_evidence_chain(tmp_path: Path):
    figures = tmp_path / "outputs" / "figures"
    figures.mkdir(parents=True)
    for name in ["zzz", "lightcurve", "summary", "folded"]:
        (figures / f"TIC_99_S01_{name}.png").touch()
    found = find_figures(output_roots(tmp_path), "TIC 99", 1)
    stems = [p.stem for p in found]
    assert stems[0].endswith("summary")
    assert stems[1].endswith("lightcurve")
    assert stems[2].endswith("folded")


def test_find_figures_empty_when_missing(tmp_path: Path):
    assert find_figures([], "TIC 1", 14) == []


# ─────────────────────────────────────────────────────────────
# helpers: sonuç satırları
# ─────────────────────────────────────────────────────────────

@dataclass
class _Score:
    total_score: float = 88.0
    candidate_class: object = None


@dataclass
class _ClassValue:
    value: str = "A"


@dataclass
class _Candidate:
    period: float = 3.5
    depth_ppm: float = 900.0

    def to_dict(self) -> dict:
        return {"period": self.period, "depth_ppm": self.depth_ppm}


@dataclass
class _Quality:
    score: _Score = field(default_factory=_Score)


@dataclass
class _SectorResult:
    sector: int
    success: bool = True
    quality: _Quality | None = None
    candidate: _Candidate | None = None


@dataclass
class _TargetResult:
    target_id: str = "TIC 261136679"
    success: bool = True
    sectors_processed: int = 1
    candidates_found: int = 1
    candidates_confirmed: int = 0
    sector_results: list = field(default_factory=list)
    error: str = ""


def test_sector_rows_maps_fields():
    q = _Quality(score=_Score(total_score=91.0, candidate_class=_ClassValue()))
    result = _TargetResult(sector_results=[_SectorResult(14, quality=q, candidate=_Candidate())])
    rows = sector_rows(result)
    assert len(rows) == 1
    row = rows[0]
    assert row["target_id"] == "TIC 261136679"
    assert row["sector"] == 14
    assert row["candidate_class"] == "A"
    assert row["total_score"] == 91.0
    assert row["period_days"] == 3.5
    assert row["depth_ppm"] == 900.0
    assert row["fpp"] is None  # alan yoksa boş, istisna yok


def test_sector_rows_survives_empty_results():
    assert sector_rows(_TargetResult(sector_results=[_SectorResult(7)])) == [
        {
            "target_id": "TIC 261136679",
            "sector": 7,
            "success": True,
            "candidate_class": "",
            "total_score": None,
            "snr": None,
            "fpp": None,
            "period_days": None,
            "duration_hours": None,
            "depth_ppm": None,
            "planet_radius_rearth": None,
            "earth_similarity_score": None,
        }
    ]


def test_run_summary_row():
    summary = run_summary_row(_TargetResult(candidates_confirmed=2))
    assert summary["success"] is True
    assert summary["candidates_confirmed"] == 2


def test_rows_from_json_files(tmp_path: Path):
    payload = {
        "target": {"source_id": "TIC 5", "sector": 14},
        "parameters": {"period_days": 4.2, "depth_ppm": 700.0},
        "derived": {"planet_radius_rearth": 1.3},
        "score": {"candidate_class": "B", "total_score": 80.5},
        "quality": {"snr": {"snr_adopted": 12.0}},
        "earth_similarity": {"score": 91.0},
    }
    path = tmp_path / "TIC_5.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    rows = rows_from_json_files([path])
    assert len(rows) == 1
    row = rows[0]
    assert row["target_id"] == "TIC 5"
    assert row["sector"] == 14
    assert row["candidate_class"] == "B"
    assert row["period_days"] == 4.2
    assert row["earth_similarity_score"] == 91.0


def test_rows_from_json_files_skips_corrupt(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("{geçersiz", encoding="utf-8")
    assert rows_from_json_files([bad]) == []


# ─────────────────────────────────────────────────────────────
# girdi doğrulama
# ─────────────────────────────────────────────────────────────

def test_parse_sectors_valid():
    assert parse_sectors("14,15,16") == [14, 15, 16]
    assert parse_sectors("7") == [7]


def test_parse_sectors_empty_returns_none():
    assert parse_sectors("") is None
    assert parse_sectors("   ") is None


def test_parse_sectors_invalid_raises():
    with pytest.raises(ValueError):
        parse_sectors("on,dört")


# ─────────────────────────────────────────────────────────────
# analysis: log aktarımı + boş hedef kontrolü
# ─────────────────────────────────────────────────────────────

def test_forward_log_routes_messages_and_tolerates_sink_errors():
    received = []

    class _Msg:
        def __str__(self) -> str:
            return "pipeline adımı\n"

    sink = _forward_log(received.append)
    assert sink is not None
    sink(_Msg())
    assert received == ["pipeline adımı"]

    # Sink hata verirse çökmez
    def _bad_sink(_line: str) -> None:
        raise RuntimeError("ui çöktü")

    robust_sink = _forward_log(_bad_sink)
    assert robust_sink is not None
    robust_sink(_Msg())  # istisna kabarcığı yukarı çıkarmamalı


def test_forward_log_none():
    assert _forward_log(None) is None


def test_analyze_targets_rejects_empty_targets():
    from desktop.analysis import analyze_targets

    with pytest.raises(AnalysisError, match="hedef listesi boş"):
        analyze_targets(AnalysisConfig(targets=[]))
