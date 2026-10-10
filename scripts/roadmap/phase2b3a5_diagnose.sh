#!/usr/bin/env bash
# Diagnose with the fixed sec_snr metric on the latest dev scratch.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase2b3a5_diag_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 2b.3a.5 diagnose =="
echo "log: $LOG"

S=$(cat /tmp/phase2b3a4_scratch)
echo "scratch: $S"

python - "$S" <<'PY'
import json, sys
from pathlib import Path
from collections import Counter, defaultdict

scratch = Path(sys.argv[1])
rows = []
n_shards = 0
for sp in sorted((scratch/"shards").glob("shard-*.json")):
    try:
        d = json.loads(sp.read_text())
        rows.extend(d.get("rows", []))
        n_shards += 1
    except Exception as e:
        print(f"  skip {sp.name}: {e}")
print(f"shards: {n_shards}, rows: {len(rows)}")

def label_of(r):
    return "planet" if str(r.get("stratum", "")).startswith("planet:") else "fp"

def target_verdict(r):
    if r.get("error"): return "error"
    if r.get("accepted_candidate"): return "accepted"
    if r.get("accepted_candidate") is False: return "rejected"
    return "unknown"

# 1) Per-stratum
print()
print("=" * 78)
print("1) PER-STRATUM VERDICT")
print("=" * 78)
bs = defaultdict(lambda: Counter())
for r in rows:
    bs[r.get("stratum", "?")][target_verdict(r)] += 1
for s in sorted(bs):
    c = bs[s]
    n_eval = c["accepted"] + c["rejected"]
    rate = c["accepted"]/n_eval if n_eval else 0
    print(f"  {s:24s}  n={sum(c.values()):3d}  eval={n_eval:3d}  "
          f"acc={c['accepted']:3d}  rej={c['rejected']:3d}  "
          f"err={c['error']:2d}  accept_rate={rate:.3f}")

# 2) Detection vs classification baselines
print()
print("=" * 78)
print("2) BASELINES")
print("=" * 78)

def evaluate(name, accept_fn):
    tp=fn=fp=tn=0
    for r in rows:
        if r.get("error"): continue
        lab = label_of(r)
        ok = accept_fn(r)
        if lab == "planet":
            if ok: tp+=1
            else: fn+=1
        else:
            if ok: fp+=1
            else: tn+=1
    rec = tp/(tp+fn) if (tp+fn) else 0
    fpr = fp/(fp+tn) if (fp+tn) else 0
    ba = (rec + (1-fpr))/2
    print(f"  {name:55s} TP={tp:3d} FN={fn:3d} FP={fp:3d} TN={tn:3d}  "
          f"recall={rec:.3f} fpr={fpr:.3f} ba={ba:.3f}")

evaluate("[A] detection-level (cascade confirmed)",
         lambda r: bool(r.get("accepted_candidate")))

# 3) sec_snr coverage
print()
print("=" * 78)
print("3) sec_snr COVERAGE")
print("=" * 78)
total_sectors = 0
nonzero_sec = 0
sec_values = []
for r in rows:
    if r.get("error"): continue
    for sec in r.get("per_sector") or []:
        total_sectors += 1
        v = sec.get("metric_secondary_eclipse_snr") or 0
        if v > 0:
            nonzero_sec += 1
            sec_values.append(v)
print(f"  total sectors: {total_sectors}")
print(f"  sectors with sec_snr > 0: {nonzero_sec} ({100*nonzero_sec/max(1,total_sectors):.1f}%)")
if sec_values:
    sec_values.sort()
    print(f"  sec_snr distribution: min={sec_values[0]:.2f} "
          f"med={sec_values[len(sec_values)//2]:.2f} max={sec_values[-1]:.2f}")

# 4) NEW features vs OLD rules: sweep
print()
print("=" * 78)
print("4) RULE SWEEP with NEW metrics")
print("=" * 78)
print(f"  {'rule':<55s} {'TP':>3s} {'FN':>3s} {'FP':>3s} {'TN':>3s}  "
      f"{'recall':>7s} {'fpr':>6s} {'ba':>6s}")

def rule(name, reject_fn):
    tp=fn=fp=tn=0
    for r in rows:
        if r.get("error"): continue
        lab = label_of(r)
        sectors = r.get("per_sector") or []
        if not sectors:
            accepted = bool(r.get("accepted_candidate"))
        else:
            accepted = any(not reject_fn(s) for s in sectors)
        if lab == "planet":
            if accepted: tp+=1
            else: fn+=1
        else:
            if accepted: fp+=1
            else: tn+=1
    rec = tp/(tp+fn) if (tp+fn) else 0
    fpr = fp/(fp+tn) if (fp+tn) else 0
    ba = (rec + (1-fpr))/2
    print(f"  {name:<55s} {tp:3d} {fn:3d} {fp:3d} {tn:3d}  "
          f"{rec:7.3f} {fpr:6.3f} {ba:6.3f}")

# Baselines
rule("[A] reject nothing (detection-level)", lambda s: False)

# Old rules
rule("[B] reject if is_fp", lambda s: bool(s.get("vetting_is_false_positive")))
rule("[C] reject if n_fail >= 1", lambda s: (s.get("vetting_n_fail") or 0) >= 1)
rule("[D] reject if class==D", lambda s: str(s.get("quality_class") or "").endswith("D"))
rule("[E] reject if class in {C,D}",
     lambda s: str(s.get("quality_class") or "").endswith(("C","D")))

# New features
print()
print("  --- with sec_snr (the newly working metric) ---")
for thr in (1.0, 2.0, 3.0, 4.0, 5.0, 8.0, 10.0):
    rule(f"reject if sec_snr >= {thr}",
         lambda s, t=thr: (s.get("metric_secondary_eclipse_snr") or 0) >= t)

print()
print("  --- combinations ---")
rule("reject if class==D OR sec_snr >= 3",
     lambda s: str(s.get("quality_class") or "").endswith("D") or
               (s.get("metric_secondary_eclipse_snr") or 0) >= 3)
rule("reject if class==D OR sec_snr >= 5",
     lambda s: str(s.get("quality_class") or "").endswith("D") or
               (s.get("metric_secondary_eclipse_snr") or 0) >= 5)
rule("reject if class in {C,D} OR sec_snr >= 5",
     lambda s: str(s.get("quality_class") or "").endswith(("C","D")) or
               (s.get("metric_secondary_eclipse_snr") or 0) >= 5)
rule("reject if (n_fail>=1) OR sec_snr >= 5",
     lambda s: (s.get("vetting_n_fail") or 0) >= 1 or
               (s.get("metric_secondary_eclipse_snr") or 0) >= 5)

# sec_depth
rule("reject if class==D OR sec_depth > 100",
     lambda s: str(s.get("quality_class") or "").endswith("D") or
               (s.get("metric_secondary_eclipse_depth_ppm") or 0) > 100)
rule("reject if class==D OR sec_depth > 500",
     lambda s: str(s.get("quality_class") or "").endswith("D") or
               (s.get("metric_secondary_eclipse_depth_ppm") or 0) > 500)

PY

echo
echo "== DONE =="
