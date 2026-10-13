#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

S=$(cat /tmp/phase3_scratch 2>/dev/null)
echo "scratch: $S"

python - "$S" <<'PY'
import json, sys
from pathlib import Path
from collections import Counter

S = Path(sys.argv[1])
rows = []
for sp in sorted((S/"shards").glob("shard-*.json")):
    try:
        d = json.loads(sp.read_text())
    except Exception:
        continue
    rows.extend(d.get("rows", []))
print(f"total rows: {len(rows)}")

# Group by label
by_label = {"false_positive": [], "quiet_star": [], "planet": []}
for r in rows:
    lab = r.get("label")
    if lab in by_label:
        by_label[lab].append(r)

def stats(rows_list, name, want_accepted=False):
    n = len(rows_list)
    if n == 0:
        print(f"  {name}: 0 rows"); return
    evaluated = [r for r in rows_list if r.get("evaluated")]
    err = [r for r in rows_list if r.get("error")]
    accepted = [r for r in rows_list if r.get("accepted_candidate") is True]
    rejected = [r for r in rows_list if r.get("accepted_candidate") is False]
    n_eval = len(evaluated)
    print(f"\n=== {name} (n={n}) ===")
    print(f"  evaluated:  {n_eval}")
    print(f"  errors:     {len(err)}")
    print(f"  accepted:   {len(accepted)}")
    print(f"  rejected:   {len(rejected)}")
    if n_eval > 0:
        rate = len(accepted) / n_eval
        print(f"  accept_rate = {rate:.4f}")
        if want_accepted:
            print(f"  (this is the FALSE-POSITIVE RATE on labelled FPs)")
        else:
            print(f"  (this is the FALSE-ALARM RATE on quiet controls)")
    # Errors breakdown
    if err:
        print(f"  error kinds:")
        for k, v in Counter(str(r.get("error"))[:60] for r in err).most_common(5):
            print(f"    {v:3d}x {k}")

stats(by_label["false_positive"], "FALSE POSITIVES (should be REJECTED)", want_accepted=True)
stats(by_label["quiet_star"], "QUIET STARS (should NOT have a candidate)", want_accepted=False)

# quick per-shard outcomes
print()
print("=== per shard ===")
by_shard = {}
for sp in sorted((S/"shards").glob("shard-*.json")):
    try:
        d = json.loads(sp.read_text())
    except Exception:
        continue
    rows = d.get("rows", [])
    fp = sum(1 for r in rows if r.get("label")=="false_positive")
    qs = sum(1 for r in rows if r.get("label")=="quiet_star")
    fp_acc = sum(1 for r in rows if r.get("label")=="false_positive" and r.get("accepted_candidate") is True)
    qs_acc = sum(1 for r in rows if r.get("label")=="quiet_star" and r.get("accepted_candidate") is True)
    print(f"  {sp.name:20s}  fp={fp:2d} (acc={fp_acc})  quiet={qs:2d} (acc={qs_acc})  rows={d.get('case_count')}")

# Also count how many rows have 'error' - the quiet targets often have no sectors
print()
print("=== error rows detail ===")
for r in rows:
    if r.get("error"):
        print(f"  {r.get('target_id'):>12s}  label={r.get('label'):20s}  err={str(r.get('error'))[:70]}")
PY
