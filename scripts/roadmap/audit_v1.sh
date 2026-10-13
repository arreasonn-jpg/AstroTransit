#!/usr/bin/env bash
# Read-only code audit. Prints the exact decision logic behind
# accepted_candidate in the FP+Quiet runner and the vetting tests
# that can promote a candidate to is_false_positive=True.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1

LOG="$HOME/audit_v1_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== CODE AUDIT V1 (read-only) =="
echo "log: $LOG"
echo "started: $(date -Iseconds)"

echo
echo "============================================================"
echo "SECTION A — FP+Quiet runner: what is accepted_candidate?"
echo "============================================================"
echo
echo "--- _evaluate_case full body ---"
python - <<'PY'
from pathlib import Path
lines = Path("scripts/validation/run_false_positive_controls.py").read_text().splitlines()
start = next((i for i, l in enumerate(lines, 1) if "def _evaluate_case" in l), None)
if start is None:
    print("NOT FOUND"); raise SystemExit(1)
end = start
for j in range(start, len(lines)):
    if j > start-1 and (lines[j].startswith("def ") or lines[j].startswith("class ")):
        end = j
        break
else:
    end = len(lines)
print(f"lines {start}-{end}")
for k in range(start-1, end):
    print(f"{k+1:4d} | {lines[k]}")
PY

echo
echo "--- quality evaluation results struct used by FP+Quiet ---"
python - <<'PY'
from pathlib import Path
src = Path("scripts/validation/run_false_positive_controls.py").read_text()
lines = src.splitlines()
in_eval = False
for i, l in enumerate(lines, 1):
    if "def _evaluate_case" in l:
        in_eval = True
    if in_eval and "return" in l and "accepted" in l:
        print(f"{i:4d} | {l}")
PY

echo
echo "============================================================"
echo "SECTION B — vetting.py: which tests exist, which are HARD/SOFT?"
echo "============================================================"
echo
echo "--- HARD_FAIL_TESTS and SOFT_FAIL_TESTS ---"
grep -nE "HARD_FAIL_TESTS|SOFT_FAIL_TESTS|CRITICAL_FP_TESTS|is_false_positive" \
    astrotransit/quality/vetting.py | head -30

echo
echo "--- how is_false_positive is computed ---"
python - <<'PY'
from pathlib import Path
lines = Path("astrotransit/quality/vetting.py").read_text().splitlines()
for i, l in enumerate(lines, 1):
    if "is_fp = " in l or "is_false_positive=" in l or "hard_fails" in l or "soft_fails" in l:
        print(f"{i:4d} | {l}")
PY

echo
echo "--- the exact threshold lines inside each test method ---"
python - <<'PY'
from pathlib import Path
import re
lines = Path("astrotransit/quality/vetting.py").read_text().splitlines()
in_test = False
test_name = None
for i, l in enumerate(lines, 1):
    if re.match(r"\s+def _test_", l):
        test_name = l.strip().split("(")[0].replace("def ", "")
    if test_name and ("threshold" in l.lower() or "if " in l and "verdict" in l):
        print(f"{i:4d} | [{test_name}] {l.strip()}")
PY

echo
echo "============================================================"
echo "SECTION C — scorer.py: score components and class thresholds"
echo "============================================================"
echo
echo "--- WEIGHTS and thresholds ---"
grep -nE "WEIGHTS|class_[abc]_threshold|_normalize_linear" \
    astrotransit/quality/scorer.py | head -30

echo
echo "--- full _assign_class ---"
python - <<'PY'
from pathlib import Path
lines = Path("astrotransit/quality/scorer.py").read_text().splitlines()
start = next((i for i, l in enumerate(lines, 1) if "def _assign_class" in l), None)
if start is None:
    print("NOT FOUND"); raise SystemExit(1)
end = start
for j in range(start, len(lines)):
    if j > start-1 and lines[j].startswith("    def "):
        end = j
        break
else:
    end = len(lines)
for k in range(start-1, end):
    print(f"{k+1:4d} | {lines[k]}")
PY

echo
echo "--- what does _detect_anomaly return (Class X)? ---"
grep -nA2 "def _detect_anomaly" astrotransit/quality/scorer.py | head -5

echo
echo "============================================================"
echo "SECTION D — metrics.py: which metrics are dead (always 0)?"
echo "============================================================"
echo
echo "--- centroid_shift usage ---"
grep -rn "centroid_shift" astrotransit/ --include="*.py" | head -20

echo
echo "--- dead metric candidates (hardcoded 0.0 or missing compute) ---"
grep -nE "= 0\.0|= 0$|= None" astrotransit/quality/metrics.py | head -30

echo
echo "--- which metrics are actually computed in compute_stellar ---"
grep -n "compute_stellar\|compute_transit\|compute_photometric" astrotransit/quality/metrics.py | head -10

echo
echo "============================================================"
echo "SECTION E — pipeline.py: the vetting->score order"
echo "============================================================"
echo
grep -nE "vetting|score|anomaly" astrotransit/quality/pipeline.py | head -30

echo
echo "============================================================"
echo "SECTION F — how does the anomaly stage work?"
echo "============================================================"
echo
echo "--- anomaly_scorer: what raises a REJECT flag? ---"
grep -nE "REJECT|SEVERE|n_severe|anomaly_flag" astrotransit/quality/anomaly_scorer.py | head -20

echo
echo "== DONE =="
