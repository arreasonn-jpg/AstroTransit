#!/usr/bin/env python3
"""
Human-assessed anomaly+FPP sonuçlarından release note üretir.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from datetime import datetime, timezone


def optional_float(x):
    try:
        value = float(x)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def display_optional(value, digits: int = 3) -> str:
    return "NA" if value is None else f"{value:.{digits}f}"


def main():
    parser = argparse.ArgumentParser(description="Write anomaly+FPP release note")
    parser.add_argument(
        "--input-json",
        type=str,
        default="outputs_anomaly_fpp/summary/anomaly_fpp_assessment.json",
    )
    parser.add_argument(
        "--output-md",
        type=str,
        default="outputs_anomaly_fpp/summary/anomaly_fpp_release_note.md",
    )
    args = parser.parse_args()

    input_json = Path(args.input_json)
    output_md = Path(args.output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)

    with input_json.open(encoding="utf-8") as f:
        data = json.load(f)

    rows = data.get("candidates", [])
    rows = sorted(rows, key=lambda r: r.get("human_priority_rank", 999))

    top_clean = [r for r in rows if r.get("human_override_decision") == "TOP_CLEAN_FOLLOWUP"]
    keep_caution = [r for r in rows if r.get("human_override_decision") == "KEEP_WITH_CROWDING_CAUTION"]
    timing_review = [r for r in rows if r.get("human_override_decision") == "MANUAL_TIMING_REVIEW_REQUIRED"]
    shape_review = [r for r in rows if r.get("human_override_decision") == "SHAPE_REVIEW_REQUIRED"]
    host_amb = [r for r in rows if r.get("human_override_decision") == "FOLLOWUP_WITH_HOST_AMBIGUITY_WARNING"]
    deprioritized = [r for r in rows if "DEPRIORITIZED" in r.get("human_override_decision", "")]

    lines = []
    lines.append("# Anomaly + FPP Final Assessment Note")
    lines.append("")
    lines.append(f"- Created: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Evaluated candidates: {len(rows)}")
    lines.append("")

    lines.append("## Executive summary")
    lines.append("")
    lines.append(
        "A standalone anomaly-detection and simple false-positive proxy framework was applied "
        "to six MCMC-converged non-TOI transit candidates. "
        "The analysis combined residual diagnostics, folded-transit consistency, timing stability, "
        "crowding metadata (CROWDSAP), and Gaia DR3 local-neighborhood checks."
    )
    lines.append("")
    lines.append(
        "The main outcome is that the six candidates are not equally strong: "
        "two remain comparatively strong follow-up targets, "
        "two require manual methodological review, "
        "and two show substantial host-association / contamination concerns."
    )
    lines.append("")

    lines.append("## Human-ranked candidate ordering")
    lines.append("")
    lines.append("| Rank | TIC | Sector | Decision | Anomaly | FPP | P(planet) proxy | Note |")
    lines.append("|---:|---|---:|---|---|---:|---:|---|")
    for r in rows:
        lines.append(
            f"| {r.get('human_priority_rank')} | {r.get('target_id')} | {r.get('sector')} | "
            f"{r.get('human_override_decision')} | {r.get('anomaly_flag')} | "
            f"{display_optional(optional_float(r.get('simple_fpp')))} | "
            f"{display_optional(optional_float(r.get('p_planet_proxy')))} | "
            f"{r.get('assessment_note')} |"
        )
    lines.append("")

    if top_clean:
        lines.append("## Strongest retained targets")
        lines.append("")
        for r in top_clean + keep_caution:
            lines.append(f"### {r['target_id']} (S{r['sector']})")
            lines.append("")
            lines.append(f"- Decision: **{r['human_override_decision']}**")
            lines.append(f"- Anomaly: `{r['anomaly_flag']}`")
            lines.append(
                f"- Simple FPP proxy: `{display_optional(optional_float(r.get('simple_fpp')))}` "
                "(NA = not estimated)"
            )
            lines.append(f"- CROWDSAP: `{r.get('crowding_ratio')}`")
            lines.append(f"- Gaia nearest neighbor: `{r.get('nearest_neighbor_arcsec')}` arcsec")
            lines.append(f"- Δmag: `{r.get('brightest_neighbor_delta_mag')}`")
            lines.append(f"- Assessment: {r['assessment_note']}")
            lines.append("")

    if timing_review or shape_review:
        lines.append("## Manual-review targets")
        lines.append("")
        for r in timing_review + shape_review:
            lines.append(f"### {r['target_id']} (S{r['sector']})")
            lines.append("")
            lines.append(f"- Decision: **{r['human_override_decision']}**")
            lines.append(f"- Timing flag: `{r.get('timing_flag')}`")
            lines.append(f"- Transit-consistency flag: `{r.get('transit_consistency_flag')}`")
            lines.append(
                f"- Simple FPP proxy: `{display_optional(optional_float(r.get('simple_fpp')))}` "
                "(NA = not estimated)"
            )
            lines.append(f"- Environment note: CROWDSAP=`{r.get('crowding_ratio')}`, nearest Gaia neighbor=`{r.get('nearest_neighbor_arcsec')}` arcsec")
            lines.append(f"- Assessment: {r['assessment_note']}")
            lines.append("")

    if host_amb or deprioritized:
        lines.append("## Host-ambiguity / contamination-limited targets")
        lines.append("")
        for r in host_amb + deprioritized:
            lines.append(f"### {r['target_id']} (S{r['sector']})")
            lines.append("")
            lines.append(f"- Decision: **{r['human_override_decision']}**")
            lines.append(f"- CROWDSAP: `{r.get('crowding_ratio')}`")
            lines.append(f"- Dominant FP scenario: `{r.get('dominant_scenario')}`")
            lines.append(f"- Nearest Gaia neighbor: `{r.get('nearest_neighbor_arcsec')}` arcsec")
            lines.append(f"- Brightest-neighbor Δmag: `{r.get('brightest_neighbor_delta_mag')}`")
            lines.append(
                f"- Simple FPP proxy: `{display_optional(optional_float(r.get('simple_fpp')))}` "
                "(NA = not estimated)"
            )
            lines.append(f"- Assessment: {r['assessment_note']}")
            lines.append("")

    lines.append("## Recommended operational outcome")
    lines.append("")
    lines.append("- Promote **TIC 354532520** as the cleanest current follow-up target.")
    lines.append("- Retain **TIC 347299560** with explicit crowding caution.")
    lines.append("- Perform manual timing review for **TIC 352146741**.")
    lines.append("- Perform folded-transit/shape review for **TIC 427332476**.")
    lines.append("- Mark **TIC 439946042** as host-ambiguous.")
    lines.append("- Deprioritize **TIC 439949948** due to strong contamination/blending risk.")
    lines.append("")

    lines.append("## Caveat")
    lines.append("")
    lines.append(
        "This FPP framework is a proxy diagnostic layer and not a formal validation engine. "
        "Residual diagnostics are based on simplified standalone modeling and may over-penalize some "
        "otherwise viable signals. Nevertheless, the Gaia + CROWDSAP contamination findings are "
        "considered operationally meaningful."
    )
    lines.append("")

    output_md.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Release note written: {output_md}")


if __name__ == "__main__":
    main()
