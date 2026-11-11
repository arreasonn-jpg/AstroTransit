"""Masaüstü uygulama yardımcıları (Qt-bağımsız, saf fonksiyonlar).

Bu modül bilinçli olarak PySide6 import etmez; birim testleri GUI
bağımlılığı olmadan çalışabilsin.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Iterable, Optional

# Geçmiş kampanyalardan bilinen ekstra çıktı kökleri (dashboard ile uyumlu).
DEFAULT_OUTPUT_ROOT_NAMES = (
    "outputs",
    "outputs_top10",
    "outputs_wsl_mcmc",
    "outputs_novel_followup",
    "outputs_novel_mcmc",
)

# Görselleri kanıt zinciri sırasına göre dizmek için sabit öncelik.
FIGURE_ORDER = {
    "summary": 1,
    "lightcurve": 2,
    "folded": 3,
    "bls_tls": 4,
    "residuals": 5,
    "timing": 6,
    "scorecard": 7,
}

RESULT_TABLE_COLUMNS = (
    "target_id",
    "sector",
    "success",
    "candidate_class",
    "total_score",
    "snr",
    "fpp",
    "period_days",
    "duration_hours",
    "depth_ppm",
    "planet_radius_rearth",
    "earth_similarity_score",
)

_ALL_CANDIDATES_JSONL = "all_candidates.jsonl"


def _get(obj: Any, *names: str, default: Any = None) -> Any:
    """Yerleşik öznitelik zincirini güvenle düşürür (None → default)."""

    current = obj
    for name in names:
        if current is None:
            return default
        current = getattr(current, name, None)
    return default if current is None else current


def _float(value: Any) -> Optional[float]:
    """Sayısal değerleri güvenle float'a çevirir; olamazsa None."""

    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def safe_target_component(source_id: str) -> str:
    """Kaynak kimliğini güvenli dosya adı parçasına çevirir (dashboard ile aynı kural)."""

    return str(source_id).replace(" ", "_").replace("/", "_")


def output_roots(project_root: Path, names: Iterable[str] = DEFAULT_OUTPUT_ROOT_NAMES) -> list[Path]:
    """Mevcut çıktı kök dizinlerini döndürür (varsa)."""

    base = Path(project_root)
    return [base / name for name in names if (base / name).exists()]


def json_root(roots: Iterable[Path]) -> Optional[Path]:
    """İlk kullanılabilir `json` alt dizinini döndürür."""

    for root in roots:
        candidate = Path(root) / "json"
        if candidate.is_dir():
            return candidate
    return None


def list_json_results(roots: Iterable[Path]) -> list[Path]:
    """Köklerdeki aday JSON dosyalarını isme göre sıralar."""

    seen: dict[str, Path] = {}
    for root in roots:
        json_dir = Path(root) / "json"
        if json_dir.is_dir():
            for f in json_dir.glob("*.json"):
                if f.name != _ALL_CANDIDATES_JSONL:
                    seen[f.name] = f
    return sorted(seen.values(), key=lambda p: p.name)


def find_figures(
    roots: Sequence[Path],
    source_id: str,
    sector: int,
) -> list[Path]:
    """Hedef/sektör PNG görsellerini kanıt zinciri sırasına göre döndürür."""

    safe = safe_target_component(source_id)
    sector_disp = f"S{sector:02d}"
    pattern = f"{safe}_{sector_disp}_*.png"
    seen: dict[str, Path] = {}
    for root in roots:
        figures_dir = Path(root) / "figures"
        if figures_dir.is_dir():
            for img in figures_dir.glob(pattern):
                if img.name not in seen:
                    seen[img.name] = img
    return sorted(
        seen.values(),
        key=lambda p: (
            next((v for k, v in FIGURE_ORDER.items() if k in p.stem), 999),
            p.name,
        ),
    )


def figure_caption(info: Path) -> str:
    """Görsel dosyasından kısa etiket üretir."""

    stem = Path(info).stem
    for name, label in {
        "summary": "Özet panel",
        "lightcurve": "Işık eğrisi",
        "folded": "Folded (periyotla katlanmış)",
        "bls_tls": "BLS/TLS karşılaştırma",
        "residuals": "Artıklar",
        "timing": "Zamanlama",
        "scorecard": "Skor kartı",
    }.items():
        if name in stem:
            return label
    return stem


