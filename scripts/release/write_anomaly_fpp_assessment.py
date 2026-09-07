#!/usr/bin/env python3
"""
Anomaly+FPP summary'den insan-yorumlu nihai değerlendirme raporu üretir.

Girdi:
    outputs_anomaly_fpp/summary/anomaly_fpp_summary.json

Çıktı:
    outputs_anomaly_fpp/summary/anomaly_fpp_assessment.md
    outputs_anomaly_fpp/summary/anomaly_fpp_assessment.json
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from datetime import datetime, timezone


def optional_float(x):
    """Eksik FPP'yi sıfır risk gibi göstermeden sayıya çevirir."""

    try:
        value = float(x)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def display_optional(value, digits: int = 3) -> str:
    return "NA" if value is None else f"{value:.{digits}f}"


def planet_proxy_sort_value(row: dict) -> float:
    value = optional_float(row.get("p_planet_proxy"))
    return -1.0 if value is None else value


def human_assessment(row: dict) -> tuple[str, int, str]:
    """
    Otomatik triage üstüne insan-yorumlu karar.

    Returns
    -------
    (human_override_decision, human_priority_rank, assessment_note)

    Rank:
        1 = en güçlü
        6 = en zayıf
    """
    target_id = row.get("target_id", "")
    anomaly_flag = row.get("anomaly_flag", "UNKNOWN")
    timing_flag = row.get("timing_flag", "")
    transit_flag = row.get("transit_consistency_flag", "")
    crowding = optional_float(row.get("crowding_ratio"))
    p_neb = optional_float(row.get("p_neb"))
    fpp = optional_float(row.get("simple_fpp"))
    nearest = optional_float(row.get("nearest_neighbor_arcsec"))
    dmag = optional_float(row.get("brightest_neighbor_delta_mag"))

    # 1) Kritik blending / ambiguous host
    if crowding is not None and crowding < 0.60:
        return (
            "DEPRIORITIZED_CONTAMINATION_RISK",
            6,
            "Very low CROWDSAP indicates strong contamination; likely ambiguous/blended host."
        )

    if (
        p_neb is not None
        and p_neb >= 0.70
        and nearest is not None
        and nearest < 5.0
        and dmag is not None
        and dmag < 0.0
    ):
        return (
            "FOLLOWUP_WITH_HOST_AMBIGUITY_WARNING",
            5,
            "Nearby brighter or near-equal-brightness source suggests host ambiguity."
        )

    # 2) Temiz çevre + temiz anomaly
    if (
        anomaly_flag == "CLEAN"
        and crowding is not None
        and crowding > 0.98
        and p_neb is not None
        and p_neb < 0.25
        and nearest is not None
        and nearest > 8.0
    ):
        return (
            "TOP_CLEAN_FOLLOWUP",
            1,
            "Clean anomaly profile and clean environment; strongest current follow-up target."
        )

    # 3) Timing sorunu ama çevre temiz
    if (
        timing_flag == "TIMING_UNSTABLE"
        and crowding is not None
        and crowding > 0.95
        and p_neb is not None
        and p_neb < 0.25
        and nearest is not None
        and nearest > 15.0
    ):
        return (
            "MANUAL_TIMING_REVIEW_REQUIRED",
            3,
            "Environment appears clean; timing instability may reflect ephemeris/midtime methodology."
        )

    # 4) Şekil sorunu ama çevre temiz
    if (
        transit_flag == "EB_SUSPECT"
        and crowding is not None
        and crowding > 0.98
        and p_neb is not None
        and p_neb < 0.10
        and nearest is not None
        and nearest > 8.0
    ):
        return (
            "SHAPE_REVIEW_REQUIRED",
            4,
            "Environment is clean, but folded transit shape requires manual review."
        )

    # 5) REVIEW ama çok kirli değil
    if (
        anomaly_flag == "REVIEW"
        and crowding is not None
        and crowding > 0.90
        and p_neb is not None
        and p_neb < 0.50
    ):
        return (
            "KEEP_WITH_CROWDING_CAUTION",
            2,
            "Moderate crowding/timing concerns, but candidate remains viable."
        )

    # 6) CLEAN ama FPP orta
    if anomaly_flag == "CLEAN" and fpp is not None and fpp < 0.50:
        return (
            "FOLLOWUP_WITH_CAUTION",
            2,
            "Morphology is clean; proxy false-positive terms remain moderately elevated."
        )

    # 7) Varsayılan fallback
    return (
        row.get("triage_decision", "MANUAL_REVIEW_REQUIRED"),
        5,
        row.get("risk_note", "No additional human note.")
    )


