#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase3_analyze_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 3 analysis (all available) =="

S=$(cat /tmp/phase3_scratch)
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

def stats(group, name):
    n = len(group)
    evaluated = [r for r in group if r.get("evaluated")]
    err = [r for r in group if r.get("error")]
    acc = [r for r in group if r.get("accepted_candidate") is True]
    rej = [r for r in group if r.get("accepted_candidate") is False]
    n_eval = len(evaluated)
    print(f"\n=== {name} ===")
    print(f"  total rows:    {n}")
    print(f"  evaluated:     {n_eval}")
    print(f"  errors:        {len(err)}")
    print(f"  accepted:      {len(acc)}")
    print(f"  rejected:      {len(rej)}")
    if n_eval > 0:
        print(f"  accept rate:   {len(acc)/n_eval:.4f}")
        print(f"  reject rate:   {len(rej)/n_eval:.4f}")
    if err:
        print(f"  error kinds:")
        for k, v in Counter(str(r.get("error"))[:60] for r in err).most_common(5):
            print(f"    {v:3d}x {k}")

fp    = [r for r in rows if r.get("label") == "false_positive"]
quiet = [r for r in rows if r.get("label") == "quiet_star"]

stats(fp, "FALSE POSITIVES (want REJECTED)")
stats(quiet, "QUIET STARS (want NOT accepted)")

# Summary
fp_eval = [r for r in fp if r.get("evaluated")]
quiet_eval = [r for r in quiet if r.get("evaluated")]
print("\n" + "="*78)
print("SUMMARY")
print("="*78)
if fp_eval:
    fp_acc = sum(1 for r in fp_eval if r.get("accepted_candidate") is True)
    print(f"  FP rejection rate:  {1 - fp_acc/len(fp_eval):.4f}  ({len(fp_eval)-fp_acc}/{len(fp_eval)})")
if quiet_eval:
    quiet_acc = sum(1 for r in quiet_eval if r.get("accepted_candidate") is True)
    print(f"  Quiet FPR:          {quiet_acc/len(quiet_eval):.4f}  ({quiet_acc}/{len(quiet_eval)})")

# Gate contract
total_err = sum(1 for r in rows if r.get("error"))
print()
print("GATE CONTRACT:")
print(f"  FP labelled:     {len(fp)}  (>= 100)")
print(f"  Quiet labelled:  {quiet_eval.__len__()}  (>= 100)")
print(f"  FP evaluated:    {len(fp_eval)}  (>= 100)")
print(f"  Quiet evaluated: {len(quiet_eval)}  (>= 100)")
print(f"  Total errors:    {total_err}  (== 0)")
PY
