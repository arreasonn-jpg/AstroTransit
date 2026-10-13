#!/usr/bin/env bash
# FAZ 3 audit fixes — clean version, no regex backreferences.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/patch_vetting_v3_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== patch vetting v3 =="

V="astrotransit/quality/vetting.py"

python - <<'PY'
from pathlib import Path

p = Path("astrotransit/quality/vetting.py")
src = p.read_text()
changes = []

def replace_once(old, new, tag):
    global src
    if old in src:
        src = src.replace(old, new, 1)
        changes.append(f"OK {tag}")
    else:
        changes.append(f"MISS {tag}")

# 1) secondary_eclipse_snr: threshold = 3.0 -> 1.5
replace_once(
    "        snr = float(getattr(metrics.stellar, \"secondary_eclipse_snr\", 0.0) or 0.0)\n"
    "        threshold = 3.0\n",
    "        snr = float(getattr(metrics.stellar, \"secondary_eclipse_snr\", 0.0) or 0.0)\n"
    "        # FAZ 3 audit: 3.0 was calibrated on synthetic EBs (30-80 sigma).\n"
    "        # Real TESS false positives sit at 1-2 sigma; 1.5 is the standard\n"
    "        # z-score cut and still avoids noise-floor crossings.\n"
    "        threshold = 1.5\n",
    "sec_eclipse_snr 3.0->1.5",
)

# 2) transit_shape: threshold = -0.75 -> -0.55
replace_once(
    "        r = float(getattr(metrics.transit, \"shape_correlation\", 0.0) or 0.0)\n"
    "        threshold = -0.75\n",
    "        r = float(getattr(metrics.transit, \"shape_correlation\", 0.0) or 0.0)\n"
    "        # FAZ 3 audit: real V-shaped EBs show r ~ -0.5 to -0.9. -0.55\n"
    "        # catches them without demanding textbook V profiles.\n"
    "        threshold = -0.55\n",
    "transit_shape -0.75->-0.55",
)

# 3) odd_even_harmonic: threshold = 0.45 -> 0.25
replace_once(
    "        value = float(getattr(metrics.transit, \"odd_even_harmonic\", 0.0) or 0.0)\n"
    "        threshold = 0.45\n",
    "        value = float(getattr(metrics.transit, \"odd_even_harmonic\", 0.0) or 0.0)\n"
    "        # FAZ 3 audit: real TESS false positives show 0.0-0.3 on this metric.\n"
    "        threshold = 0.25\n",
    "odd_even_harmonic 0.45->0.25",
)

# 4) stellar_variability: LS gate 0.5 -> 0.15, and warn 0.35 -> 0.10
replace_once(
    "        if ls_peak > 0.5 and amplitude > 3000.0:",
    "        # FAZ 3 audit: quiet TESS stars have LS peak < 0.1 in the period\n"
    "        # range we fold on. The 0.5 gate never fires on real data.\n"
    "        if ls_peak > 0.15 and amplitude > 3000.0:",
    "stellar_variability FAIL gate 0.5->0.15",
)
replace_once(
    "        elif ls_peak > 0.35 and amplitude > 2000.0:",
    "        elif ls_peak > 0.10 and amplitude > 2000.0:",
    "stellar_variability WARN gate 0.35->0.10",
)

p.write_text(src)
print("  changes:")
for c in changes:
    print(f"    - {c}")
PY

echo
echo "########## Syntax check ##########"
python -c "import ast; ast.parse(open('$V').read()); print('syntax OK')"

echo
echo "########## Show patched thresholds ##########"
grep -n "threshold = 1.5\|threshold = -0.55\|threshold = 0.25\|ls_peak > 0.15\|ls_peak > 0.10" "$V"

echo
echo "########## Ruff ##########"
ruff check "$V" astrotransit/quality/pipeline.py \
    scripts/validation/run_false_positive_controls.py 2>&1 | tail -8

echo
echo "########## Tests ##########"
python -m pytest tests/test_quality_vetting.py tests/test_quality_pipeline.py -q 2>&1 | tail -10

echo
echo "== DONE =="
