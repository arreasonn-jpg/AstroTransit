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
    print("=== Leakage Summary ===")
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
