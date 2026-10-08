#!/usr/bin/env bash
set -uo pipefail

REPO="$HOME/AstroTransit"
cd "$REPO" || { echo "FATAL"; exit 1; }
source .venv/bin/activate || { echo "FATAL"; exit 1; }

LOG="$HOME/phase1a_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

echo "=== PHASE 1A: leakage analysis + taxonomy + confusion matrix ==="
echo "Log: $LOG"

# 1) Create leakage_taxonomy.py
mkdir -p astrotransit/validation
cat > astrotransit/validation/leakage_taxonomy.py <<'PY_EOF'
"""Adversarial FP leakage taxonomy.

Bu modül, adversarial FP korpusunda ``leaked_as_candidate`` olarak sonuçlanan
senaryoları sınıflandırır. Amaç: "10 FP kaçtı" ifadesini bilimsel olarak
anlamlı bir sınıflandırmaya dönüştürmek. Örneğin:

    "FP kaçışlarının %60'ı düşük transit sayısından kaynaklanıyor."

Bu, hangi vetting testinin hangi koşulda zayıf kaldığını gösterir ve
iyileştirmeyi hedefe yönlendirir.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Optional

#: Kategorik taksonomi. Yeni kategori eklerken hem burayı hem de
#: ``classify_leak`` fonksiyonunu güncelle.
LEAKAGE_CATEGORIES = (
    "LOW_TRANSIT_COUNT",
    "WEAK_SECONDARY",
    "WEAK_ODD_EVEN",
    "V_SHAPE",
    "GRAZING",
    "DURATION_ANOMALY",
    "STELLAR_VARIABILITY",
    "HARMONIC_CONFUSION",
    "BLENDING",
    "OTHER",
)


def classify_leak(row: Mapping[str, Any]) -> tuple[str, list[str]]:
    """Bir leak satırını kategoriye ve tetikleyicilere ayırır.

    Returns
    -------
    (category, reasons)
        ``category`` — birincil taksonomik kategori
        ``reasons`` — sınıflandırmayı tetikleyen gözlemlerin listesi

    Öncelik sırası bilinçlidir: en somut/güçlü gözlem en üstte.
    """
    reasons: list[str] = []

    # Sayısal alanları güvenli biçimde çek
    def _num(*names: str) -> Optional[float]:
        for n in names:
            v = row.get(n)
            if v is None:
                continue
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
        return None

    transits = _num("n_transits", "number_of_transits", "transit_count")
    depth_variance = _num("depth_variance")
    odd_even = _num("odd_even_mismatch", "odd_even")
    secondary = _num("secondary_eclipse_depth_ppm", "secondary_eclipse_depth")
    symmetry = _num("transit_symmetry")
    duration_hours = _num("duration_hours")
    period_days = _num("period_days")
    variability = _num("variability_amplitude_ppm", "variability_amplitude")
    dilution = _num("dilution")
    steepness = _num("steepness")
    fpp = _num("fpp", "false_positive_probability")

    # 1) Harmonik karışıklık: period 2P veya P/2 olarak raporlanmış
    if row.get("harmonic_confusion") is True:
        return "HARMONIC_CONFUSION", ["harmonic_confusion flag set"]

    # 2) Düşük transit sayısı (≤ 5) — morphology zayıf
    if transits is not None and transits <= 5:
        reasons.append(f"n_transits={transits:.0f} (low; morphology weak)")
        # Diğer testler de zayıfsa LOW_TRANSIT_COUNT birincil
        secondary_weak = secondary is None or abs(secondary) < 500
        odd_even_weak = odd_even is None or abs(odd_even) < 1.5
        if secondary_weak and odd_even_weak:
            return "LOW_TRANSIT_COUNT", reasons

    # 3) V şekli: steepness yüksek (1.0 = tam üçgen)
    if steepness is not None and steepness >= 0.9:
        return "V_SHAPE", [f"steepness={steepness:.2f} (triangular profile)"]

    # 4) Zayıf ikincil
    if secondary is not None and abs(secondary) < 100:
        return "WEAK_SECONDARY", [f"secondary_eclipse_depth={secondary:.1f} ppm (weak)"]

    # 5) Zayıf odd/even
    if odd_even is not None and abs(odd_even) < 1.0:
        return "WEAK_ODD_EVEN", [f"odd_even_mismatch={odd_even:.2f} (weak)"]

    # 6) Duration anomalisi
    if duration_hours is not None and period_days is not None:
        ratio = duration_hours / (period_days * 24.0)
        if ratio > 0.2 or ratio < 0.01:
            return "DURATION_ANOMALY", [f"duration/period={ratio:.3f}"]

    # 7) Yıldız değişkenliği
    if variability is not None and variability > 1000:
        return "STELLAR_VARIABILITY", [f"variability_amplitude={variability:.0f} ppm"]

    # 8) Blending / dilution
    if dilution is not None and dilution < 0.5:
        return "BLENDING", [f"dilution={dilution:.2f} (< 0.5)"]

    # 9) Grazing: depth variance yüksek
    if depth_variance is not None and depth_variance > 0.1:
        return "GRAZING", [f"depth_variance={depth_variance:.3f}"]

    # 10) Simetri bozukluğu
    if symmetry is not None and abs(symmetry) > 0.3:
        return "OTHER", [f"transit_symmetry={symmetry:.3f} (asymmetric)"]

    return "OTHER", reasons or ["no specific trigger matched"]


def summarize_leaks(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Tüm leak satırları için kategori dağılımını özetler.

    Returns
    -------
    dict with keys:
        ``total``: toplam leak sayısı
        ``by_category``: kategori → adet
        ``by_family``: aile → adet
        ``details``: her leak için ayrıntılı sınıflandırma
    """
    leak_rows = [r for r in rows if str(r.get("outcome")) == "leaked_as_candidate"]
    counter = Counter()
    by_family: Counter = Counter()
    details = []

    for row in leak_rows:
        category, reasons = classify_leak(row)
        counter[category] += 1
        by_family[str(row.get("family", "unknown"))] += 1
        details.append({
            "scenario_id": row.get("scenario_id"),
            "family": row.get("family"),
            "category": category,
            "reasons": reasons,
            "fpp": row.get("fpp"),
            "n_transits": row.get("n_transits") or row.get("number_of_transits"),
            "depth_ppm": row.get("depth_ppm") or row.get("depth"),
            "snr": row.get("snr"),
        })

    total = len(leak_rows)
    by_cat = dict(counter.most_common())
    percentages = {k: (100.0 * v / total if total else 0.0) for k, v in by_cat.items()}

    return {
        "total": total,
        "by_category": by_cat,
        "by_category_percent": {k: round(v, 2) for k, v in percentages.items()},
        "by_family": dict(by_family.most_common()),
        "details": details,
    }


