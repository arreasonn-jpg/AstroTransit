#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase3_wrap_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== wrap run_single in _time_limit =="

R="scripts/validation/run_false_positive_controls.py"
python - <<'PY'
from pathlib import Path

p = Path("scripts/validation/run_false_positive_controls.py")
src = p.read_text()

old = '        result = orchestrator.run_single(case.target_id, sectors=requested)\n'
new = (
    '        with _time_limit(PER_TARGET_TIMEOUT_SECONDS):\n'
    '            result = orchestrator.run_single(case.target_id, sectors=requested)\n'
)
if old in src and 'with _time_limit(PER_TARGET_TIMEOUT_SECONDS):' not in src:
    src = src.replace(old, new, 1)
    p.write_text(src)
    print("  wrapped run_single")
else:
    print("  WARN: pattern changed or already wrapped")

import ast
ast.parse(p.read_text())
print("  syntax OK")
PY

echo
echo "########## Verify ##########"
grep -n "_time_limit\|PER_TARGET_TIMEOUT" "$R" | head -10

echo
echo "########## Ruff ##########"
ruff check "$R" 2>&1 | tail -3

echo
echo "########## Offline test (does import work?) ##########"
python -c "
import sys
sys.path.insert(0, '.')
from importlib.util import spec_from_file_location, module_from_spec
spec = spec_from_file_location('run_fp', 'scripts/validation/run_false_positive_controls.py')
m = module_from_spec(spec)
spec.loader.exec_module(m)
print('  module loaded OK')
print(f'  PER_TARGET_TIMEOUT_SECONDS = {m.PER_TARGET_TIMEOUT_SECONDS}')
"

echo
echo "== DONE =="
