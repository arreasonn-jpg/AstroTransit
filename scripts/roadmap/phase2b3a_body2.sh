#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase2b3a_body2_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 2b.3a body2 =="

echo
echo "########## 1) _dip_amplitude (line 867) ##########"
python - <<'PY'
from pathlib import Path
lines = Path("astrotransit/quality/metrics.py").read_text().splitlines()
start = next(i for i, l in enumerate(lines, 1) if "def _dip_amplitude" in l)
end = next((j for j in range(start, len(lines)) if lines[j].startswith("    def ") or lines[j].startswith("class ")), len(lines))
print(f"lines {start}-{end}")
for j in range(start-1, end):
    print(f"{j+1:4d} | {lines[j]}")
PY

echo
echo "########## 2) _check_secondary_eclipse (line 1014) ##########"
python - <<'PY'
from pathlib import Path
lines = Path("astrotransit/quality/metrics.py").read_text().splitlines()
start = next(i for i, l in enumerate(lines, 1) if "def _check_secondary_eclipse" in l)
end = next((j for j in range(start, len(lines)) if lines[j].startswith("    def ") or lines[j].startswith("class ")), len(lines))
print(f"lines {start}-{end}")
for j in range(start-1, end):
    print(f"{j+1:4d} | {lines[j]}")
PY

echo
echo "########## 3) _raw_odd_even_at (line 714) ##########"
python - <<'PY'
from pathlib import Path
lines = Path("astrotransit/quality/metrics.py").read_text().splitlines()
start = next(i for i, l in enumerate(lines, 1) if "def _raw_odd_even_at" in l)
end = next((j for j in range(start, len(lines)) if lines[j].startswith("    def ") or lines[j].startswith("class ")), len(lines))
print(f"lines {start}-{end}")
for j in range(start-1, end):
    print(f"{j+1:4d} | {lines[j]}")
PY

echo
echo "########## 4) Snapshot: any hardcoded thresholds in metrics.py ##########"
grep -nE "(<|>|<=|>=|==)\s*[0-9]+\.?[0-9]*" astrotransit/quality/metrics.py | grep -E "snr|sigma|8\.0|3\.0|2\.0" | head -20

echo
echo "== DONE =="
