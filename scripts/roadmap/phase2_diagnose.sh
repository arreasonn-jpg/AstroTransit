#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase2_diag_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== PHASE 2 DIAGNOSE =="

SCRATCH=$(cat /tmp/phase2b_full_scratch)

echo
echo "########## 1) Row schema — what fields does a shard row have? ##########"
python - "$SCRATCH" <<'PY'
import json, sys
from pathlib import Path
scratch = Path(sys.argv[1])
first = None
for sp in sorted((scratch/"shards").glob("shard-*.json")):
    d = json.loads(sp.read_text())
    rows = d.get("rows") if isinstance(d, dict) else d
    if rows:
        first = rows[0]
        break
if first:
    print(json.dumps(first, indent=2, default=str)[:3000])
PY

echo
echo "########## 2) APC cases: full vetting detail ##########"
python - "$SCRATCH" <<'PY'
import json, sys
from pathlib import Path
from collections import Counter
scratch = Path(sys.argv[1])

all_rows = []
for sp in sorted((scratch/"shards").glob("shard-*.json")):
    d = json.loads(sp.read_text())
    rows = d.get("rows") if isinstance(d, dict) else d
    all_rows.extend(rows)

apc = [r for r in all_rows if r.get("stratum") == "false_positive:APC"]
print(f"APC rows: {len(apc)}")
print()

# Flag patterns across APC
flag_counter = Counter()
for r in apc:
    flags = r.get("fp_flags") or []
    if not flags:
        flag_counter["(no flags)"] += 1
    else:
        for f in flags:
            flag_counter[f] += 1
print("APC fp_flag frequency:")
for k, v in flag_counter.most_common():
    print(f"  {k:35s} {v}/{len(apc)}")
print()

# Outcome distribution
print("APC outcome distribution:")
for k, v in Counter(str(r.get("outcome")) for r in apc).most_common():
    print(f"  {k:35s} {v}")
print()

# FPP distribution
print("APC FPP values:")
for r in apc:
    print(f"  {r.get('target_id'):>10s}  outcome={r.get('outcome'):24s} "
          f"n_fail={r.get('n_fail')} n_warn={r.get('n_warn')} fpp={r.get('fpp')} "
          f"flags={r.get('fp_flags')}")
print()

# Compare: what fields does the vetting produce?
print("Keys available in one APC row:")
for r in apc[:1]:
    for k in sorted(r.keys()):
        v = r[k]
        s = str(v)[:80]
        print(f"  {k:35s} = {s}")
PY

echo
echo "########## 3) All-rows: which vetting tests fired where? ##########"
python - "$SCRATCH" <<'PY'
import json, sys
from pathlib import Path
from collections import Counter, defaultdict
scratch = Path(sys.argv[1])

all_rows = []
for sp in sorted((scratch/"shards").glob("shard-*.json")):
    d = json.loads(sp.read_text())
    rows = d.get("rows") if isinstance(d, dict) else d
    all_rows.extend(rows)

by_stratum = defaultdict(lambda: {"n": 0, "flag_counts": Counter(), "fpp": [], "n_fail": Counter()})
for r in all_rows:
    s = r.get("stratum", "?")
    b = by_stratum[s]
    b["n"] += 1
    for f in (r.get("fp_flags") or []):
        b["flag_counts"][f] += 1
    if r.get("fpp") is not None:
        b["fpp"].append(r["fpp"])
    b["n_fail"][str(r.get("n_fail"))] += 1

for s in sorted(by_stratum):
    b = by_stratum[s]
    print(f"--- {s} (n={b['n']}) ---")
    print(f"  n_fail distribution: {dict(b['n_fail'])}")
    fpps = b["fpp"]
    if fpps:
        print(f"  fpp: min={min(fpps):.3f} max={max(fpps):.3f} median={sorted(fpps)[len(fpps)//2]:.3f}")
    print(f"  flag frequency:")
    for k, v in b["flag_counts"].most_common():
        print(f"    {k:35s} {v}")
    print()
PY

echo
echo "########## 4) planet misses (FN): which planetary controls failed? ##########"
python - "$SCRATCH" <<'PY'
import json, sys
from pathlib import Path
scratch = Path(sys.argv[1])

all_rows = []
for sp in sorted((scratch/"shards").glob("shard-*.json")):
    d = json.loads(sp.read_text())
    rows = d.get("rows") if isinstance(d, dict) else d
    all_rows.extend(rows)

planets = [r for r in all_rows if str(r.get("stratum", "")).startswith("planet:")]
missed = [r for r in planets if r.get("outcome") != "true_positive"]
print(f"planets total: {len(planets)}, missed (FN): {len(missed)}")
for r in missed:
    print(f"  {r.get('target_id'):>10s} {r.get('stratum'):20s} "
          f"outcome={r.get('outcome')} "
          f"n_fail={r.get('n_fail')} n_warn={r.get('n_warn')} "
          f"fpp={r.get('fpp')} flags={r.get('fp_flags')}")
PY

echo
echo "== DIAGNOSE DONE =="
