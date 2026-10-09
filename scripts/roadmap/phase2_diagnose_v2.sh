#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase2_diag_v2_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== PHASE 2 DIAGNOSE v2 (available fields only) =="

SCRATCH=$(cat /tmp/phase2b_full_scratch)

python - "$SCRATCH" <<'PY'
import json, sys
from pathlib import Path
from collections import Counter, defaultdict
scratch = Path(sys.argv[1])

rows = []
for sp in sorted((scratch/"shards").glob("shard-*.json")):
    d = json.loads(sp.read_text())
    r = d.get("rows") if isinstance(d, dict) else d
    rows.extend(r)
print(f"total rows: {len(rows)}")

# What fraction of each stratum is accepted?
by_stratum = defaultdict(lambda: {"n": 0, "accepted": 0, "errors": 0,
                                  "classes": Counter(), "scores": []})
for r in rows:
    s = r.get("stratum", "?")
    b = by_stratum[s]
    b["n"] += 1
    if r.get("error"):
        b["errors"] += 1
        continue
    if r.get("accepted_candidate"):
        b["accepted"] += 1
    for c in (r.get("quality_classes") or []):
        b["classes"][str(c)] += 1
    for v in (r.get("quality_scores") or []):
        if v is not None:
            b["scores"].append(float(v))

print()
print("=== Per-stratum acceptance (the actual metric) ===")
for s in sorted(by_stratum):
    b = by_stratum[s]
    n_eval = b["n"] - b["errors"]
    rate = b["accepted"]/n_eval if n_eval else 0
    print(f"  {s:24s} n={b['n']:3d} err={b['errors']:2d} eval={n_eval:3d} "
          f"accepted={b['accepted']:3d}  accept_rate={rate:.3f}")
    print(f"     classes: {dict(b['classes'])}")
    if b["scores"]:
        ss = sorted(b["scores"])
        print(f"     scores:  min={ss[0]:.1f} med={ss[len(ss)//2]:.1f} max={ss[-1]:.1f}")

# For APC specifically: accepted vs rejected
print()
print("=== APC specifics: accepted vs not ===")
apc = [r for r in rows if r.get("stratum") == "false_positive:APC"]
acc = [r for r in apc if r.get("accepted_candidate")]
rej = [r for r in apc if not r.get("accepted_candidate") and not r.get("error")]
print(f"  accepted: {len(acc)}")
print(f"  rejected: {len(rej)}")
print(f"  errors:   {len(apc)-len(acc)-len(rej)}")

for label, grp in (("ACCEPTED (bad)", acc), ("REJECTED (good)", rej)):
    print(f"\n--- {label} ---")
    for r in grp:
        print(f"  {r['target_id']:>10s}  "
              f"classes={r.get('quality_classes')}  "
              f"scores={[round(x,1) for x in (r.get('quality_scores') or [])]}")

# FP:FP specifics
print()
print("=== FP:FP accepted (the biggest bucket) ===")
fp = [r for r in rows if r.get("stratum") == "false_positive:FP"
      and r.get("accepted_candidate") and not r.get("error")]
print(f"  count: {len(fp)}")
for r in fp[:20]:
    print(f"  {r['target_id']:>10s}  "
          f"classes={r.get('quality_classes')}  "
          f"scores={[round(x,1) for x in (r.get('quality_scores') or [])]}")

# Planet misses (FN)
print()
print("=== Planet misses (FN) ===")
missed = [r for r in rows
          if str(r.get("stratum", "")).startswith("planet:")
          and not r.get("accepted_candidate") and not r.get("error")]
print(f"  count: {len(missed)}")
for r in missed[:20]:
    print(f"  {r['target_id']:>10s} {r['stratum']:20s} "
          f"classes={r.get('quality_classes')}  "
          f"scores={[round(x,1) for x in (r.get('quality_scores') or [])]}")

# Score threshold sweep: what threshold would maximize balanced accuracy?
print()
print("=== Score threshold sweep (mean quality score) ===")
def mean_score(r):
    ss = [float(x) for x in (r.get("quality_scores") or []) if x is not None]
    return sum(ss)/len(ss) if ss else None

labeled = []
for r in rows:
    if r.get("error"): continue
    s = str(r.get("stratum",""))
    if s.startswith("planet:"):
        labeled.append((mean_score(r), r.get("accepted_candidate"), "planet"))
    elif s.startswith("false_positive:"):
        labeled.append((mean_score(r), r.get("accepted_candidate"), "fp"))

labeled = [(sc, ac, lab) for (sc, ac, lab) in labeled if sc is not None]
print(f"  labeled with score: {len(labeled)}")

# Sweep a "reject if mean_score < threshold" rule
for thr in (40, 50, 55, 60, 65, 70, 75, 80):
    tp = sum(1 for sc, ac, lab in labeled if lab=="planet" and sc >= thr)
    fn = sum(1 for sc, ac, lab in labeled if lab=="planet" and sc < thr)
    fp = sum(1 for sc, ac, lab in labeled if lab=="fp" and sc >= thr)
    tn = sum(1 for sc, ac, lab in labeled if lab=="fp" and sc < thr)
    rec = tp/(tp+fn) if (tp+fn) else 0
    fpr = fp/(fp+tn) if (fp+tn) else 0
    ba = (rec + (1-fpr))/2
    print(f"  thr={thr:3d}  TP={tp:3d} FN={fn:3d} FP={fp:3d} TN={tn:3d}  "
          f"recall={rec:.3f} fpr={fpr:.3f} balanced_acc={ba:.3f}")
PY

echo
echo "== DONE =="
