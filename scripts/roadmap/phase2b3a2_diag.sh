#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase2b3a2_diag_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 2b.3a.2 diag =="
echo "log: $LOG"

echo
echo "########## 1) Failing vetting test bodies ##########"
python - <<'PY'
from pathlib import Path
lines = Path("tests/test_quality_vetting.py").read_text().splitlines()
for name in ("def test_secondary_fail", "def test_vet_eb_candidate"):
    for i, l in enumerate(lines):
        if l.strip().startswith(name):
            start = i
            end = i
            # read until next top-level def
            for j in range(i+1, len(lines)):
                if lines[j].startswith("def ") or (lines[j] and not lines[j][0].isspace() and lines[j].strip()):
                    end = j
                    break
            else:
                end = len(lines)
            print(f"\n--- {name} (lines {start+1}-{end}) ---")
            for j in range(start, end):
                print(f"{j+1:4d} | {lines[j]}")
            break
PY

echo
echo "########## 2) Exact assertion failure messages ##########"
python -m pytest tests/test_quality_vetting.py::test_secondary_fail tests/test_quality_vetting.py::test_vet_eb_candidate -v 2>&1 | tail -60

echo
echo "########## 3) Fixture values: what does a synthetic EB produce now? ##########"
python - <<'PY'
# Reproduce what the failing tests likely do, and see what the new metrics return.
import numpy as np
from astrotransit.quality.metrics import QualityMetricsCalculator
from astrotransit.detection.cascade import CascadeCandidate

# Try to build typical fixtures from the failing tests
# 1) Secondary eclipse with modest depth
n = 2000
cadence = 120.0 / 86400.0
time = np.arange(n, dtype=float) * cadence
period = 2.0
t0 = 0.0
flux = np.ones(n)

# Primary: depth 1%, duration 0.15d
phase = ((time - t0) % period) / period
primary_mask = np.abs(phase) < (0.15 / (2 * period))
flux[primary_mask] -= 0.01

# Secondary: depth 0.5%, at phase 0.5
secondary_mask = np.abs(phase - 0.5) < (0.15 / (2 * period))
flux[secondary_mask] -= 0.005

# Noise ~2000 ppm
rng = np.random.default_rng(42)
flux += rng.normal(0, 2000e-6, n)

# Try compute_stellar via a minimal wrapper
class Dummy:
    def __init__(self, time, flux):
        self.time = time
        self.flux = flux

# Direct call to the static method
sec_depth = QualityMetricsCalculator._check_secondary_eclipse(
    time, flux, period, t0
)
sec_snr = QualityMetricsCalculator._compute_secondary_eclipse_snr(
    time, flux, period, t0, 0.15
)
print(f"_check_secondary_eclipse -> depth={sec_depth*1e6:.1f} ppm")
print(f"_compute_secondary_eclipse_snr -> snr={sec_snr:.3f}")

# Now with deeper secondary (10% of primary = 1000 ppm)
flux2 = np.ones(n)
flux2[primary_mask] -= 0.01
flux2[secondary_mask] -= 0.001  # 1000 ppm secondary
flux2 += rng.normal(0, 2000e-6, n)
sec_depth2 = QualityMetricsCalculator._check_secondary_eclipse(time, flux2, period, t0)
sec_snr2 = QualityMetricsCalculator._compute_secondary_eclipse_snr(time, flux2, period, t0, 0.15)
print(f"\nSecondary 1000 ppm:")
print(f"  depth={sec_depth2*1e6:.1f} ppm, snr={sec_snr2:.3f}")
PY

echo
echo "########## 4) Fix ruff lint in test file ##########"
python - <<'PY'
from pathlib import Path
p = Path("tests/test_metrics_dip_amplitude.py")
src = p.read_text()

old = '''def test_no_dip_returns_zero():
    flux = np.ones(100)
    m = np.zeros(100, dtype=bool); m[10:25] = True
    o = np.zeros(100, dtype=bool); o[30:90] = True
    depth, se = QualityMetricsCalculator._dip_amplitude(flux, m, o)
    assert depth == 0.0'''

new = '''def test_no_dip_returns_zero():
    flux = np.ones(100)
    m = np.zeros(100, dtype=bool)
    m[10:25] = True
    o = np.zeros(100, dtype=bool)
    o[30:90] = True
    depth, _se = QualityMetricsCalculator._dip_amplitude(flux, m, o)
    assert depth == 0.0'''

if old in src:
    src = src.replace(old, new, 1)
    p.write_text(src)
    print("  patched test_no_dip_returns_zero")
else:
    print("  WARN: old block not found")

# Also check for the other unused `se` in test_no_dip and test_shallow etc
import re
# Verify no other semicolons
rest = p.read_text()
if ";" in rest and "dtype=bool)" in rest:
    # Count semicolons in the file
    print(f"  semicolons remaining: {rest.count(';')}")
PY

echo
echo "########## 5) Ruff check on test file ##########"
ruff check tests/test_metrics_dip_amplitude.py 2>&1 | tail -8

echo
echo "== DIAG DONE =="
