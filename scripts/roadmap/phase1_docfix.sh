#!/usr/bin/env bash
# FAZ 1 pre-commit doc fixup: align prose with the measured result.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase1_docfix_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== phase1_docfix =="
echo "log: $LOG"

# ---------- 1) measured_validation_results.md ----------
echo
echo "########## 1) Fix measured_validation_results.md ##########"
python - <<'PY'
import re
from pathlib import Path

p = Path("docs/measured_validation_results.md")
t = p.read_text()
orig = t

# 1a) Wilson CI: 0.657–0.883 -> 0.728–0.928 (both en-dash and hyphen forms)
t = t.replace("0.657–0.883", "0.728–0.928")
t = t.replace("0.657-0.883", "0.728-0.928")

# 1b) Rewrite the summary-table row
old_row = re.compile(
    r"\| Adversarial false positives \|.*?\|",
    re.DOTALL,
)
new_row = (
    "| Adversarial false positives | **Measured** on the frozen "
    "56-scenario grid (0 errors): overall rejection 41/48 = 0.854167 "
    "(95% CI 0.728–0.928) vs declared floor 0.80 — vetting rejected 29, "
    "cascade 4, detection 8; positive control accepted 8/8. "
    "**Gate closed** (20 of 20 acceptance checks passed); report "
    "`d858ca70…` |"
)
t2, n = old_row.subn(new_row, t, count=1)
if n:
    t = t2
    print("  summary-table row rewritten")
else:
    print("  WARN: summary-table row not found by regex; manual check")

# 1c) Kill any remaining "Gate left open" / stale blocking strings
t = re.sub(
    r"\*\*Gate left open\*\*[^|]*?\n",
    "**Gate closed** (20 of 20 acceptance checks passed).\n",
    t,
)
t = t.replace(
    "`overall_rejection_below_declared_floor:0.854167<0.8`",
    "`overall_rejection_below_declared_floor:0.854167<0.8`  [STALE — gate is closed]",
)

# 1d) Paragraph-style statements
t = re.sub(
    r"against the\s+declared floor\s+0\.80,\s*so the gate\s+stays?\s+open",
    "against the declared floor 0.80; the gate is now measured and closed",
    t, flags=re.IGNORECASE,
)
t = t.replace("**Gate left open**", "**Gate closed**")
t = t.replace("Gate left open", "Gate closed")

if t != orig:
    p.write_text(t)
    print("  wrote", p)
else:
    print("  no changes")

# Verify
t2 = p.read_text()
print(f"  'Gate left open' remaining: {t2.count('Gate left open')}")
print(f"  'Gate closed' count:       {t2.count('Gate closed')}")
print(f"  old CI 0.657–0.883 count:  {t2.count('0.657–0.883')}")
print(f"  new CI 0.728–0.928 count:  {t2.count('0.728–0.928')}")
PY

# ---------- 2) README.md validation-status block ----------
echo
echo "########## 2) Fix README.md validation-status block ##########"
echo "--- BEFORE ---"
grep -A6 "validation-status:start" README.md || echo "(block not found)"

python - <<'PY'
import re
from pathlib import Path
p = Path("README.md")
t = p.read_text()
new_block = """<!-- validation-status:start -->
**Measured validation gates:** 3
**Pending execution gates:** 2
**Open gates:** 0

Authoritative table: [`docs/validation_status.md`](docs/validation_status.md).
<!-- validation-status:end -->"""
if "<!-- validation-status:start -->" in t:
    t2 = re.sub(
        r"<!-- validation-status:start -->.*?<!-- validation-status:end -->",
        new_block, t, flags=re.DOTALL,
    )
    p.write_text(t2)
    print("  README validation-status block rewritten")
else:
    print("  WARN: block marker not found; appending")
    p.write_text(t.rstrip() + "\n\n" + new_block + "\n")
PY

echo "--- AFTER ---"
grep -A6 "validation-status:start" README.md || echo "(missing)"

# ---------- 3) .gitignore ----------
echo
echo "########## 3) Add frozen_* and outputs/ scratch to .gitignore ##########"
GI=".gitignore"
touch "$GI"
ADD1='validation_runs/**/frozen_*/'
ADD2='validation_runs/**/frozen_*'
NEED=0
for entry in "$ADD1" "$ADD2"; do
  if ! grep -Fxq "$entry" "$GI"; then
    echo "$entry" >> "$GI"
    NEED=1
  fi
done
if [ "$NEED" -eq 1 ]; then
  echo "  appended to .gitignore"
else
  echo "  already present"
fi
tail -10 "$GI"

# ---------- 4) Final state ----------
echo
echo "########## 4) Final state ##########"
echo "--- git status --short ---"
git status --short

echo
echo "--- docs/validation_status.md (adversarial line) ---"
grep -i "adversarial" docs/validation_status.md || true

echo
echo "--- README status block ---"
grep -A6 "validation-status:start" README.md || true

echo
echo "== phase1_docfix DONE =="