def build_markdown(rows: list[dict]) -> str:
    lines = []
    lines.append("# Anomaly + FPP Human Assessment")
    lines.append("")
    lines.append(f"- Created: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Candidates: {len(rows)}")
    lines.append("")

    lines.append("## Ranked summary")
    lines.append("")
    lines.append("| Rank | TIC | Sector | Human decision | Auto triage | Anomaly | FPP | P(planet) | Note |")
    lines.append("|---:|---|---:|---|---|---|---:|---:|---|")

    for r in sorted(rows, key=lambda x: (x["human_priority_rank"], -planet_proxy_sort_value(x))):
        lines.append(
            f"| {r['human_priority_rank']} | {r['target_id']} | {r['sector']} | "
            f"{r['human_override_decision']} | {r.get('triage_decision','')} | "
            f"{r.get('anomaly_flag','')} | {display_optional(optional_float(r.get('simple_fpp')))} | "
            f"{display_optional(optional_float(r.get('p_planet_proxy')))} | {r.get('assessment_note','')} |"
        )

    lines.append("")
    lines.append("## Candidate notes")
    lines.append("")

    for r in sorted(rows, key=lambda x: (x["human_priority_rank"], -planet_proxy_sort_value(x))):
        lines.append(f"### {r['target_id']} (S{r['sector']})")
        lines.append("")
        lines.append(f"- Human decision: **{r['human_override_decision']}**")
        lines.append(f"- Auto triage: `{r.get('triage_decision','')}`")
        lines.append(f"- Anomaly: `{r.get('anomaly_flag','')}` (score={display_optional(optional_float(r.get('anomaly_score')))})")
        lines.append(
            f"- Simple FPP proxy: `{display_optional(optional_float(r.get('simple_fpp')))}` "
            "(NA = not estimated)"
        )
        lines.append(f"- P(planet) proxy: `{display_optional(optional_float(r.get('p_planet_proxy')))}` (NA = not estimated)")
        lines.append(f"- Dominant scenario: `{r.get('dominant_scenario','')}`")
        lines.append(f"- CROWDSAP: `{r.get('crowding_ratio')}`")
        lines.append(f"- Nearest Gaia neighbor: `{r.get('nearest_neighbor_arcsec')}` arcsec")
        lines.append(f"- Brightest-neighbor Δmag: `{r.get('brightest_neighbor_delta_mag')}`")
        lines.append(f"- Note: {r.get('assessment_note','')}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description="Human assessment report writer")
    parser.add_argument(
        "--input-json",
        type=str,
        default="outputs_anomaly_fpp/summary/anomaly_fpp_summary.json",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="outputs_anomaly_fpp/summary",
    )
    args = parser.parse_args()

    input_json = Path(args.input_json)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with input_json.open(encoding="utf-8") as f:
        data = json.load(f)

    rows = data.get("candidates", [])
    enriched = []

    for row in rows:
        decision, rank, note = human_assessment(row)
        row = dict(row)
        row["human_override_decision"] = decision
        row["human_priority_rank"] = rank
        row["assessment_note"] = note
        enriched.append(row)

    # JSON çıktı
    out_json = output_dir / "anomaly_fpp_assessment.json"
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "n_candidates": len(enriched),
        "candidates": enriched,
    }
    with out_json.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # Markdown çıktı
    out_md = output_dir / "anomaly_fpp_assessment.md"
    out_md.write_text(build_markdown(enriched), encoding="utf-8")

    print("Assessment written:")
    print(f"  {out_json}")
    print(f"  {out_md}")


if __name__ == "__main__":
    main()