__all__ = ["LEAKAGE_CATEGORIES", "classify_leak", "summarize_leaks"]
PY_EOF

echo "Wrote astrotransit/validation/leakage_taxonomy.py"

# 2) Test
cat > tests/test_leakage_taxonomy.py <<'PY_EOF'
"""Tests for the adversarial FP leakage taxonomy."""

from astrotransit.validation.leakage_taxonomy import (
    LEAKAGE_CATEGORIES,
    classify_leak,
    summarize_leaks,
)


def test_categories_are_stable():
    assert "LOW_TRANSIT_COUNT" in LEAKAGE_CATEGORIES
    assert "V_SHAPE" in LEAKAGE_CATEGORIES
    assert "OTHER" in LEAKAGE_CATEGORIES


def test_low_transit_count():
    row = {"n_transits": 3, "secondary_eclipse_depth_ppm": 50, "odd_even_mismatch": 0.5}
    cat, reasons = classify_leak(row)
    assert cat == "LOW_TRANSIT_COUNT"
    assert any("n_transits" in r for r in reasons)


def test_v_shape():
    row = {"n_transits": 15, "steepness": 1.0}
    cat, _ = classify_leak(row)
    assert cat == "V_SHAPE"


def test_harmonic():
    row = {"harmonic_confusion": True}
    cat, _ = classify_leak(row)
    assert cat == "HARMONIC_CONFUSION"


def test_blending():
    row = {"n_transits": 15, "dilution": 0.3, "steepness": 0.5}
    cat, _ = classify_leak(row)
    assert cat == "BLENDING"


def test_summarize():
    rows = [
        {"outcome": "leaked_as_candidate", "n_transits": 3, "family": "f1",
         "secondary_eclipse_depth_ppm": 50, "odd_even_mismatch": 0.5},
        {"outcome": "leaked_as_candidate", "n_transits": 15, "steepness": 1.0, "family": "f2"},
        {"outcome": "rejected_at_vetting", "family": "f1"},
    ]
    summary = summarize_leaks(rows)
    assert summary["total"] == 2
    assert summary["by_category"]["LOW_TRANSIT_COUNT"] == 1
    assert summary["by_category"]["V_SHAPE"] == 1
    assert summary["by_family"]["f1"] == 1
    assert summary["by_family"]["f2"] == 1


