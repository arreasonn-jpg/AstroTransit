#!/usr/bin/env bash
# FAZ 2b.3c-runner: gate measurement uses accepted_for_gate() instead of
# cascade-confirmed-only. This is the FAZ 2b.3c decision rule in action.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b3c_runner_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 2b.3c runner =="
echo "log: $LOG"

cp scripts/validation/run_blind_holdout.py /tmp/run_blind_holdout.py.faz2b3c.bak
echo "backup: /tmp/run_blind_holdout.py.faz2b3c.bak"

echo
echo "########## 1) Current accepted_candidate assignment ##########"
grep -n "accepted_candidate" scripts/validation/run_blind_holdout.py

echo
echo "########## 2) Patch _evaluate_case ##########"
python - <<'PY'
from pathlib import Path
import re

p = Path("scripts/validation/run_blind_holdout.py")
src = p.read_text()

# Current line:
#     row["accepted_candidate"] = bool(confirmed)
# New: use accepted_for_gate() from each sector's score, with fallback
# to confirmed when score is missing (so behavior degrades gracefully).
old = '        row["accepted_candidate"] = bool(confirmed)'
new = '''        # FAZ 2b.3c: a candidate is accepted only if any sector's score
        # survives both vetting (is_false_positive) and the class gate
        # (rejected_by_class). Fall back to cascade-confirmed when the
        # score object is missing (e.g., pre-fit failures).
        def _sector_accepted(sector_obj):
            quality = getattr(sector_obj, "quality", None)
            score = getattr(quality, "score", None) if quality else None
            if score is not None and hasattr(score, "accepted_for_gate"):
                return bool(score.accepted_for_gate())
            return bool(getattr(sector_obj, "candidate_confirmed", False))

        row["accepted_candidate"] = any(_sector_accepted(s) for s in sectors)'''

if old in src:
    src = src.replace(old, new, 1)
    p.write_text(src)
    print("  patched accepted_candidate computation")
else:
    print("FATAL: could not find accepted_candidate assignment")
    raise SystemExit(1)
PY

echo
echo "########## 3) Also record score-level class rejection in row ##########"
python - <<'PY'
from pathlib import Path

p = Path("scripts/validation/run_blind_holdout.py")
src = p.read_text()

# In the per_sector block, add rejected_by_class / accepted_for_gate
if "rejected_by_class" not in src:
    # Find the per-sector dict where we already have quality_class, quality_score
    old = '                "quality_class": _verdict_value(getattr(score_o, "candidate_class", "")) if score_o else "",'
    new = (
        '                "quality_class": _verdict_value(getattr(score_o, "candidate_class", "")) if score_o else "",\n'
        '                "rejected_by_class": bool(getattr(score_o, "rejected_by_class", False)) if score_o else False,\n'
        '                "accepted_for_gate": bool(getattr(score_o, "accepted_for_gate", lambda: False)()) if score_o else False,'
    )
    if old in src:
        src = src.replace(old, new, 1)
        p.write_text(src)
        print("  added rejected_by_class + accepted_for_gate to per_sector")
    else:
        print("  WARN: quality_class per-sector line not found")
else:
    print("  (already present)")
PY

echo
echo "########## 4) Syntax + ruff ##########"
python -c "import ast; ast.parse(open('scripts/validation/run_blind_holdout.py').read()); print('  syntax OK')"
ruff check scripts/validation/run_blind_holdout.py 2>&1 | tail -3

echo
echo "########## 5) Unit tests ##########"
python -m pytest tests/test_blind_holdout.py tests/test_validation_blind_holdout_full.py -q 2>&1 | tail -3

echo
echo "== DONE =="
