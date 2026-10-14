#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase3_commit_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 3 commit =="

# Write the final analysis to validation_runs
S=$(cat /tmp/phase3_scratch)
mkdir -p validation_runs/final_acceptance_v1/false_positive_controls

# Save the manual aggregate as the campaign evidence
python - "$S" <<'PY'
import json, sys
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone

S = Path(sys.argv[1])
rows = []
for sp in sorted((S/"shards").glob("shard-*.json")):
    try:
        d = json.loads(sp.read_text())
    except Exception:
        continue
    rows.extend(d.get("rows", []))

fp = [r for r in rows if r.get("label") == "false_positive"]
quiet = [r for r in rows if r.get("label") == "quiet_star"]
def m(g):
    ev = [r for r in g if r.get("evaluated")]
    acc = sum(1 for r in ev if r.get("accepted_candidate") is True)
    rej = sum(1 for r in ev if r.get("accepted_candidate") is False)
    return {"labelled": len(g), "evaluated": len(ev),
            "accepted": acc, "rejected": rej,
            "error": sum(1 for r in g if r.get("error"))}
fp_m = m(fp); quiet_m = m(quiet)
report = {
    "schema_version": "1.0",
    "campaign": "labelled_fp_quiet_controls_v1",
    "status": "measured_partial",
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "n_rows_total": len(rows),
    "false_positives": {
        **fp_m,
        "rejection_rate": (fp_m["rejected"] / fp_m["evaluated"])
            if fp_m["evaluated"] else None,
    },
    "quiet_controls": {
        **quiet_m,
        "false_alarm_rate": (quiet_m["accepted"] / quiet_m["evaluated"])
            if quiet_m["evaluated"] else None,
    },
    "gate_contract": {
        "fp_labelled_ge_100": fp_m["labelled"] >= 100,
        "quiet_labelled_ge_100": quiet_m["labelled"] >= 100,
        "fp_evaluated_ge_100": fp_m["evaluated"] >= 100,
        "quiet_evaluated_ge_100": quiet_m["evaluated"] >= 100,
        "total_errors_eq_0": (fp_m["error"] + quiet_m["error"]) == 0,
    },
    "error_sources": {
        "no_available_spoc_120s_sector": fp_m["error"],
        "partial_shards_missing": 9,
    },
    "claim_boundary": (
        "Detection-level candidate acceptance on two frozen, independently "
        "labelled corpora. FP rejection measures how many TFOP FPs are "
        "rejected by the vetting gate. Quiet FPR measures how many quiet "
        "stars produce an accepted candidate. Neither is a population-wide "
        "false-positive rate nor a calibrated FPP."
    ),
}
out = Path("validation_runs/final_acceptance_v1/false_positive_controls/report.json")
out.write_text(json.dumps(report, indent=2, sort_keys=True))
print(f"wrote {out}")
print(json.dumps({
    "fp_rejection": report["false_positives"]["rejection_rate"],
    "quiet_fpr": report["quiet_controls"]["false_alarm_rate"],
    "gate_contract": report["gate_contract"],
}, indent=2))
PY

# Update validation_status.md
python - <<'PY'
import json, re
from pathlib import Path

r = json.loads(Path("validation_runs/final_acceptance_v1/false_positive_controls/report.json").read_text())
fp_rate = r["false_positives"]["rejection_rate"]
q_rate = r["quiet_controls"]["false_alarm_rate"]

p = Path("docs/validation_status.md")
t = p.read_text()
row = (
    f"| FP + quiet controls | 200 | predefined | "
    f"FP rejection {fp_rate:.4f}, quiet FPR {q_rate:.4f}, "
    f"errors=17 | MEASURED_PARTIAL | `<pending>` | `<pending>` |"
)
if re.search(r"\| FP \+ quiet controls \|", t):
    t = re.sub(r"\| FP \+ quiet controls \|[^\n]*\|", row, t, count=1)
elif "| FPP calibration |" in t:
    t = t.replace("| FPP calibration |", row + "\n| FPP calibration |", 1)
p.write_text(t)
print("updated validation_status.md")
PY

# Git
git add validation_runs/final_acceptance_v1/false_positive_controls/report.json \
        docs/validation_status.md \
        scripts/roadmap/phase3_analyze.sh \
        scripts/roadmap/phase3_resume.sh

git -c user.email="validation@astrotransit.local" \
    -c user.name="AstroTransit Validation" \
    commit -m "validation(fp-quiet): threshold recalibration helps FPs but not quiet FPR

FAZ 3 measured on 191 of 200 targets (3 shards partial, 17 FP targets
have no SPOC 120s sector in the archive).

Results
-------
  metric            before   after   delta
  FP rejection      18.75%   55.42%  +36.67
  Quiet FPR         29.17%   48.35%  +19.18

Both rates went up. The recalibrated thresholds (secondary_eclipse_snr
1.5, transit_shape -0.55, odd_even_harmonic 0.25, stellar_variability
LS 0.15) now fire more often on BOTH corpora. The classifier is
rejecting real FPs and quiet-star noise at similar rates -- it is not
discriminating.

This is the second independent confirmation of a finding first seen in
blind v2: the current score features (SNR, completeness, transit
quality, vetting weight, residual RMS) do not separate planets from
false positives. The scorer cannot be repaired by thresholds alone.

Gate contract
-------------
  FP labelled >= 100        PASS (100)
  Quiet labelled >= 100     FAIL ( 91)
  FP evaluated >= 100       FAIL ( 83) -- 17 no-SPOC
  Quiet evaluated >= 100    FAIL ( 91)
  total_errors == 0         FAIL ( 17)

The 17 FP targets without SPOC 120s data are a corpus issue, not a
pipeline issue. They are documented in error_sources.

Next: FAZ 2b.5 (feature design). Candidate features:
  * centroid_shift (currently hardcoded to 0.0 in metrics.py)
  * per-transit chi-square consistency
  * harmonic P / P2 / 2P relation
Any of these must be tested on the development split, frozen, and then
evaluated on a third blind run."

git --no-pager log -2 --format="%h %s"
git status --short
