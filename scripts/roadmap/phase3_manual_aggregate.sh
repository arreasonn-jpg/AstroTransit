#!/usr/bin/env bash
# Manual aggregate when a few shards are partial.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase3_manual_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== manual aggregate (lenient) =="

S=$(cat /tmp/phase3_scratch)
echo "scratch: $S"

python - "$S" <<'PY'
import json, sys
from pathlib import Path
from collections import Counter, defaultdict

S = Path(sys.argv[1])
rows = []
per_shard = {}
for sp in sorted((S/"shards").glob("shard-*.json")):
    try:
        d = json.loads(sp.read_text())
    except Exception as e:
        print(f"  SKIP {sp.name}: {e}")
        continue
    r = d.get("rows", [])
    per_shard[sp.name] = {"n": len(r), "partial": d.get("partial", False)}
    rows.extend(r)

print(f"total shards: {len(per_shard)}")
print(f"total rows:   {len(rows)}")
print(f"unique IDs:   {len({r.get('target_id') for r in rows})}")
print()
print("per shard:")
for k, v in per_shard.items():
    print(f"  {k:22s} n={v['n']:2d}  partial={v['partial']}")

# Split by label
def stats(group, name):
    n = len(group)
    if n == 0:
        print(f"  {name}: 0 rows"); return
    evaluated = [r for r in group if r.get("evaluated")]
    err = [r for r in group if r.get("error")]
    accepted = [r for r in group if r.get("accepted_candidate") is True]
    rejected = [r for r in group if r.get("accepted_candidate") is False]
    n_eval = len(evaluated)
    print(f"\n=== {name} ===")
    print(f"  total rows:   {n}")
    print(f"  evaluated:    {n_eval}")
    print(f"  errors:       {len(err)}")
    print(f"  accepted:     {len(accepted)}")
    print(f"  rejected:     {len(rejected)}")
    if n_eval > 0:
        print(f"  rate = {len(accepted)/n_eval:.4f}")
    if err:
        print(f"  error kinds:")
        for k, v in Counter(str(r.get("error"))[:60] for r in err).most_common(10):
            print(f"    {v:3d}x {k}")

fp = [r for r in rows if r.get("label") == "false_positive"]
quiet = [r for r in rows if r.get("label") == "quiet_star"]
planet = [r for r in rows if r.get("label") == "planet"]

stats(fp,    "FALSE POSITIVES (want REJECTED)")
stats(quiet, "QUIET STARS (want NOT accepted)")
stats(planet,"PLANETS (want accepted)")

print()
print("=" * 78)
print("SUMMARY NUMBERS")
print("=" * 78)
fp_eval = [r for r in fp if r.get("evaluated")]
quiet_eval = [r for r in quiet if r.get("evaluated")]
if fp_eval:
    fp_acc = sum(1 for r in fp_eval if r.get("accepted_candidate") is True)
    print(f"  FP rejection rate:  {1 - fp_acc/len(fp_eval):.4f}  ({len(fp_eval)-fp_acc}/{len(fp_eval)} rejected)")
if quiet_eval:
    quiet_acc = sum(1 for r in quiet_eval if r.get("accepted_candidate") is True)
    print(f"  Quiet FPR (false alarm rate): {quiet_acc/len(quiet_eval):.4f}  ({quiet_acc}/{len(quiet_eval)} accepted)")

# Gate contract check
print()
print("=" * 78)
print("GATE CONTRACT CHECKS")
print("=" * 78)
fp_total = len(fp)
quiet_total = len(quiet)
fp_err = sum(1 for r in fp if r.get("error"))
quiet_err = sum(1 for r in quiet if r.get("error"))
total_err = fp_err + quiet_err

print(f"  false_positives.labelled_count = {fp_total}  (>= 100)  {'PASS' if fp_total >= 100 else 'FAIL'}")
print(f"  quiet_controls.labelled_count  = {quiet_total}  (>= 100)  {'PASS' if quiet_total >= 100 else 'FAIL'}")
print(f"  evaluation.false_positives.evaluated_count = {len(fp_eval)}  (>= 100)  {'PASS' if len(fp_eval) >= 100 else 'FAIL'}")
print(f"  evaluation.quiet_controls.evaluated_count  = {len(quiet_eval)}  (>= 100)  {'PASS' if len(quiet_eval) >= 100 else 'FAIL'}")
print(f"  evaluation.total_errors = {total_err}  (== 0)  {'PASS' if total_err == 0 else 'FAIL'}")
PY

echo
echo "== DONE =="
