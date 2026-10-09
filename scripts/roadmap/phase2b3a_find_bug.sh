#!/usr/bin/env bash
# FAZ 2b.3a: locate the secondary_eclipse_snr computation and figure out
# why real TESS data always yields 0.00.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase2b3a_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 2b.3a: find sec_snr bug =="
echo "log: $LOG"

echo
echo "########## 1) Where is secondary_eclipse_snr defined? ##########"
grep -rn "secondary_eclipse_snr" astrotransit/ --include="*.py" | head -30

echo
echo "########## 2) Where is secondary_eclipse_depth computed? ##########"
grep -rn "secondary_eclipse_depth" astrotransit/ --include="*.py" | grep -v "__pycache__" | head -30

echo
echo "########## 3) Show the metrics.py compute_all / secondary-related code ##########"
python - <<'PY'
from pathlib import Path
import re

p = Path("astrotransit/quality/metrics.py")
if not p.exists():
    print("MISSING:", p); raise SystemExit
src = p.read_text()
lines = src.splitlines()

# Show all blocks touching secondary
for i, line in enumerate(lines, 1):
    if "secondary" in line.lower():
        # print the line and 15 lines after
        end = min(len(lines), i+15)
        print(f"\n--- lines {i}-{end} (context around secondary) ---")
        for j in range(i-1, end):
            print(f"{j+1:4d} | {lines[j]}")
        break
PY

echo
echo "########## 4) Full section of metrics.py with secondary_eclipse_snr ##########"
python - <<'PY'
from pathlib import Path
src = Path("astrotransit/quality/metrics.py").read_text()
lines = src.splitlines()
# Find the function/class where sec_snr is assigned
for i, line in enumerate(lines, 1):
    if "secondary_eclipse_snr" in line and "=" in line and "self." not in line:
        # print 40 lines before and after
        start = max(0, i-40)
        end = min(len(lines), i+20)
        print(f"\n--- lines {start+1}-{end} ---")
        for j in range(start, end):
            print(f"{j+1:4d} | {lines[j]}")
        break
PY

echo
echo "########## 5) Show full QualityMetrics dataclass fields ##########"
grep -n "class QualityMetrics\|^    [a-z_]*:" astrotransit/quality/metrics.py | head -40

echo
echo "########## 6) Show where QualityMetricsCalculator computes all ##########"
grep -n "def compute_all\|def _compute\|def compute" astrotransit/quality/metrics.py | head -20

echo
echo "########## 7) Where does vetting read the metric? ##########"
grep -n "secondary_eclipse_snr\|_test_secondary_eclipse_snr" astrotransit/quality/vetting.py

echo
echo "########## 8) Metrics used in the SecSNR test ##########"
sed -n '/def _test_secondary_eclipse_snr/,/return VettingTest/p' astrotransit/quality/vetting.py

echo
echo "########## 9) Show the actual computation for secondary_eclipse_depth ##########"
python - <<'PY'
from pathlib import Path
src = Path("astrotransit/quality/metrics.py").read_text()
lines = src.splitlines()
# Find where sec depth is assigned with = sign
for i, line in enumerate(lines, 1):
    if "secondary_eclipse_depth" in line and "=" in line:
        start = max(0, i-5)
        end = min(len(lines), i+40)
        print(f"\n--- lines {start+1}-{end} ---")
        for j in range(start, end):
            print(f"{j+1:4d} | {lines[j]}")
        print()
PY

echo
echo "########## 10) Quick sanity test: run metrics on a synthetic case ##########"
python - <<'PY'
# Build a synthetic light curve with a clear secondary eclipse at phase 0.5
# and verify what the metric returns.
import numpy as np

try:
    from astrotransit.quality import metrics as qm
    print("imported metrics module")
    names = [n for n in dir(qm) if "secondary" in n.lower() or "class" in n.lower() or "Metrics" in n]
    print(f"relevant names: {names}")
except Exception as e:
    print("import failed:", type(e).__name__, e)
PY

echo
echo "== FAZ 2b.3a DONE =="
