#!/usr/bin/env bash
# FAZ 2b.4-revert: class gate did not transfer. Revert to detection-level
# baseline + vetting-only. Keep the field for future use.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b4_revert_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== revert class gate =="

cp astrotransit/quality/scorer.py /tmp/scorer.py.faz2b4revert.bak

python - <<'PY'
from pathlib import Path

p = Path("astrotransit/quality/scorer.py")
src = p.read_text()

# Change accepted_for_gate to a strict vetting-only rule. Keep the field
# for future use but do not include it in the gate predicate.
old = (
    '        return not (self.is_false_positive or self.rejected_by_class)\n'
)
new = (
    '        # FAZ 2b.4: the class-only gate (C/D) did not transfer to the\n'
    '        # blind partition (recall 0.264 vs 0.532 on development). The\n'
    '        # finding is that the scorer does not separate planets from FPs\n'
    '        # -- within every class the score distributions overlap. So the\n'
    '        # gate is now vetting-only; the class field is kept for future\n'
    '        # feature engineering but is not part of the decision.\n'
    '        return not self.is_false_positive\n'
)
if old in src:
    src = src.replace(old, new, 1)
    p.write_text(src)
    print("  reverted accepted_for_gate to vetting-only")
else:
    print("  WARN: pattern not found")
PY

# Verify
python -c "import ast; ast.parse(open('astrotransit/quality/scorer.py').read()); print('syntax OK')"

# Show new method
grep -A3 "def accepted_for_gate" astrotransit/quality/scorer.py | head -8

# Tests
python -m pytest tests/test_quality_scorer.py tests/test_quality_vetting.py -q 2>&1 | tail -3

echo
echo "== DONE =="
