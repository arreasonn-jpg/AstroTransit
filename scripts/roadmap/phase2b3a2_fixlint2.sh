#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase2b3a2_fixlint2_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== fixlint2 =="
echo "log: $LOG"

python - <<'PY'
from pathlib import Path
import re

p = Path("tests/test_quality_vetting.py")
src = p.read_text()

# 1) Insert module-level import after the vetting import block.
#    Find the closing paren of `from astrotransit.quality.vetting import (...)`.
m = re.search(
    r"(from astrotransit\.quality\.vetting import \(.*?\)\n)",
    src, re.DOTALL,
)
if not m:
    print("FATAL: vetting import block not found")
    raise SystemExit(1)

vetting_import = m.group(1)
module_import = (
    "\nfrom astrotransit.quality.metrics import (\n"
    "    PhotometricMetrics,\n"
    "    QualityMetrics,\n"
    "    StellarMetrics,\n"
    "    TransitMetrics,\n"
    ")\n"
)
if "from astrotransit.quality.metrics import" not in src:
    src = src.replace(vetting_import, vetting_import + module_import, 1)
    print("  added module-level import of QualityMetrics et al.")
else:
    print("  module-level import already present")

# 2) Remove the inline (function-local) import block.
inline_pattern = re.compile(
    r"\n    from astrotransit\.quality\.metrics import \(\n"
    r"(?:.*?\n)*?"
    r"    \)\n",
    re.DOTALL,
)
src2, n = inline_pattern.subn("\n", src, count=1)
if n:
    src = src2
    print("  removed inline import block")
else:
    print("  WARN: inline import block not found (may already be gone)")

p.write_text(src)
print(f"  wrote {p}")
PY

echo
echo "########## Verify ##########"
ruff check tests/test_quality_vetting.py 2>&1 | tail -5
python -m pytest tests/test_quality_vetting.py -q 2>&1 | tail -3

echo
echo "########## Stage + commit ##########"
git add tests/test_quality_vetting.py
GITID=(-c user.email="validation@astrotransit.local" -c user.name="AstroTransit Validation")
git "${GITID[@]}" commit -F /tmp/faz2b3a_commit_msg.txt
COMMIT_EXIT=$?
echo "  commit exit=$COMMIT_EXIT"

git --no-pager log -2 --format="%h %s"
echo
echo "working tree:"
git status --short
echo
echo "== fixlint2 DONE =="
