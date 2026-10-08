#!/usr/bin/env bash
# AstroTransit 10/10 Roadmap — PHASE 0: Foundation lock
# Idempotent. Safe to re-run. Writes log to ~/phase0_<timestamp>.log

set -uo pipefail

REPO="$HOME/AstroTransit"
cd "$REPO" || { echo "FATAL: $REPO not found"; exit 1; }

# shellcheck disable=SC1091
source .venv/bin/activate || { echo "FATAL: .venv activate failed"; exit 1; }

LOG="$HOME/phase0_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

echo "=========================================="
echo " AstroTransit 10/10 — PHASE 0"
echo " Log file: $LOG"
echo "=========================================="

echo
echo "########## 1) DISCOVERY ##########"
echo "--- git status --short ---"
git status --short || true
echo
echo "--- git branch --show-current ---"
git branch --show-current || true
echo
echo "--- top-level dirs ---"
find . -maxdepth 1 -type d -not -name '.git' -not -name '.venv' -not -name '.' | sort
echo
echo "--- pyproject.toml coverage-related lines (with line numbers) ---"
python - <<'PY_DISCOVERY'
from pathlib import Path
p = Path("pyproject.toml")
if not p.exists():
    print("pyproject.toml MISSING")
else:
    for i, line in enumerate(p.read_text().splitlines(), 1):
        low = line.lower()
        if any(k in low for k in ("coverage", "fail_under", "branch", "pytest")):
            print(f"{i:4d} | {line}")
PY_DISCOVERY
echo
echo "--- README.md size ---"
[ -f README.md ] && wc -l README.md || echo "README.md MISSING"
echo
echo "--- README.md last 40 lines ---"
[ -f README.md ] && tail -40 README.md || true
echo
echo "--- docs/ ---"
ls -la docs/ 2>/dev/null || echo "(no docs/)"
echo
echo "--- validation_runs/ ---"
ls -la validation_runs/ 2>/dev/null || echo "(no validation_runs/)"
echo
echo "--- .github/workflows/ ---"
ls -la .github/workflows/ 2>/dev/null || echo "(no .github/workflows/)"
echo
echo "--- key source files (adversarial fp / blind holdout / eb discriminator) ---"
find astrotransit -maxdepth 4 -type f \( -name '*adversarial*' -o -name '*blind*' -o -name '*eb_coorbital*' -o -name '*fpp*' \) 2>/dev/null | sort || true

echo
echo "########## 2) pyproject.toml → fail_under = 90 + branch coverage ##########"

cp -n pyproject.toml pyproject.toml.phase0.bak 2>/dev/null && echo "Backup: pyproject.toml.phase0.bak" || echo "Backup already exists"

python - <<'PY_FIX_TOML'
import re
from pathlib import Path

p = Path("pyproject.toml")
text = p.read_text()
orig = text

# 1) fail_under N → 90
text, n_fail = re.subn(r'(fail_under\s*=\s*)\d+', r'\g<1>90', text)

# 2) [tool.coverage.run] branch = true
if "[tool.coverage.run]" not in text:
    text += "\n[tool.coverage.run]\nbranch = true\n"
    branch_note = "added [tool.coverage.run] with branch = true"
else:
    head, _, rest = text.partition("[tool.coverage.run]")
    m = re.search(r'\n\[', rest)
    if m:
        section = rest[:m.start()]
        tail = rest[m.start():]
    else:
        section = rest
        tail = ""
    if not re.search(r'^\s*branch\s*=', section, re.M):
        section = "branch = true\n" + section.lstrip("\n")
        branch_note = "added branch = true to existing [tool.coverage.run]"
    else:
        branch_note = "branch key already present"
    text = head + "[tool.coverage.run]\n" + section.rstrip() + "\n" + tail

p.write_text(text)
print(f"fail_under replacements: {n_fail}")
print(f"branch coverage: {branch_note}")
print("changed:", text != orig)
print("--- coverage-related lines AFTER ---")
for i, line in enumerate(text.splitlines(), 1):
    low = line.lower()
    if any(k in low for k in ("coverage", "fail_under", "branch")):
        print(f"{i:4d} | {line}")
PY_FIX_TOML

echo
echo "########## 3) docs/validation_status.md ##########"

mkdir -p docs

python - <<'PY_STATUS'
import hashlib, subprocess, datetime
from pathlib import Path

