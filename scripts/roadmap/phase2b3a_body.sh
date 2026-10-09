#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase2b3a_body_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 2b.3a body =="
echo "log: $LOG"

echo
echo "########## 1) Full body of _compute_secondary_eclipse_snr ##########"
python - <<'PY'
from pathlib import Path
src = Path("astrotransit/quality/metrics.py").read_text()
lines = src.splitlines()

# Find the def _compute_secondary_eclipse_snr line
start = None
for i, line in enumerate(lines, 1):
    if "def _compute_secondary_eclipse_snr" in line:
        start = i
        break
if start is None:
    print("NOT FOUND"); raise SystemExit(1)

# Find next top-level def/class after start
end = len(lines)
for j in range(start, len(lines)):
    ln = lines[j]
    # a new method/function starts with def at indent 4, or class at indent 0
    if j > start and (ln.startswith("    def ") or ln.startswith("class ") or ln.startswith("def ")):
        end = j
        break

print(f"function lines {start}-{end}")
print()
for j in range(start-1, end):
    print(f"{j+1:4d} | {lines[j]}")
PY

echo
echo "########## 2) Call site in compute_stellar (lines 440-482) ##########"
sed -n '440,482p' astrotransit/quality/metrics.py

echo
echo "########## 3) _compute_secondary_eclipse_depth if it exists ##########"
grep -n "_compute_secondary" astrotransit/quality/metrics.py

echo
echo "########## 4) All methods inside QualityMetricsCalculator ##########"
grep -n "    def " astrotransit/quality/metrics.py

echo
echo "########## 5) Run function on a synthetic case with clear secondary ##########"
python - <<'PY'
import numpy as np
from astrotransit.quality.metrics import QualityMetricsCalculator
from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve
from astrotransit.detection.cascade import CascadeCandidate

# Build a light curve with primary + secondary eclipse (both at P=2d)
rng = np.random.default_rng(42)
P = 2.0
n = 4000
cadence = 120.0 / 86400.0  # 120s in days
time = np.arange(n, dtype=float) * cadence
flux = np.ones(n)
# primary: depth 1%, duration 0.15d
phase = np.mod(time, P) / P
primary_mask = (phase < 0.04) | (phase > 0.96)
flux[primary_mask] -= 0.010
# secondary: depth 0.5% at phase ~0.5 (2% wide)
sec_mask = (phase > 0.48) & (phase < 0.52)
flux[sec_mask] -= 0.005
# noise
flux += rng.normal(0, 300e-6, n)

# Wrap into DetrendedLightCurve
try:
    dlc = DetrendedLightCurve(time=time, flux=flux, flux_err=np.full(n, 300e-6),
                              target_id="SYN", sector=1, trend=np.ones(n))
except Exception as e:
    print("DetrendedLightCurve build failed:", e)
    # Try alternative signature
    import inspect
    sig = inspect.signature(DetrendedLightCurve)
    print("signature:", sig)
    raise SystemExit

# Candidate
try:
    cand = CascadeCandidate(target_id="SYN", sector=1, period=P, depth=0.010,
                            duration=0.15, t0=0.0, snr=30.0, status=None)
except Exception as e:
    print("CascadeCandidate build failed:", e)
    import inspect
    print("signature:", inspect.signature(CascadeCandidate))
    raise SystemExit

calc = QualityMetricsCalculator(cadence_sec=120.0)
try:
    stellar = calc.compute_stellar(dlc, cand)
    print(f"secondary_eclipse_depth    = {stellar.secondary_eclipse_depth*1e6:.1f} ppm")
    print(f"secondary_eclipse_snr      = {stellar.secondary_eclipse_snr:.3f}")
    print(f"variability_amplitude      = {stellar.variability_amplitude:.1f}")
    print(f"lomb_scargle_peak          = {stellar.lomb_scargle_peak:.4f}")
except Exception as e:
    import traceback
    traceback.print_exc()
PY

echo
echo "== DONE =="
