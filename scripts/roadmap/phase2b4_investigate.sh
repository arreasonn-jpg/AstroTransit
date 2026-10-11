#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase2b4_invest_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== _assign_class investigation =="

echo
echo "########## 1) Full _assign_class method ##########"
python - <<'PY'
from pathlib import Path
lines = Path("astrotransit/quality/scorer.py").read_text().splitlines()
start = next((i for i, l in enumerate(lines, 1) if "def _assign_class" in l), None)
if start is None:
    print("NOT FOUND"); raise SystemExit(1)
end = start
for j in range(start, len(lines)):
    if j > start-1 and lines[j].startswith("    def "):
        end = j
        break
else:
    end = len(lines)
print(f"lines {start}-{end}")
for k in range(start-1, end):
    print(f"{k+1:4d} | {lines[k]}")
PY

echo
echo "########## 2) Class thresholds and constants ##########"
grep -n "CLASS_\|class_threshold\|class_a\|class_b\|class_c\|class_d\|total_score >=\|total_score <" astrotransit/quality/scorer.py | head -30

echo
echo "########## 3) What classes are the FP vs planet targets? ##########"
python - <<'PY'
import json
from pathlib import Path
from collections import Counter, defaultdict

S = Path("/tmp/phase2b4_scratch").read_text().strip()
shards = Path(S) / "shards"
class_by_stratum = defaultdict(Counter)
for sp in sorted(shards.glob("shard-*.json")):
    try:
        d = json.loads(sp.read_text())
    except Exception:
        continue
    for r in d.get("rows", []):
        if r.get("error"): continue
        stratum = r.get("stratum", "?")
        for sec in (r.get("per_sector") or []):
            cls = sec.get("quality_class") or "?"
            class_by_stratum[stratum][cls] += 1

print(f"  {'stratum':24s}  {'A':>4s}  {'B':>4s}  {'C':>4s}  {'D':>4s}  {'?':>4s}")
for s in sorted(class_by_stratum):
    c = class_by_stratum[s]
    print(f"  {s:24s}  {c['A']:>4d}  {c['B']:>4d}  {c['C']:>4d}  {c['D']:>4d}  {c['']:>4d}")
PY

echo
echo "########## 4) Sample planet targets that lost (rejected) ##########"
python - <<'PY'
import json
from pathlib import Path
S = Path("/tmp/phase2b4_scratch").read_text().strip()
for sp in sorted((Path(S) / "shards").glob("shard-*.json")):
    try:
        d = json.loads(sp.read_text())
    except Exception:
        continue
    for r in d.get("rows", []):
        if r.get("error"): continue
        if not str(r.get("stratum","")).startswith("planet:"): continue
        if r.get("accepted_candidate"): continue
        for sec in (r.get("per_sector") or []):
            print(f"  {r['target_id']:>10s}  {r.get('stratum'):20s}  "
                  f"class={sec.get('quality_class'):>2s}  "
                  f"score={sec.get('quality_score') or 0:5.1f}  "
                  f"rejected_by_class={sec.get('rejected_by_class')}  "
                  f"is_fp={sec.get('vetting_is_false_positive')}  "
                  f"n_fail={sec.get('vetting_n_fail')}  "
                  f"sec_snr={sec.get('metric_secondary_eclipse_snr') or 0:.2f}")
            break  # just first sector
PY

echo
echo "== DONE =="
