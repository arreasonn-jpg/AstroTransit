#!/usr/bin/env bash
# Add _time_limit protection to run_false_positive_controls.py
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase3_addtimeout_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== add per-target timeout =="

R="scripts/validation/run_false_positive_controls.py"
cp "$R" /tmp/run_fp_controls.py.faz3.bak

python - <<'PY'
from pathlib import Path
import re

p = Path("scripts/validation/run_false_positive_controls.py")
src = p.read_text()

if "_time_limit" in src:
    print("  already patched")
    raise SystemExit(0)

# 1) Insert helper after imports
m = re.search(r"^(import sys\n)", src, re.MULTILINE)
if not m:
    m = re.search(r"^(from __future__ import annotations\n)", src, re.MULTILINE)
if not m:
    print("FATAL: no import anchor"); raise SystemExit(1)

helper = '''

import signal
from contextlib import contextmanager


PER_TARGET_TIMEOUT_SECONDS = 480  # 8 min, matches blind runner


@contextmanager
def _time_limit(seconds: int):
    """Per-target wall-clock bound (FAZ 3).

    MAST catalog queries hang for many minutes on some TIC IDs. Bound
    every target's pipeline call so one slow target cannot starve the
    whole shard.
    """
    def _handler(signum, frame):
        raise TimeoutError(f"per-target timeout after {seconds}s")

    old = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(int(seconds))
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)

'''

src = src[:m.end(1)] + helper + src[m.end(1):]
p.write_text(src)
print("  inserted _time_limit helper")
PY

echo
echo "########## Find the target-evaluation call site ##########"
grep -n "orchestrator.run_single\|run_single(" "$R" | head -10

echo
echo "########## Show context around run_single ##########"
grep -B3 -A3 "run_single" "$R" | head -40

echo
echo "== DONE (manual wrap next) =="
