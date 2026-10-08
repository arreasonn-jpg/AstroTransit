#!/usr/bin/env bash
# PHASE 1C: root-cause the report.json vs rows.jsonl discrepancy.
# Read-only. No file mutations.

set -uo pipefail
REPO="$HOME/AstroTransit"
cd "$REPO" || { echo "FATAL: $REPO missing"; exit 1; }
source .venv/bin/activate || { echo "FATAL: .venv activate"; exit 1; }

LOG="$HOME/phase1c_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

echo "=========================================="
echo " PHASE 1C: git-history root cause"
echo " Log: $LOG"
echo "=========================================="

echo
echo "########## 1) Last commits that touched each artifact ##########"
for f in \
  validation_runs/final_acceptance_v1/adversarial_fp/report.json \
  validation_runs/final_acceptance_v1/adversarial_fp/rows.jsonl \
  validation_runs/final_acceptance_v1/adversarial_fp/corpus_manifest.json \
  validation_runs/final_acceptance_v1/program.json \
  configs/benchmark_fp.toml ; do
  echo "--- $f ---"
  if [ -f "$f" ]; then
    git log --format="  %h %ad %s" --date=short -6 -- "$f" || true
  else
    echo "  MISSING"
  fi
done

echo
echo "########## 2) Most recent 30 commits ##########"
git log --format="%h %ad %s" --date=short -30 || true

echo
echo "########## 3) Commits touching quality/ + adversarial_fp over last 40 ##########"
git log --format="%h %ad %s" --date=short -40 -- \
  astrotransit/quality/ \
  astrotransit/validation/adversarial_fp.py \
  astrotransit/detection/ \
  scripts/validation/run_adversarial_fp_controls.py || true

echo
echo "########## 4) Identify the two commits ##########"
REPORT_COMMIT=$(git log -1 --format=%h -- \
  validation_runs/final_acceptance_v1/adversarial_fp/report.json 2>/dev/null || echo "")
ROWS_COMMIT=$(git log -1 --format=%h -- \
  validation_runs/final_acceptance_v1/adversarial_fp/rows.jsonl 2>/dev/null || echo "")
echo "report.json last modified at:  $REPORT_COMMIT"
echo "rows.jsonl  last modified at:  $ROWS_COMMIT"
echo
if [ -n "$REPORT_COMMIT" ] && [ -n "$ROWS_COMMIT" ] && [ "$REPORT_COMMIT" != "$ROWS_COMMIT" ]; then
  echo ">>> DIFFERENT COMMITS — smoking gun."
  echo
  echo "--- commit message for report.json ---"
  git log -1 --format="%H%n%an %ad%n%s%n%n%b" "$REPORT_COMMIT" -- || true
  echo
  echo "--- commit message for rows.jsonl ---"
  git log -1 --format="%H%n%an %ad%n%s%n%n%b" "$ROWS_COMMIT" -- || true
  echo
  echo "--- commits in between ---"
  git log --format="%h %ad %s" --date=short "$REPORT_COMMIT".."$ROWS_COMMIT" || true
  echo
  echo "--- files changed between those two commits (top 40) ---"
  git diff --stat "$REPORT_COMMIT" "$ROWS_COMMIT" | tail -40 || true
fi

echo
echo "########## 5) What changed in vetting.py since report.json's commit ##########"
if [ -n "$REPORT_COMMIT" ]; then
  echo "--- diffstat: quality/ since $REPORT_COMMIT ---"
  git diff --stat "$REPORT_COMMIT" HEAD -- astrotransit/quality/ || true
  echo
  echo "--- diffstat: detection/ since $REPORT_COMMIT ---"
  git diff --stat "$REPORT_COMMIT" HEAD -- astrotransit/detection/ || true
  echo
  echo "--- diffstat: scripts/validation/ since $REPORT_COMMIT ---"
  git diff --stat "$REPORT_COMMIT" HEAD -- scripts/validation/ || true
  echo
  echo "--- unified diff: astrotransit/quality/vetting.py $REPORT_COMMIT..HEAD ---"
  git diff "$REPORT_COMMIT" HEAD -- astrotransit/quality/vetting.py | head -400 || true
  echo
  echo "--- unified diff: astrotransit/validation/adversarial_fp.py $REPORT_COMMIT..HEAD ---"
  git diff "$REPORT_COMMIT" HEAD -- astrotransit/validation/adversarial_fp.py | head -400 || true
  echo
  echo "--- unified diff: astrotransit/quality/pipeline.py $REPORT_COMMIT..HEAD ---"
  git diff "$REPORT_COMMIT" HEAD -- astrotransit/quality/pipeline.py | head -200 || true
fi

echo
echo "########## 6) Full current astrotransit/quality/vetting.py ##########"
if [ -f astrotransit/quality/vetting.py ]; then
  wc -l astrotransit/quality/vetting.py
  echo "---"
  cat astrotransit/quality/vetting.py
else
  echo "MISSING"
fi

echo
echo "########## 7) program.json — adversarial gate declaration ##########"
python - <<'PY'
import json
from pathlib import Path
p = Path("validation_runs/final_acceptance_v1/program.json")
if not p.exists():
    print("MISSING"); raise SystemExit
d = json.loads(p.read_text())
print("top-level keys:", sorted(d.keys()))
def walk(o, prefix=""):
    if isinstance(o, dict):
        gid = o.get("id")
        if isinstance(gid, str) and ("adversarial" in gid.lower() or "fp" in gid.lower()):
            print(f"\n--- gate: {gid} ---")
            print(json.dumps(o, indent=2)[:4000])
        for k, v in o.items():
            walk(v, prefix + "/" + str(k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            walk(v, prefix + f"[{i}]")
walk(d)
PY

echo
echo "########## 8) configs/benchmark_fp.toml (full) ##########"
cat configs/benchmark_fp.toml 2>/dev/null || echo "MISSING"

echo
echo "########## 9) docs mention of the 79.17% number ##########"
grep -rn -E "79\.17|38[/ ]|adversarial.*reject|rejection.*adversarial" \
  docs/ README.md 2>/dev/null | head -30 || true

echo
echo "=========================================="
echo " PHASE 1C complete."
echo "=========================================="
