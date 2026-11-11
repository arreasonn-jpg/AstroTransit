#!/usr/bin/env bash
# FAZ 2b.5 recon: TESS FITS structure, existing centroid plumbing,
# and integration points. Read-only.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b5_recon_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 2b.5 recon =="
echo "log: $LOG"

echo
echo "########## 1) meta_json in cache ##########"
python - <<'PY'
import numpy as np, json
from pathlib import Path
files = sorted(Path(".cache/astrotransit/tess").glob("*.npz"))
if not files:
    print("  no cache"); raise SystemExit
d = np.load(files[0])
meta = json.loads(str(d["meta_json"]))
print(f"  keys: {sorted(meta.keys())}")
for k in sorted(meta.keys()):
    v = meta[k]
    s = str(v)[:100]
    print(f"    {k}: {s}")
PY

echo
echo "########## 2) tess_client: how are columns selected? ##########"
grep -n "MOM_CENTR\|centroid\|columns\|to_pandas\|lightkurve\|download" \
    astrotransit/data/tess_client.py | head -30

echo
echo "########## 3) tess_client download_lightcurve body ##########"
python - <<'PY'
from pathlib import Path
lines = Path("astrotransit/data/tess_client.py").read_text().splitlines()
start = next((i for i, l in enumerate(lines, 1) if "def download_lightcurve" in l), None)
if start is None:
    print("  NOT FOUND")
else:
    end = start
    for j in range(start, len(lines)):
        if j > start-1 and lines[j].startswith("    def "):
            end = j
            break
    else:
        end = len(lines)
    print(f"  lines {start}-{end}")
    for k in range(start-1, min(end, start+40)):
        print(f"{k+1:4d} | {lines[k]}")
PY

echo
echo "########## 4) Existing centroid plumbing ##########"
grep -rn "centroid_shift_arcsec\|centroid_shift" \
    astrotransit/ --include="*.py" | grep -v "__pycache__" | head -20

echo
echo "########## 5) FPP calculator signature ##########"
grep -nA15 "def compute\|def calculate\|class SimpleFPPCalculator\|class FPPCalculator" \
    astrotransit/quality/fpp/calculator.py | head -30

echo
echo "########## 6) BEB test: what does it expect? ##########"
python - <<'PY'
from pathlib import Path
lines = Path("astrotransit/quality/fpp/beb_test.py").read_text().splitlines()
start = next((i for i, l in enumerate(lines, 1) if "def _indicator_centroid_shift" in l), None)
if start:
    end = start
    for j in range(start, len(lines)):
        if j > start-1 and lines[j].strip().startswith("def "):
            end = j
            break
    else:
        end = len(lines)
    for k in range(start-1, min(end, start+40)):
        print(f"{k+1:4d} | {lines[k]}")
PY

echo
echo "########## 7) How is fpp_data built in the pipeline? ##########"
grep -n "fpp_data\|SimpleFPPCalculator\|\.compute(" astrotransit/quality/pipeline.py | head -20

echo
echo "########## 8) Do we have any TESS FITS samples locally? ##########"
find . -type f \( -name "*.fits" -o -name "*_lc.fits" \) \
    -not -path "./.git/*" -not -path "./.venv/*" 2>/dev/null | head -10

echo
echo "########## 9) What does astroquery return for TESS? ##########"
grep -n "search_lightcurve\|TessLightCurveFile\|LightCurve\|download" \
    astrotransit/data/tess_client.py | head -20

echo
echo "########## 10) metrics.py StellarMetrics dataclass ##########"
python - <<'PY'
from pathlib import Path
lines = Path("astrotransit/quality/metrics.py").read_text().splitlines()
start = next((i for i, l in enumerate(lines, 1) if "class StellarMetrics" in l), None)
if start:
    end = start
    for j in range(start, len(lines)):
        if j > start-1 and lines[j].startswith("class "):
            end = j
            break
    else:
        end = len(lines)
    for k in range(start-1, min(end, start+30)):
        print(f"{k+1:4d} | {lines[k]}")
PY

echo
echo "== DONE =="
