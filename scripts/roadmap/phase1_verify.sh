#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

echo "=========================================="
echo " FAZ 1 VERIFY (read-only)"
echo "=========================================="

echo
echo "########## 1) Gate status from frozen report ##########"
python - <<'PY'
import json, hashlib
from pathlib import Path
p = Path("validation_runs/final_acceptance_v1/adversarial_fp/report.json")
rep = json.loads(p.read_text())
ov = rep["overall"]
print(f"  report.json sha256: {hashlib.sha256(p.read_bytes()).hexdigest()}")
print(f"  status:            {rep['status']}")
print(f"  blocking_reasons:  {rep.get('blocking_reasons')}")
print(f"  rejection:         {ov['adversarial_rejected']}/{ov['adversarial_scenarios']} = {ov['adversarial_rejection_rate']}")
print(f"  control:           {ov['control_accepted']}/{ov['control_scenarios']} = {ov['control_acceptance_rate']}")
print(f"  wilson_95:         {ov['adversarial_rejection_wilson_95']}")
print(f"  by_stage:          {ov['adversarial_rejected_by_stage']}")
print()
print("  per-family (adversarial only):")
for fam, blk in sorted(rep["families"].items()):
    if blk.get("expected") == "false_positive":
        print(f"    {fam:32s} n={blk['n_evaluated']} rate={blk['rejection_rate']}")
print()
print("  contract check (program.json):")
print("    overall_rejection_rate >= 0.8 :", ov['adversarial_rejection_rate'] >= 0.8)
print("    control_acceptance_rate >= 0.5:", ov['control_acceptance_rate'] >= 0.5)
print("    total_errors == 0             :", ov['total_errors'] == 0)
for fam, blk in sorted(rep["families"].items()):
    if blk.get("expected") == "false_positive":
        ok = (blk.get("rejection_rate") or 0) >= 0.5
        print(f"    {fam}.rejection_rate >= 0.5   : {ok}")
PY

echo
echo "########## 2) Fresh rows.jsonl matches report ##########"
python - <<'PY'
import json
from pathlib import Path
from collections import Counter
rows = [json.loads(l) for l in Path(
    "validation_runs/final_acceptance_v1/adversarial_fp/rows.jsonl"
).read_text().splitlines() if l.strip()]
print(f"  rows: {len(rows)}")
print(f"  outcomes: {dict(Counter(str(r.get('outcome')) for r in rows))}")
adv = [r for r in rows if r.get("family") != "planetary_control"]
leaks = [r for r in adv if r.get("outcome") == "leaked_as_candidate"]
print(f"  adversarial leaks: {len(leaks)} (should be 7)")
for r in leaks:
    print(f"    {r['scenario_id']:34s} flags={r.get('fp_flags')} n_fail={r.get('n_fail')} fpp={r.get('fpp')}")
PY

echo
echo "########## 3) leakage_taxonomy fix verified ##########"
python - <<'PY'
import json
from pathlib import Path
p = Path("validation_runs/final_acceptance_v1/adversarial_fp/leakage_taxonomy.json")
if not p.exists():
    print("  MISSING"); raise SystemExit
d = json.loads(p.read_text())
print(f"  total leaks: {d['total']} (should be 7, not 43)")
print(f"  by_category: {d['by_category']}")
print(f"  by_family:")
for fam, n in d["by_family"].items():
    print(f"    {fam:32s} {n}")
print(f"  planetary_control in leaks: {'planetary_control' in d['by_family']} (should be False)")
PY

echo
echo "########## 4) confusion matrix matches report ##########"
python - <<'PY'
import json
from pathlib import Path
p = Path("validation_runs/final_acceptance_v1/adversarial_fp/confusion_matrix.json")
if not p.exists():
    print("  MISSING"); raise SystemExit
d = json.loads(p.read_text())
print(f"  matrix: {d['matrix']}")
print(f"  metrics: {d['metrics']}")
PY

echo
echo "########## 5) Docs reflect 85.42% ##########"
echo "--- docs/validation_status.md adversarial row ---"
grep -i "adversarial" docs/validation_status.md || true
echo "--- README.md adversarial references ---"
grep -iE "adversarial|85\.42|79\.17" README.md | head -10 || true
echo "--- measured_validation_results.md last-updated marker ---"
grep -iE "85\.42|41/48|rejection 0\.8" docs/measured_validation_results.md | head -10 || true

echo
echo "########## 6) vetting.py — current HARD/SOFT/SNR gate ##########"
python - <<'PY'
from astrotransit.quality.vetting import HARD_FAIL_TESTS, SOFT_FAIL_TESTS
print(f"  HARD contains secondary_eclipse    : {'secondary_eclipse' in HARD_FAIL_TESTS}")
print(f"  SOFT contains secondary_eclipse    : {'secondary_eclipse' in SOFT_FAIL_TESTS}")
print(f"  HARD contains secondary_eclipse_snr: {'secondary_eclipse_snr' in HARD_FAIL_TESTS}")
# check the SNR gate is present in source
import re
from pathlib import Path
src = Path("astrotransit/quality/vetting.py").read_text()
has_gate = "noise_floor_snr" in src
print(f"  _test_secondary_eclipse SNR gate   : {has_gate}")
PY

echo
echo "########## 7) Run FAZ 1 tests ##########"
python -m pytest \
  tests/test_vetting_secondary_eclipse_snr_gate.py \
  tests/test_leakage_taxonomy.py \
  tests/test_adversarial_fp.py \
  -q 2>&1 | tail -8

echo
echo "########## 8) Files to commit ##########"
echo "--- modified (tracked) ---"
git status --short | grep -E "^ M|^M " || true
echo "--- new (untracked, to include) ---"
git status --short | grep -E "^\?\? (astrotransit|docs|tests|scripts/roadmap|validation_runs/final_acceptance_v1/adversarial_fp/(confusion|leakage))" || true
echo "--- new (untracked, EXCLUDE from commit) ---"
git status --short | grep -E "^\?\? (outputs/|validation_runs/final_acceptance_v1/adversarial_fp/frozen_)" || true

echo
echo "=========================================="
echo " VERIFY COMPLETE"
echo "=========================================="
