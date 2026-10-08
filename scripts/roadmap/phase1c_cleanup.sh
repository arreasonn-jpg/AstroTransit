#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

echo "===== Working tree state ====="
git status --short | head -30
echo

echo "===== vetting.py HARD/SOFT sets right now ====="
python - <<'PY'
from astrotransit.quality.vetting import HARD_FAIL_TESTS, SOFT_FAIL_TESTS
print("HARD:", sorted(HARD_FAIL_TESTS))
print("SOFT:", sorted(SOFT_FAIL_TESTS))
PY
echo

echo "===== Removing orphan guard test (kept in scratch for reference) ====="
if [ -f tests/test_vetting_secondary_eclipse_hard.py ]; then
  mv tests/test_vetting_secondary_eclipse_hard.py \
     outputs/adv-fp-fix-20261008_160702/test_vetting_secondary_eclipse_hard.py.orphan
  echo "  moved to scratch"
else
  echo "  (already gone)"
fi
echo

echo "===== Fresh report snapshot (kept for decision) ====="
python - <<'PY'
import json
from pathlib import Path
p = Path("outputs/adv-fp-fix-20261008_160702/report.json")
if not p.exists():
    print("MISSING"); raise SystemExit
rep = json.loads(p.read_text())
print("status:", rep["status"])
print("blocking:", rep.get("blocking_reasons"))
print("overall:", json.dumps(rep["overall"], indent=2))
PY
echo

echo "===== Which 4 controls got rejected? ====="
python - <<'PY'
import json
from pathlib import Path
rows = [json.loads(l) for l in Path(
    "outputs/adv-fp-fix-20261008_160702/rows.jsonl"
).read_text().splitlines() if l.strip()]
ctrl = [r for r in rows if r.get("family") == "planetary_control"]
print(f"controls: {len(ctrl)}")
for r in ctrl:
    flags = r.get("fp_flags") or []
    outcome = r.get("outcome")
    mark = "REJECTED" if outcome != "leaked_as_candidate" else "accepted"
    print(f"  {r['scenario_id']:32s} {mark:9s} "
          f"flags={flags} "
          f"n_fail={r.get('n_fail')} "
          f"secondary_ppm={r.get('secondary_eclipse_depth_ppm')}")
PY
echo
echo "DONE. Log saved."
