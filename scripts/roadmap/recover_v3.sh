#!/usr/bin/env bash
# Recovery: (1) re-apply v3 thresholds (idempotent)
#           (2) insert missing _target_passes_gate helper
#           (3) verify + commit
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/recover_v3_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== recover v3 =="

V="astrotransit/quality/vetting.py"
R="scripts/validation/run_false_positive_controls.py"

echo
echo "########## 0) Current threshold state in vetting.py ##########"
grep -nE "threshold = 3\.0|threshold = 1\.5|threshold = -0\.75|threshold = -0\.55|threshold = 0\.45|threshold = 0\.25|ls_peak > 0\.5|ls_peak > 0\.15|ls_peak > 0\.35|ls_peak > 0\.10" "$V"

echo
echo "########## 1) Re-apply v3 thresholds (idempotent) ##########"
python - <<'PY'
from pathlib import Path

p = Path("astrotransit/quality/vetting.py")
src = p.read_text()
changes = []

def replace_once(old, new, tag):
    global src
    if old in src:
        src = src.replace(old, new, 1)
        changes.append(f"APPLIED {tag}")
    elif new in src:
        changes.append(f"ALREADY {tag}")
    else:
        changes.append(f"MISS {tag}")

replace_once(
    "        snr = float(getattr(metrics.stellar, \"secondary_eclipse_snr\", 0.0) or 0.0)\n"
    "        threshold = 3.0\n",
    "        snr = float(getattr(metrics.stellar, \"secondary_eclipse_snr\", 0.0) or 0.0)\n"
    "        # FAZ 3 audit: 3.0 was calibrated on synthetic EBs.\n"
    "        # Real TESS false positives sit at 1-2 sigma.\n"
    "        threshold = 1.5\n",
    "sec_eclipse_snr 3.0->1.5",
)
replace_once(
    "        r = float(getattr(metrics.transit, \"shape_correlation\", 0.0) or 0.0)\n"
    "        threshold = -0.75\n",
    "        r = float(getattr(metrics.transit, \"shape_correlation\", 0.0) or 0.0)\n"
    "        # FAZ 3 audit: real V-shaped EBs show r ~ -0.5 to -0.9.\n"
    "        threshold = -0.55\n",
    "transit_shape -0.75->-0.55",
)
replace_once(
    "        value = float(getattr(metrics.transit, \"odd_even_harmonic\", 0.0) or 0.0)\n"
    "        threshold = 0.45\n",
    "        value = float(getattr(metrics.transit, \"odd_even_harmonic\", 0.0) or 0.0)\n"
    "        # FAZ 3 audit: real TESS FPs show 0.0-0.3.\n"
    "        threshold = 0.25\n",
    "odd_even_harmonic 0.45->0.25",
)
replace_once(
    "        if ls_peak > 0.5 and amplitude > 3000.0:",
    "        # FAZ 3 audit: quiet TESS stars have LS peak < 0.1.\n"
    "        if ls_peak > 0.15 and amplitude > 3000.0:",
    "stellar_variability FAIL 0.5->0.15",
)
replace_once(
    "        elif ls_peak > 0.35 and amplitude > 2000.0:",
    "        elif ls_peak > 0.10 and amplitude > 2000.0:",
    "stellar_variability WARN 0.35->0.10",
)

p.write_text(src)
print("  changes:")
for c in changes:
    print(f"    - {c}")

import ast
ast.parse(src)
print("  syntax OK")
PY

echo
echo "########## 2) Insert missing _target_passes_gate helper ##########"
python - <<'PY'
from pathlib import Path

p = Path("scripts/validation/run_false_positive_controls.py")
src = p.read_text()

# Check for actual DEFINITION (not call site)
if "def _target_passes_gate(" in src:
    print("  helper already defined")
    raise SystemExit(0)

anchor = "def _evaluate_case_raw("
if anchor not in src:
    print("  FATAL: anchor _evaluate_case_raw not found")
    raise SystemExit(1)

helper = '''def _target_passes_gate(result: Any, sectors: list[dict[str, Any]]) -> bool:
    """True iff any successful sector passes the vetting gate.

    FAZ 3 audit: accepted_candidate must reflect the classifier, not the
    detector. Uses QualityScore.accepted_for_gate() from each sector;
    falls back to cascade-confirmed when the score object is missing
    (e.g., pre-fit failures).
    """
    try:
        raw_sectors = list(getattr(result, "sector_results", []) or [])
    except Exception:
        return bool(getattr(result, "candidates_confirmed", 0) > 0)
    for item in raw_sectors:
        if not getattr(item, "success", False):
            continue
        quality = getattr(item, "quality", None)
        score = getattr(quality, "score", None) if quality else None
        if score is not None and hasattr(score, "accepted_for_gate"):
            if bool(score.accepted_for_gate()):
                return True
        else:
            if bool(getattr(item, "candidate_confirmed", False)):
                return True
    return False


'''

src = src.replace(anchor, helper + anchor, 1)
p.write_text(src)
import ast
ast.parse(src)
print("  helper inserted, syntax OK")
PY

echo
echo "########## 3) Verify pipeline.py odd_even_threshold ##########"
grep -n "odd_even_threshold=" astrotransit/quality/pipeline.py

echo
echo "########## 4) Syntax check ##########"
python -c "import ast; ast.parse(open('$V').read()); ast.parse(open('$R').read()); ast.parse(open('astrotransit/quality/pipeline.py').read()); print('all OK')"

echo
echo "########## 5) Ruff ##########"
ruff check "$V" "$R" astrotransit/quality/pipeline.py 2>&1 | tail -5

echo
echo "########## 6) Tests ##########"
python -m pytest tests/test_quality_vetting.py tests/test_quality_pipeline.py tests/test_quality_scorer.py -q 2>&1 | tail -8

echo
echo "########## 7) Final threshold verification ##########"
grep -nE "threshold = 1\.5|threshold = -0\.55|threshold = 0\.25|ls_peak > 0\.15|ls_peak > 0\.10" "$V"

echo
echo "== DONE =="
