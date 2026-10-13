#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
LOG="$HOME/audit_v2_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== AUDIT V2 — the missing pieces =="

echo
echo "============================================================"
echo "1) vetting.py lines 40-100 — the test category sets"
echo "============================================================"
sed -n '40,100p' astrotransit/quality/vetting.py

echo
echo "============================================================"
echo "2) vetting.py lines 320-360 — the is_fp rule (full)"
echo "============================================================"
sed -n '320,360p' astrotransit/quality/vetting.py

echo
echo "============================================================"
echo "3) run_false_positive_controls.py _evaluate_case_raw"
echo "============================================================"
python - <<'PY'
from pathlib import Path
lines = Path("scripts/validation/run_false_positive_controls.py").read_text().splitlines()
start = next((i for i, l in enumerate(lines, 1) if "def _evaluate_case_raw" in l), None)
if start is None:
    print("NOT FOUND — searching alternate name")
    for i, l in enumerate(lines, 1):
        if "_evaluate_case" in l or "accepted_candidate" in l:
            print(f"{i:4d} | {l}")
else:
    end = start
    for j in range(start, len(lines)):
        if j > start-1 and lines[j].startswith("def "):
            end = j
            break
    else:
        end = len(lines)
    print(f"lines {start}-{end}")
    for k in range(start-1, end):
        print(f"{k+1:4d} | {lines[k]}")
PY

echo
echo "============================================================"
echo "4) scorer.py _compute_vetting_score and _compute_transit_quality_score"
echo "============================================================"
python - <<'PY'
from pathlib import Path
lines = Path("astrotransit/quality/scorer.py").read_text().splitlines()
for name in ("_compute_vetting_score", "_compute_transit_quality_score",
             "_compute_period_consistency", "_compute_physical_consistency"):
    start = next((i for i, l in enumerate(lines, 1) if f"def {name}" in l), None)
    if start is None:
        print(f"\n--- {name} NOT FOUND ---")
        continue
    end = start
    for j in range(start, len(lines)):
        if j > start-1 and lines[j].startswith("    def "):
            end = j
            break
    else:
        end = len(lines)
    print(f"\n--- {name} (lines {start}-{end}) ---")
    for k in range(start-1, end):
        print(f"{k+1:4d} | {lines[k]}")
PY

echo
echo "============================================================"
echo "5) metrics.py line 460-500 — the compute_stellar return"
echo "============================================================"
sed -n '460,500p' astrotransit/quality/metrics.py

echo
echo "============================================================"
echo "6) The current defaults wired into FalsePositiveVetter()"
echo "============================================================"
grep -nA15 "FalsePositiveVetter(" astrotransit/quality/pipeline.py | head -25

echo
echo "== DONE =="
