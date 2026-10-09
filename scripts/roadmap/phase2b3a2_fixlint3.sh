#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase2b3a2_fixlint3_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== fixlint3 =="
echo "log: $LOG"

echo
echo "########## 1) Current state of imports ##########"
sed -n '1,15p' tests/test_quality_vetting.py

echo
echo "########## 2) Add module-level metrics import (idempotent) ##########"
python - <<'PY'
from pathlib import Path
import re

p = Path("tests/test_quality_vetting.py")
src = p.read_text()

needle = "from astrotransit.quality.metrics import"

# Check if a module-level import already exists (must start at col 0)
has_module_level = bool(re.search(r"^from astrotransit\.quality\.metrics import",
                                   src, re.MULTILINE))

if has_module_level:
    print("  module-level import already present, no change")
else:
    # Find the closing of the vetting import block
    m = re.search(
        r"(from astrotransit\.quality\.vetting import \(.*?\)\n)",
        src, re.DOTALL,
    )
    if not m:
        print("FATAL: vetting import block not found")
        raise SystemExit(1)
    block = m.group(1)
    insertion = (
        "\n"
        "from astrotransit.quality.metrics import (\n"
        "    PhotometricMetrics,\n"
        "    QualityMetrics,\n"
        "    StellarMetrics,\n"
        "    TransitMetrics,\n"
        ")\n"
    )
    src = src.replace(block, block + insertion, 1)
    p.write_text(src)
    print("  added module-level metrics import")

print()
print("--- first 20 lines after ---")
for i, line in enumerate(p.read_text().splitlines()[:20], 1):
    print(f"{i:3d} | {line}")
PY

echo
echo "########## 3) Ruff check ##########"
ruff check tests/test_quality_vetting.py 2>&1 | tail -5

echo
echo "########## 4) Full test suite on touched test files ##########"
python -m pytest tests/test_quality_vetting.py tests/test_metrics_dip_amplitude.py -q 2>&1 | tail -5

echo
echo "########## 5) Sanity — other suites ##########"
python -m pytest tests/test_quality_metrics.py tests/test_adversarial_fp.py -q 2>&1 | tail -3

echo
echo "########## 6) Stage + commit ##########"
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
echo "== fixlint3 DONE =="