def sha12(path):
    p = Path(path)
    if not p.exists():
        return "N/A"
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]

try:
    commit = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"],
        stderr=subprocess.DEVNULL
    ).decode().strip()
except Exception:
    commit = "unknown"

now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

content = f"""# AstroTransit — Validation Status

> **Single source of truth** for scientific validation gates.
> Auto-managed. Thresholds are frozen before running and never changed after seeing results.

| Gate | Dataset | Threshold | Result | Status | Commit | Hash |
|------|---------|-----------|--------|--------|--------|------|
| Known targets | 50 | predefined | 46/46 | PASS | `{commit}` | `{sha12('validation_runs/known_targets/summary.json')}` |
| Injection | 888 | predefined | 52.48% | MEASURED | `{commit}` | `{sha12('validation_runs/injection/summary.json')}` |
| Adversarial FP | 48 | >=80% | 79.17% | FAIL | `{commit}` | `{sha12('validation_runs/adversarial_fp/summary.json')}` |
| Blind holdout | 144 | predefined | pending | PENDING | `{commit}` | `N/A` |
| FPP calibration | 200 | predefined | pending | PENDING | `{commit}` | `N/A` |

## Counts

- **Measured gates:** 3
- **Pending execution gates:** 2
- **Open (failed) gates:** 1

## Rules

1. `PENDING` != `PASS`.
2. Thresholds are frozen **before** running; never changed after seeing results.
3. Every row must be reproducible from the `commit` + dataset hash listed above.
4. The blind holdout is an exam, not a teacher — never tune on it.
5. If a gate fails, fix the algorithm on the **development** dataset, freeze a new version, then re-run.

_Last updated: {now}_
"""
Path("docs/validation_status.md").write_text(content)
print("Wrote docs/validation_status.md")
print(content)
PY_STATUS

echo
echo "########## 4) README.md — measured-gate block ##########"

python - <<'PY_README'
import re
from pathlib import Path

readme = Path("README.md")
if not readme.exists():
    print("README.md missing, skipping")
    raise SystemExit(0)

text = readme.read_text()

block = """<!-- validation-status:start -->
**Measured validation gates:** 3
**Pending execution gates:** 2
**Open gates:** 1

Authoritative table: [`docs/validation_status.md`](docs/validation_status.md).
<!-- validation-status:end -->"""

if "<!-- validation-status:start -->" in text:
    text = re.sub(
        r"<!-- validation-status:start -->.*?<!-- validation-status:end -->",
        block, text, flags=re.DOTALL
    )
    print("Replaced existing block.")
else:
    text = text.rstrip() + "\n\n" + block + "\n"
    print("Appended block at end of README.")

readme.write_text(text)
PY_README

echo
echo "########## 5) Git RC tag ##########"

if git rev-parse --verify v0.10.0-validation-rc1 >/dev/null 2>&1; then
    echo "Tag v0.10.0-validation-rc1 already exists — skipping."
else
    git add pyproject.toml docs/validation_status.md README.md 2>/dev/null || true
    git -c user.email="validation@astrotransit.local" \
        -c user.name="AstroTransit Validation" \
        commit -m "validation(rc1): lock coverage to 90, add validation status table" \
        || echo "(nothing to commit or commit failed — continuing)"
    git tag -a v0.10.0-validation-rc1 -m "Validation RC1" \
        && echo "Created tag v0.10.0-validation-rc1" \
        || echo "(tag creation failed or already exists)"
fi

echo
echo "########## 6) VERIFY ##########"

echo "--- git diff (last commit + working tree) ---"
git --no-pager diff HEAD~1 -- pyproject.toml README.md docs/validation_status.md 2>/dev/null | head -200 || true
echo "(if no previous commit, showing working tree diff instead)"
git --no-pager diff -- pyproject.toml README.md docs/validation_status.md | head -200 || true
echo
echo "--- final docs/validation_status.md ---"
cat docs/validation_status.md
echo
echo "--- coverage smoke test (may take a minute) ---"
if python -c "import pytest" 2>/dev/null; then
    python -m pytest --cov=astrotransit --cov-branch --cov-report=term-missing -q 2>&1 | tail -45 || true
else
    echo "(pytest not importable in this venv)"
fi

echo
echo "=========================================="
echo " PHASE 0 complete."
echo " Log: $LOG"
echo "=========================================="
