#!/usr/bin/env bash
# FAZ 2b.3c: add rejected_by_class field + populate it.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b3c_apply_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 2b.3c apply =="
echo "log: $LOG"

cp astrotransit/quality/scorer.py /tmp/scorer.py.faz2b3c.bak
echo "backup: /tmp/scorer.py.faz2b3c.bak"

echo
echo "########## 1) Show current QualityScore dataclass ##########"
sed -n '95,170p' astrotransit/quality/scorer.py

echo
echo "########## 2) Show constructor block 385-420 ##########"
sed -n '385,420p' astrotransit/quality/scorer.py

echo
echo "########## 3) Apply patch ##########"
python - <<'PY'
from pathlib import Path
import re

p = Path("astrotransit/quality/scorer.py")
src = p.read_text()
orig = src

# ---- A) Field: add rejected_by_class after is_false_positive (dataclass) ----
old_field = "    is_false_positive: bool = False\n"
new_field = (
    "    is_false_positive: bool = False\n"
    "    #: FAZ 2b.3c: True when the candidate class is C or D. These are\n"
    "    #: 'suspicious' and 'low-quality' candidates; the automated pipeline\n"
    "    #: treats them as false positives so that only Class A/B survive.\n"
    "    rejected_by_class: bool = False\n"
)
if "rejected_by_class" not in src:
    src = src.replace(old_field, new_field, 1)
    print("  + dataclass field rejected_by_class")
else:
    print("  (dataclass field already present)")

# ---- B) to_dict: include the new field ----
old_dict_line = '            "is_false_positive": self.is_false_positive,\n'
new_dict_line = (
    '            "is_false_positive": self.is_false_positive,\n'
    '            "rejected_by_class": self.rejected_by_class,\n'
)
if '"rejected_by_class": self.rejected_by_class,' not in src:
    src = src.replace(old_dict_line, new_dict_line, 1)
    print("  + to_dict entry for rejected_by_class")

# ---- C) Constructor: add keyword arg after is_false_positive=... ----
# Match the specific line `is_false_positive=vetting.is_false_positive,`
old_ctor = "            is_false_positive=vetting.is_false_positive,\n"
new_ctor = (
    "            is_false_positive=vetting.is_false_positive,\n"
    "            # FAZ 2b.3c: reject Class C and D automatically.\n"
    "            rejected_by_class=(candidate_class in (CandidateClass.C, CandidateClass.D)),\n"
)
if "rejected_by_class=(candidate_class in" not in src:
    if old_ctor in src:
        src = src.replace(old_ctor, new_ctor, 1)
        print("  + constructor keyword arg rejected_by_class")
    else:
        print("  WARN: constructor line not found verbatim; trying loose match")
        m = re.search(r"(\n(\s+)is_false_positive=vetting\.is_false_positive,)", src)
        if m:
            indent = m.group(2)
            src = src.replace(
                m.group(1),
                f"\n{indent}is_false_positive=vetting.is_false_positive,\n"
                f"{indent}# FAZ 2b.3c: reject Class C and D automatically.\n"
                f"{indent}rejected_by_class=(candidate_class in (CandidateClass.C, CandidateClass.D)),",
                1,
            )
            print("  + constructor keyword arg (loose match)")
        else:
            print("  FATAL: could not locate constructor line")
            raise SystemExit(1)
else:
    print("  (constructor already patched)")

# ---- D) Add convenience method accepted_for_gate() to QualityScore ----
if "def accepted_for_gate" not in src:
    # Insert right before `def to_dict` inside QualityScore
    m = re.search(r"(\n    def to_dict\(self\) -> dict:\n)", src)
    if m:
        helper = (
            "\n    def accepted_for_gate(self) -> bool:\n"
            "        \"\"\"FAZ 2b.3c: gate-level acceptance decision.\n\n"
            "        Returns True iff this candidate survives both the vetting\n"
            "        false-positive verdict and the class-based rejection\n"
            "        (Class C and D are treated as false positives).\n"
            "        \"\"\"\n"
            "        return not (self.is_false_positive or self.rejected_by_class)\n"
        )
        src = src[:m.start(1)] + helper + src[m.start(1):]
        print("  + method accepted_for_gate()")

if src != orig:
    p.write_text(src)
    print("  wrote scorer.py")
else:
    print("  no changes")
PY

echo
echo "########## 4) Syntax check ##########"
python -c "import ast; ast.parse(open('astrotransit/quality/scorer.py').read()); print('  syntax OK')"

echo
echo "########## 5) Ruff ##########"
ruff check astrotransit/quality/scorer.py 2>&1 | tail -3

echo
echo "########## 6) Unit tests (scorer + related) ##########"
python -m pytest tests/test_quality_scorer.py tests/test_quality_vetting.py tests/test_quality_metrics.py -q 2>&1 | tail -5

echo
echo "== DONE =="
