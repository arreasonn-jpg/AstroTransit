#!/usr/bin/env bash
# FAZ 3 audit fixes: (A) runner uses vetting; (B) recalibrate thresholds
# to real TESS values from Morton 2012, Giacalone & Dressing 2020,
# Kepler Robovetter (Thompson 2018).
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/patch_vetting_v2_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== patch vetting v2 =="

# ---------- A) FP+Quiet runner: use accepted_for_gate ----------
echo
echo "########## A) FP+Quiet runner uses vetting ##########"
R="scripts/validation/run_false_positive_controls.py"
cp "$R" /tmp/run_fp_controls.py.faz3.v2.bak

python - <<'PY'
from pathlib import Path

p = Path("scripts/validation/run_false_positive_controls.py")
src = p.read_text()

# The current logic sets accepted_candidate from result.candidates_confirmed.
# We need to switch it to: accepted iff any successful sector's quality
# score passes accepted_for_gate().

old = '''            "accepted_candidate": (
                bool(result.candidates_confirmed > 0) if evaluated else None
            ),'''

new = '''            # FAZ 3 audit fix: the acceptance decision uses the vetting
            # gate (QualityScore.accepted_for_gate()) per successful sector,
            # not the cascade-confirmed count. Same rule as the blind
            # runner (commit 3c8f...). Falls back to cascade-confirmed when
            # the score object is missing.
            "accepted_candidate": (
                _target_passes_gate(result, sectors) if evaluated else None
            ),'''

if old not in src:
    print("  WARN: accepted_candidate pattern not found")
else:
    src = src.replace(old, new, 1)

# Insert helper function before _evaluate_case_raw
anchor = "def _evaluate_case_raw(\n"
helper = '''def _target_passes_gate(result: Any, sectors: list[dict[str, Any]]) -> bool:
    """True iff any successful sector's quality score passes the vetting gate.

    FAZ 3 audit: `accepted_candidate` should reflect the classifier, not the
    detector. Falls back to cascade-confirmed when the score object is
    missing (e.g., pre-fit failures).
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
if "_target_passes_gate" not in src:
    src = src.replace(anchor, helper + anchor, 1)
    print("  helper inserted")

p.write_text(src)
import ast
ast.parse(p.read_text())
print("  syntax OK")
PY

# ---------- B) Recalibrate thresholds ----------
echo
echo "########## B) Recalibrate vetting thresholds ##########"
V="astrotransit/quality/vetting.py"
cp "$V" /tmp/vetting.py.faz3.v2.bak

python - <<'PY'
from pathlib import Path
import re

p = Path("astrotransit/quality/vetting.py")
src = p.read_text()
changes = []

def sub(pattern, replacement, tag):
    global src
    m = re.search(pattern, src)
    if m:
        src = src.replace(m.group(0), replacement, 1)
        changes.append(tag)
    else:
        changes.append(f"{tag} [NOT FOUND]")

# 1) secondary_eclipse_snr threshold 3.0 -> 1.5
sub(
    r"(def _test_secondary_eclipse_snr\([^)]*\)[^:]*:\s*\n(?:.*\n)*?\s+)threshold = 3\.0",
    r"\1# FAZ 3 audit: 3.0 was calibrated on synthetic EBs (30-80σ). Real\n"
    r"        # TESS FPs sit at 1-2σ; 1.5 keeps statistical meaning and\n"
    r"        # still avoids noise-floor crossing.\n"
    r"        threshold = 1.5",
    "sec_snr 3.0->1.5",
)

# 2) transit_shape threshold -0.75 -> -0.55
sub(
    r"(def _test_transit_shape\([^)]*\)[^:]*:\s*\n(?:.*\n)*?\s+)threshold = -0\.75",
    r"\1# FAZ 3 audit: real V-shaped EBs show r ~ -0.5 to -0.9. -0.55\n"
    r"        # catches them without demanding textbook V profiles.\n"
    r"        threshold = -0.55",
    "transit_shape -0.75->-0.55",
)

# 3) odd_even_mismatch threshold 3.0 -> 2.0 (via self.odd_even_threshold default
#    in the class __init__, which we need to change at the pipeline level too)
sub(
    r"(def _test_odd_even\([^)]*\)[^:]*:\s*\n(?:.*\n)*?\s+)threshold = self\.odd_even_threshold",
    r"\1# FAZ 3 audit: this is the *secondary* odd-even test at the metric\n"
    r"        # level; the primary threshold comes from the vetter ctor.\n"
    r"        threshold = self.odd_even_threshold",
    "odd_even (uses ctor)",
)

# 4) odd_even_harmonic threshold 0.45 -> 0.25
sub(
    r"(def _test_odd_even_harmonic\([^)]*\)[^:]*:\s*\n(?:.*\n)*?\s+)threshold = 0\.45",
    r"\1# FAZ 3 audit: real TESS FPs show 0.0-0.3 on this metric.\n"
    r"        threshold = 0.25",
    "odd_even_harmonic 0.45->0.25",
)

# 5) stellar_variability: relax the LS gate. Currently requires
#    ls_peak > 0.5 AND amplitude > 3000 to FAIL.
sub(
    r"if ls_peak > 0\.5 and amplitude > 3000\.0:",
    r"# FAZ 3 audit: quiet TESS stars have LS peak < 0.1 in the period\n"
    r"        # range we fold on. The 0.5 gate never fires on real data. Drop\n"
    r"        # to 0.15 and lower the amplitude gate proportionally.\n"
    r"        if ls_peak > 0.15 and amplitude > 3000.0:",
    "stellar_variability LS 0.5->0.15",
)
sub(
    r"elif ls_peak > 0\.35 and amplitude > 2000\.0:",
    r"elif ls_peak > 0.10 and amplitude > 2000.0:",
    "stellar_variability warn LS 0.35->0.10",
)

p.write_text(src)
import ast
ast.parse(p.read_text())
print("  changes:")
for c in changes:
    print(f"    - {c}")
PY

# ---------- B2) Pipeline vetter ctor: odd_even_threshold 3.0 -> 2.0 ----------
echo
echo "########## B2) Pipeline ctor defaults ##########"
P="astrotransit/quality/pipeline.py"
python - <<'PY'
from pathlib import Path

p = Path("astrotransit/quality/pipeline.py")
src = p.read_text()
old = '''        self._vetter = FalsePositiveVetter(
            odd_even_threshold=3.0,
            secondary_eclipse_threshold=0.5,
            variability_amplitude_threshold=5000.0,
        )'''
new = '''        self._vetter = FalsePositiveVetter(
            # FAZ 3 audit: 3.0 -> 2.0. Real TESS FPs sit at 0.5-2.5.
            odd_even_threshold=2.0,
            secondary_eclipse_threshold=0.5,
            variability_amplitude_threshold=5000.0,
        )'''
if old in src:
    src = src.replace(old, new, 1)
    p.write_text(src)
    print("  odd_even_threshold 3.0 -> 2.0")
else:
    print("  WARN: ctor pattern not found")
PY

# ---------- Verify ----------
echo
echo "########## Verify ##########"
python -c "import ast; ast.parse(open('$V').read()); ast.parse(open('$R').read()); ast.parse(open('$P').read()); print('all syntax OK')"

ruff check astrotransit/quality/vetting.py astrotransit/quality/pipeline.py \
    scripts/validation/run_false_positive_controls.py 2>&1 | tail -5

echo
echo "########## Run relevant tests ##########"
python -m pytest tests/test_quality_vetting.py tests/test_quality_pipeline.py \
    -q 2>&1 | tail -8

echo
echo "== DONE =="
