#!/usr/bin/env bash
# Fix the two lint issues that blocked the FAZ 1 commit.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase1_fix_lint_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== phase1_fix_lint =="
echo "log: $LOG"

LT="astrotransit/validation/leakage_taxonomy.py"
cp "$LT" /tmp/leakage_taxonomy.py.prelint.bak

echo
echo "########## 1) Show current state of the two problem areas ##########"
grep -n "fpp" "$LT" || true
echo "---"
grep -n "counter" "$LT" || true

echo
echo "########## 2) Apply fixes ##########"
python - <<'PY'
from pathlib import Path
import re

p = Path("astrotransit/validation/leakage_taxonomy.py")
src = p.read_text()
orig = src

# Fix 1: remove unused fpp assignment
# The pattern is:  fpp = _num("fpp", "false_positive_probability")
# with optional leading whitespace
before = src
src = re.sub(
    r'[ \t]*fpp = _num\("fpp", "false_positive_probability"\)\n',
    '',
    src,
)
if src != before:
    print("  removed unused 'fpp = _num(...)' line")
else:
    print("  WARN: fpp assignment line not found")

# Fix 2: type-annotate Counter
before = src
src = src.replace(
    "counter = Counter()",
    "counter: Counter[str] = Counter()",
)
# Also handle the by_family one if it's unannotated
src = src.replace(
    "by_family: Counter = Counter()",
    "by_family: Counter[str] = Counter()",
)
if src != before:
    print("  annotated Counter types")
else:
    print("  WARN: no Counter() calls found to annotate")

# Ensure 'from typing import Any, Mapping, Optional' includes nothing extra
# (leave as-is if already fine)

p.write_text(src)
print(f"  wrote {p}")
PY

echo
echo "########## 3) Verify with ruff + mypy on that single file ##########"
echo "--- ruff check ---"
ruff check "$LT" 2>&1 | tail -20 || true
echo "--- ruff format check ---"
ruff format --check "$LT" 2>&1 | tail -10 || true
echo "--- mypy ---"
mypy "$LT" 2>&1 | tail -20 || true

echo
echo "########## 4) Run the tests again ##########"
python -m pytest tests/test_leakage_taxonomy.py -q 2>&1 | tail -6

echo
echo "########## 5) Show git status ##########"
git status --short

echo
echo "== phase1_fix_lint DONE =="
