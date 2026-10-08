#!/usr/bin/env bash
# PHASE 1B DIAGNOSTIC (read-only). Reconciles report.json vs rows.jsonl vs
# the phase1a script's numbers. Mutates nothing.

set -uo pipefail
REPO="$HOME/AstroTransit"
cd "$REPO" || { echo "FATAL: $REPO missing"; exit 1; }
source .venv/bin/activate || { echo "FATAL: .venv activate"; exit 1; }
LOG="$HOME/phase1b_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

echo "=========================================="
echo " PHASE 1B DIAGNOSTIC (read-only)"
echo " Log: $LOG"
echo "=========================================="

echo
echo "########## 1) Which files exist ##########"
for f in \
  validation_runs/final_acceptance_v1/adversarial_fp/rows.jsonl \
  validation_runs/final_acceptance_v1/adversarial_fp/report.json \
  validation_runs/final_acceptance_v1/adversarial_fp/corpus_manifest.json \
  validation_runs/final_acceptance_v1/adversarial_fp/leakage_taxonomy.json \
  validation_runs/final_acceptance_v1/adversarial_fp/confusion_matrix.json \
  astrotransit/validation/leakage_taxonomy.py \
  scripts/roadmap/analyze_adversarial_leaks.py \
  scripts/roadmap/confusion_matrix.py \
  scripts/roadmap/phase1a_leakage.sh ; do
  [ -f "$f" ] && echo "  OK   $f" || echo "  MISS $f"
done

echo
echo "########## 2) rows.jsonl — raw outcome distribution ##########"
python - <<'PY'
import json
from pathlib import Path
from collections import Counter

p = Path("validation_runs/final_acceptance_v1/adversarial_fp/rows.jsonl")
if not p.exists():
    print("rows.jsonl MISSING"); raise SystemExit
rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
print("total rows:", len(rows))
print("first row keys:", sorted(rows[0].keys()))
print()
print("outcome counts (all rows):")
for k, v in sorted(Counter(r.get("outcome") for r in rows).items()):
    print(f"  {k:35s} {v}")
print()
print("(family, outcome) x count:")
for (fam, out), n in sorted(Counter((r.get("family"), r.get("outcome")) for r in rows).items()):
    print(f"  {fam:32s} {out:35s} {n}")
print()
print("family totals:")
for k, v in sorted(Counter(r.get("family") for r in rows).items()):
    print(f"  {k:32s} {v}")
PY

echo
echo "########## 3) report.json — what the frozen gate says ##########"
python - <<'PY'
import json
from pathlib import Path
p = Path("validation_runs/final_acceptance_v1/adversarial_fp/report.json")
if not p.exists():
    print("report.json MISSING"); raise SystemExit
rep = json.loads(p.read_text())
print("status:", rep.get("status"))
print("blocking_reasons:", rep.get("blocking_reasons"))
print()
print("overall:")
print(json.dumps(rep.get("overall", {}), indent=2))
print()
print("outcome_counts:", json.dumps(rep.get("outcome_counts", {}), indent=2))
print()
print("per-family:")
for fam, blk in rep.get("families", {}).items():
    print(f"  {fam:32s} n_eval={blk.get('n_evaluated')} "
          f"rej={blk.get('rejected_count')} leak={blk.get('leak_count')} "
          f"accept={blk.get('accepted_count')}")
PY

echo
echo "########## 4) Independent recompute: build_adversarial_report(rows) ##########"
python - <<'PY'
import json
from pathlib import Path
from astrotransit.validation.adversarial_fp import build_adversarial_report
rows = [json.loads(l) for l in Path(
    "validation_runs/final_acceptance_v1/adversarial_fp/rows.jsonl"
).read_text().splitlines() if l.strip()]
rep = build_adversarial_report(rows)
print("recomputed status:", rep.get("status"))
print("recomputed overall:")
print(json.dumps(rep.get("overall", {}), indent=2))
print("recomputed blocking_reasons:", rep.get("blocking_reasons"))
PY

echo
echo "########## 5) phase1a_leakage.sh (full) ##########"
cat scripts/roadmap/phase1a_leakage.sh 2>/dev/null || echo "(no phase1a_leakage.sh)"

echo
echo "########## 6) analyze_adversarial_leaks.py (full) ##########"
cat scripts/roadmap/analyze_adversarial_leaks.py 2>/dev/null || echo "(no analyze_adversarial_leaks.py)"

echo
echo "########## 7) confusion_matrix.py (full) ##########"
cat scripts/roadmap/confusion_matrix.py 2>/dev/null || echo "(no confusion_matrix.py)"

echo
echo "########## 8) leakage_taxonomy.py (public surface) ##########"
python - <<'PY'
import inspect
try:
    from astrotransit.validation import leakage_taxonomy as lt
    print("import OK")
    for n in sorted(dir(lt)):
        if n.startswith("_"): continue
        o = getattr(lt, n)
        if inspect.isfunction(o) or inspect.isclass(o):
            try: print(f"  {n}{inspect.signature(o)}")
            except Exception: print(f"  {n}")
        elif isinstance(o, (str, int, float, list, tuple, set, frozenset, dict)):
            print(f"  {n} = {o!r}"[:220])
except Exception as e:
    print("import FAILED:", e)
PY

echo
echo "########## 9) leakage_taxonomy.json (summary) ##########"
python - <<'PY'
import json
from pathlib import Path
p = Path("validation_runs/final_acceptance_v1/adversarial_fp/leakage_taxonomy.json")
if not p.exists():
    print("MISSING"); raise SystemExit
d = json.loads(p.read_text())
def show(o, pre=""):
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, (str, int, float)):
                print(f"{pre}{k}: {v}")
            elif isinstance(v, list):
                print(f"{pre}{k}: list[{len(v)}]")
            elif isinstance(v, dict):
                print(f"{pre}{k}: dict{{{len(v)}}}")
show(d)
PY

echo
echo "########## 10) confusion_matrix.json (raw) ##########"
cat validation_runs/final_acceptance_v1/adversarial_fp/confusion_matrix.json 2>/dev/null || echo "(none)"

echo
echo "=========================================="
echo " PHASE 1B complete."
echo "=========================================="
