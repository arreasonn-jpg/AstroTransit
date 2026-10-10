#!/usr/bin/env bash
# FAZ 2b.3c: adopt "reject if quality_class in {C, D}" as the pipeline rule.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b3c_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 2b.3c: class-gate =="
echo "log: $LOG"

echo
echo "########## 1) Inspect scorer.py signature ##########"
grep -n "def score\|class QualityScore\|is_false_positive\|candidate_class" astrotransit/quality/scorer.py | head -30

echo
echo "########## 2) Show where is_false_positive is set ##########"
sed -n '230,320p' astrotransit/quality/scorer.py

echo
echo "########## 3) Patch scorer.py: add class-based rejection ##########"
cp astrotransit/quality/scorer.py /tmp/scorer.py.faz2b3c.bak

python - <<'PY'
from pathlib import Path
import re

p = Path("astrotransit/quality/scorer.py")
src = p.read_text()

# Find QualityScore dataclass and add the new field
if "rejected_by_class" in src:
    print("  already patched")
    raise SystemExit(0)

# Insert new field near is_false_positive
m = re.search(r"(\n    is_false_positive:\s*bool\s*=\s*False\n)", src)
if not m:
    print("FATAL: is_false_positive field not found in QualityScore")
    raise SystemExit(1)

src = src.replace(
    m.group(1),
    "\n    is_false_positive: bool = False\n"
    "    #: FAZ 2b.3c: True when the candidate class is C or D. These are\n"
    "    #: 'suspicious' and 'low-quality' candidates; the automated pipeline\n"
    "    #: treats them as false positives so that only Class A/B survive.\n"
    "    rejected_by_class: bool = False\n",
    1,
)

# Find the place where QualityScore is constructed and add the computation.
# Typically the pattern looks like: QualityScore(..., is_false_positive=..., ...)
# We'll add `rejected_by_class=...` in the same constructor call.
m2 = re.search(r"(return QualityScore\(\s*\n(?:.*\n)*?)(\s*\))", src)
if not m2:
    print("WARN: QualityScore constructor not found by regex; manual patch needed")
else:
    print("  QualityScore() found at:", m2.start())
PY

echo
echo "########## 4) Show the score() method body around class assignment ##########"
grep -n "candidate_class\s*=\|is_false_positive\s*=\|class_descriptions\|CLASS_DESCRIPTIONS" astrotransit/quality/scorer.py | head -20

echo
echo "== DONE (manual inspection next) =="