def test_no_leaks():
    summary = summarize_leaks([{"outcome": "rejected_at_vetting"}])
    assert summary["total"] == 0
    assert summary["by_category"] == {}
PY_EOF

echo "Wrote tests/test_leakage_taxonomy.py"

# 3) Analysis script
cat > scripts/roadmap/analyze_adversarial_leaks.py <<'PY_EOF'
"""Analyze adversarial FP leakage cases and produce a report."""

import json
import sys
from pathlib import Path

from astrotransit.validation.leakage_taxonomy import summarize_leaks


def main() -> int:
    rows_path = Path("validation_runs/final_acceptance_v1/adversarial_fp/rows.jsonl")
    if not rows_path.exists():
        print(f"ERROR: {rows_path} not found", file=sys.stderr)
        return 1

    rows = []
    with rows_path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    print(f"Loaded {len(rows)} rows from {rows_path}")
    summary = summarize_leaks(rows)

    # Print human-readable summary
    print()
    print(f"=== Leakage Summary ===")
    print(f"Total leaks: {summary['total']}")
    print()
    print("By category:")
    for cat, cnt in summary["by_category"].items():
        pct = summary["by_category_percent"][cat]
        print(f"  {cat:25s} {cnt:3d} ({pct:5.1f}%)")
    print()
    print("By family:")
    for fam, cnt in summary["by_family"].items():
        print(f"  {fam:30s} {cnt:3d}")
    print()
    print("Details:")
    for d in summary["details"]:
        print(f"  {d['scenario_id']:40s} → {d['category']:25s} fpp={d['fpp']}")

    # Write markdown report
    out_md = Path("docs/adversarial_fp_leakage_analysis.md")
    lines = [
        "# Adversarial FP Leakage Analysis",
        "",
        f"Total leaks: **{summary['total']}**",
        "",
        "## By category",
        "",
        "| Category | Count | % |",
        "|---|---:|---:|",
    ]
    for cat, cnt in summary["by_category"].items():
        pct = summary["by_category_percent"][cat]
        lines.append(f"| {cat} | {cnt} | {pct:.1f}% |")
    lines += ["", "## By family", "", "| Family | Count |", "|---|---:|"]
    for fam, cnt in summary["by_family"].items():
        lines.append(f"| {fam} | {cnt} |")
    lines += ["", "## Per-scenario detail", "", "| Scenario | Family | Category | FPP | Reasons |", "|---|---|---|---|---|"]
    for d in summary["details"]:
        reasons = "; ".join(d["reasons"])
        lines.append(
            f"| `{d['scenario_id']}` | {d['family']} | {d['category']} | {d['fpp']} | {reasons} |"
        )
    out_md.write_text("\n".join(lines) + "\n")
    print()
    print(f"Wrote {out_md}")

    # Write JSON summary
    out_json = Path("validation_runs/final_acceptance_v1/adversarial_fp/leakage_taxonomy.json")
    out_json.write_text(json.dumps(summary, indent=2))
    print(f"Wrote {out_json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
PY_EOF

chmod +x scripts/roadmap/analyze_adversarial_leaks.py
echo "Wrote scripts/roadmap/analyze_adversarial_leaks.py"

# 4) Confusion matrix script
cat > scripts/roadmap/confusion_matrix.py <<'PY_EOF'
"""Build a confusion matrix from adversarial FP rows.jsonl."""

import json
import sys
from collections import Counter
from pathlib import Path


def main() -> int:
    rows_path = Path("validation_runs/final_acceptance_v1/adversarial_fp/rows.jsonl")
    if not rows_path.exists():
        print(f"ERROR: {rows_path} not found", file=sys.stderr)
        return 1

    rows = []
    with rows_path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    # Determine expected (FP vs planet) from family
    # We know planetary_control is the only "planet" family
    PLANET_FAMILIES = {"planetary_control"}
    REJECT_OUTCOMES = {
        "rejected_at_detection",
        "rejected_at_cascade",
        "rejected_at_vetting",
        "rejected_at_anomaly",
    }
    LEAK = "leaked_as_candidate"

    # 2x2 matrix
    matrix = Counter()
    for r in rows:
        fam = str(r.get("family", ""))
        expected = "planet" if fam in PLANET_FAMILIES else "fp"
        outcome = str(r.get("outcome", ""))
        if outcome in REJECT_OUTCOMES:
            predicted = "fp"  # rejected = predicted FP
        elif outcome == LEAK:
            predicted = "planet"  # accepted = predicted planet
        else:
            continue  # skip errors
        matrix[(expected, predicted)] += 1

    TP = matrix[("fp", "fp")]       # correctly rejected FP
    FN = matrix[("fp", "planet")]   # FP leaked
    TN = matrix[("planet", "planet")]  # correctly accepted planet
    FP = matrix[("planet", "fp")]   # planet rejected (bad)

    # Compute metrics
    total = TP + FN + TN + FP
    specificity = TP / (TP + FN) if (TP + FN) > 0 else None
    sensitivity = TN / (TN + FP) if (TN + FP) > 0 else None  # this is "recall of planets"
    balanced_acc = (specificity + sensitivity) / 2 if (specificity is not None and sensitivity is not None) else None
    precision = TP / (TP + FP) if (TP + FP) > 0 else None
    fpr = FP / (FP + TN) if (FP + TN) > 0 else None  # FP rate on planets
    fnr = FN / (FN + TP) if (FN + TP) > 0 else None  # miss rate on FP

    result = {
        "matrix": {
            "true_fp_predicted_fp": TP,
            "true_fp_predicted_planet": FN,
            "true_planet_predicted_planet": TN,
            "true_planet_predicted_fp": FP,
            "total": total,
        },
        "metrics": {
            "fp_specificity": round(specificity, 4) if specificity is not None else None,
            "planet_recall": round(sensitivity, 4) if sensitivity is not None else None,
            "balanced_accuracy": round(balanced_acc, 4) if balanced_acc is not None else None,
            "precision": round(precision, 4) if precision is not None else None,
            "fpr_on_planets": round(fpr, 4) if fpr is not None else None,
            "fnr_on_fp": round(fnr, 4) if fnr is not None else None,
        },
    }

    # Print
    print("=== Confusion Matrix ===")
    print(f"                 Predicted FP    Predicted Planet")
    print(f"Actual FP        {TP:5d}           {FN:5d}")
    print(f"Actual Planet    {FP:5d}           {TN:5d}")
    print()
    print("Metrics:")
    for k, v in result["metrics"].items():
        print(f"  {k:20s} {v}")

    out = Path("validation_runs/final_acceptance_v1/adversarial_fp/confusion_matrix.json")
    out.write_text(json.dumps(result, indent=2))
    print()
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
PY_EOF

chmod +x scripts/roadmap/confusion_matrix.py
echo "Wrote scripts/roadmap/confusion_matrix.py"

# 5) Run tests
echo
echo "=== Running leakage taxonomy tests ==="
python -m pytest tests/test_leakage_taxonomy.py -v 2>&1 | tail -30

# 6) Run analysis
echo
echo "=== Running leakage analysis ==="
python scripts/roadmap/analyze_adversarial_leaks.py 2>&1 | tail -60

# 7) Run confusion matrix
echo
echo "=== Running confusion matrix ==="
python scripts/roadmap/confusion_matrix.py 2>&1 | tail -30

# 8) Dump vetting pipeline code
echo
echo "=== Dumping astrotransit/quality/vetting.py (first 200 lines) ==="
sed -n '1,200p' astrotransit/quality/vetting.py 2>/dev/null || echo "MISSING"

echo
echo "=== Dumping astrotransit/quality/pipeline.py (first 200 lines) ==="
sed -n '1,200p' astrotransit/quality/pipeline.py 2>/dev/null || echo "MISSING"

echo
echo "=== Dumping astrotransit/quality/scorer.py (first 150 lines) ==="
sed -n '1,150p' astrotransit/quality/scorer.py 2>/dev/null || echo "MISSING"

echo
echo "=== Dumping scripts/validation/run_adversarial_fp_controls.py (first 200 lines) ==="
sed -n '1,200p' scripts/validation/run_adversarial_fp_controls.py 2>/dev/null || echo "MISSING"

echo
echo "=== Dumping astrotransit/pipelines/tess_pipeline.py (first 150 lines) ==="
sed -n '1,150p' astrotransit/pipelines/tess_pipeline.py 2>/dev/null || echo "MISSING"

echo
echo "=== PHASE 1A complete ==="
echo "Log: $LOG"