def sector_rows(result: Any) -> list[dict[str, Any]]:
    """TESSSectorResult listesini tablo satırlarına çevirir.

    Eksik alanlara dayanıklıdır: alan yoksa boş bırakılır, istisna
    yükselmez (UI tablosu parçalanmamalı).
    """

    rows: list[dict[str, Any]] = []
    target_id = _get(result, "target_id", default="")
    for sr in _get(result, "sector_results", default=[]):
        quality = _get(sr, "quality", default=None)
        candidate = _get(sr, "candidate", default=None)
        try:
            plan_fit = _get(sr, "plan_fit", default=None)
        except Exception:
            plan_fit = None
        cand_dict: dict[str, Any] = {}
        to_dict = getattr(candidate, "to_dict", None)
        if callable(to_dict):
            try:
                cand_dict = to_dict() or {}
            except Exception:
                cand_dict = {}
        cls = _get(quality, "score", "candidate_class")
        cls_value = getattr(cls, "value", None) or (cls if isinstance(cls, str) else "")
        # Plan modu: kalite/vetting koşmadı; MAP fit sonucuyla doldur.
        if plan_fit is not None and not cand_dict:
            cand_dict = {
                "period": _get(plan_fit, "period"),
                "duration": _get(plan_fit, "duration"),
                "rp_rs": _get(plan_fit, "rp_rs"),
                "snr": None,
            }
            cls_value = "plan_fit (kısıtlı doğrulama)"
            quality = None
        rows.append(
            {
                "target_id": str(target_id),
                "sector": _get(sr, "sector", default=""),
                "success": bool(_get(sr, "success", default=False)),
                "candidate_class": str(cls_value) if cls_value else "",
                "total_score": _float(_get(quality, "score", "total_score")),
                "snr": _float(_get(quality, "snr", "snr_adopted")),
                "fpp": _float(
                    _get(quality, "vetting", "false_positive_probability")
                ),
                "period_days": _float(cand_dict.get("period", cand_dict.get("period_days"))),
                "duration_hours": _float(cand_dict.get("duration_hours", cand_dict.get("duration"))),
                "depth_ppm": _float(cand_dict.get("depth_ppm")),
                "planet_radius_rearth": _float(
                    cand_dict.get("planet_radius_rearth")
                ),
                "earth_similarity_score": _float(
                    cand_dict.get("earth_similarity_score")
                ),
            }
        )
    return rows


def run_summary_row(result: Any) -> dict[str, Any]:
    """Toplevel TESSTargetResult özetini döndürür (UI üst şeridi)."""

    return {
        "target_id": _get(result, "target_id", default=""),
        "success": bool(_get(result, "success", default=False)),
        "sectors_processed": _get(result, "sectors_processed", default=0),
        "candidates_found": _get(result, "candidates_found", default=0),
        "candidates_confirmed": _get(result, "candidates_confirmed", default=0),
        "error": _get(result, "error", default="") or "",
    }


_JSON_ROW_CACHE: dict[str, tuple[float, int, dict[str, Any]]] = {}


def rows_from_json_files(files: Iterable[Path]) -> list[dict[str, Any]]:
    """Kaydedilmiş aday JSON çıktısını tablo satırına çevirir (alanlar eski şemalara toleranslı).

    Optimizasyon: mtime+boyut sabit olan dosyalar yeniden örneklenmez; son
    taramayla aynıysa bellekten dönüş yapılır (yüzlerce dosyada UI takılması...
    """

    import json

    rows: list[dict[str, Any]] = []
    for path in files:
        key = str(path)
        try:
            stat = Path(path).stat()
            stamp = (stat.st_mtime, stat.st_size)
        except OSError:
            continue
        cached = _JSON_ROW_CACHE.get(key)
        if cached is not None and cached[0] == stamp[0] and cached[1] == stamp[1]:
            rows.append(cached[2])
            continue
        try:
            with Path(path).open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        target = data.get("target", {}) or {}
        params = data.get("parameters", {}) or {}
        derived = data.get("derived", {}) or {}
        quality = data.get("quality", {}) or {}
        score_data = data.get("score", {}) or {}
        similarity = data.get("earth_similarity", {}) or {}
        fpp = _float(
            _get(quality, "vetting", "false_positive_probability")
            if isinstance(quality, dict)
            else None
        )
        if fpp is None:
            fpp = _float(quality.get("fpp") if isinstance(quality, dict) else None) or _float(data.get("fpp"))
        row = {
            "target_id": target.get("source_id", Path(path).stem),
            "sector": target.get("sector", ""),
            "success": True,
            "candidate_class": str(score_data.get("candidate_class", "")),
            "total_score": _float(score_data.get("total_score")),
            "snr": _float(_get(quality, "snr", "snr_adopted")),
            "fpp": fpp,
            "period_days": _float(params.get("period_days", params.get("period"))),
            "duration_hours": _float(params.get("duration_hours", params.get("duration"))),
            "depth_ppm": _float(params.get("depth_ppm", derived.get("depth_ppm"))),
            "planet_radius_rearth": _float(derived.get("planet_radius_rearth")),
            "earth_similarity_score": _float(similarity.get("score")),
        }
        if len(_JSON_ROW_CACHE) > 4000:  # tavan: aşırı büyümeyi önle
            _JSON_ROW_CACHE.clear()
        _JSON_ROW_CACHE[key] = (stamp[0], stamp[1], row)
        rows.append(row)
    return rows


def parse_sectors(text: str) -> Optional[list[int]]:
    """"14,15,16" biçimindeki metni int listesine çevirir; boşsa None.

    Geçersiz girdi ValueError yükseltir — UI bunu kendi içinde yakalar.
    """

    cleaned = (text or "").strip()
    if not cleaned:
        return None
    sectors = [int(part) for part in re.split(r"[,\s]+", cleaned) if part]
    if not sectors:
        return None
    return sectors


__all__ = [
    "DEFAULT_OUTPUT_ROOT_NAMES",
    "FIGURE_ORDER",
    "RESULT_TABLE_COLUMNS",
    "figure_caption",
    "find_figures",
    "json_root",
    "list_json_results",
    "output_roots",
    "parse_sectors",
    "rows_from_json_files",
    "run_summary_row",
    "safe_target_component",
    "sector_rows",
]
