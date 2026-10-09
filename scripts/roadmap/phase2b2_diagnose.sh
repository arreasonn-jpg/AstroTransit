#!/usr/bin/env bash
# FAZ 2b.2 diagnose: what rules would separate FP from planets?
# Works on whatever shards exist, so it can be re-run as data arrives.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase2b2_diag_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 2b.2 DIAGNOSE =="
echo "log: $LOG"

S=$(cat /tmp/phase2b2_dev_scratch)
echo "scratch: $S"

python - "$S" <<'PY'
import json, sys
from pathlib import Path
from collections import Counter, defaultdict

scratch = Path(sys.argv[1])
rows = []
n_shards = 0
for sp in sorted((scratch/"shards").glob("shard-*.json")):
    d = json.loads(sp.read_text())
    rows.extend(d.get("rows", []))
    n_shards += 1
print(f"shards: {n_shards}")
print(f"rows:   {len(rows)}")

# -------- helpers --------
def target_verdict(r):
    if r.get("error"): return "error"
    if r.get("accepted_candidate"): return "accepted"
    if r.get("accepted_candidate") is False: return "rejected"
    return "unknown"

def label_of(r):
    s = str(r.get("stratum", ""))
    return "planet" if s.startswith("planet:") else "fp"

# -------- 1) Per-stratum verdict --------
print()
print("=" * 78)
print("1) PER-STRATUM VERDICT (all available shards)")
print("=" * 78)
bs = defaultdict(lambda: Counter())
for r in rows:
    bs[r.get("stratum", "?")][target_verdict(r)] += 1
for s in sorted(bs):
    c = bs[s]
    n_eval = c["accepted"] + c["rejected"]
    rate = c["accepted"]/n_eval if n_eval else 0
    print(f"  {s:24s}  n={sum(c.values()):3d}  eval={n_eval:3d}  "
          f"accepted={c['accepted']:3d}  rejected={c['rejected']:3d}  "
          f"error={c['error']:2d}  accept_rate={rate:.3f}")

# -------- 2) FP_APC detail: what does the vetting do for accepted? --------
print()
print("=" * 78)
print("2) FP:APC — accepted (leaked) targets, per-sector vetting summary")
print("=" * 78)
apc_acc = [r for r in rows if r.get("stratum") == "false_positive:APC"
           and r.get("accepted_candidate") and not r.get("error")]
print(f"count: {len(apc_acc)}")
print()
print(f"  {'target':>10s}  {'class':>3s}  {'score':>6s}  "
      f"{'n_fail':>6s}  {'n_warn':>6s}  {'fpp':>6s}  {'sec_snr':>7s}  "
      f"{'shape_r':>7s}  {'oe':>5s}  {'ls_pk':>6s}  flags")
for r in apc_acc:
    for sec in r.get("per_sector", []):
        flags = ",".join(sec.get("vetting_fp_flags") or []) or "-"
        print(f"  {r['target_id']:>10s}  {str(sec.get('quality_class')):>3s}  "
              f"{sec.get('quality_score') or 0:6.1f}  "
              f"{sec.get('vetting_n_fail') or 0:6d}  "
              f"{sec.get('vetting_n_warn') or 0:6d}  "
              f"{sec.get('vetting_fpp') or 0:6.3f}  "
              f"{sec.get('metric_secondary_eclipse_snr') or 0:7.2f}  "
              f"{sec.get('metric_shape_correlation') or 0:7.2f}  "
              f"{sec.get('metric_odd_even_mismatch') or 0:5.2f}  "
              f"{sec.get('metric_lomb_scargle_peak') or 0:6.3f}  "
              f"{flags}")

# -------- 3) Same for FP:FP accepted --------
print()
print("=" * 78)
print("3) FP:FP — accepted (leaked) targets")
print("=" * 78)
fp_acc = [r for r in rows if r.get("stratum") == "false_positive:FP"
          and r.get("accepted_candidate") and not r.get("error")]
print(f"count: {len(fp_acc)}")
print()
for r in fp_acc[:20]:
    for sec in r.get("per_sector", []):
        flags = ",".join(sec.get("vetting_fp_flags") or []) or "-"
        print(f"  {r['target_id']:>10s}  cls={str(sec.get('quality_class')):>2s}  "
              f"score={sec.get('quality_score') or 0:6.1f}  "
              f"n_fail={sec.get('vetting_n_fail') or 0:2d}  "
              f"fpp={sec.get('vetting_fpp') or 0:6.3f}  "
              f"sec_snr={sec.get('metric_secondary_eclipse_snr') or 0:5.2f}  "
              f"shape={sec.get('metric_shape_correlation') or 0:6.2f}  "
              f"flags={flags}")

# -------- 4) Per-test verdict counts by stratum --------
print()
print("=" * 78)
print("4) PER-TEST VERDICT COUNTS by label (planet vs fp)")
print("=" * 78)
test_verdicts = defaultdict(lambda: defaultdict(lambda: {"planet": Counter(), "fp": Counter()}))
for r in rows:
    if r.get("error"): continue
    lab = label_of(r)
    for sec in r.get("per_sector", []):
        for t in (sec.get("vetting_tests") or []):
            name = t.get("name", "?")
            v = t.get("verdict", "?")
            test_verdicts[name][v][lab] += 1

all_tests = sorted(test_verdicts)
for name in all_tests:
    per_v = test_verdicts[name]
    row_str = []
    for v in ("pass", "warn", "fail", "skip"):
        c = per_v[v]
        row_str.append(f"{v}:P{c['planet']}/F{c['fp']}")
    print(f"  {name:32s}  " + "  ".join(row_str))

# -------- 5) RULE SWEEP --------
print()
print("=" * 78)
print("5) RULE SWEEP — target-level accept iff ANY sector passes the rule")
print("=" * 78)
print(f"  {'rule':<55s} {'TP':>3s} {'FN':>3s} {'FP':>3s} {'TN':>3s}  "
      f"{'recall':>7s} {'fpr':>6s} {'bal_acc':>8s}")

def apply_rule(reject_fn, name):
    tp = fn = fp = tn = 0
    for r in rows:
        if r.get("error"): continue
        lab = label_of(r)
        sectors = r.get("per_sector") or []
        if not sectors:
            # No sector info -> current behavior: accepted iff accepted_candidate
            accepted = bool(r.get("accepted_candidate"))
        else:
            accepted = any(not reject_fn(s) for s in sectors)
        if lab == "planet":
            (tp if accepted else fn).__class__  # noop
            if accepted: tp += 1
            else: fn += 1
        else:
            if accepted: fp += 1
            else: tn += 1
    rec = tp/(tp+fn) if (tp+fn) else 0
    fpr = fp/(fp+tn) if (fp+tn) else 0
    ba = (rec + (1-fpr))/2
    print(f"  {name:<55s} {tp:3d} {fn:3d} {fp:3d} {tn:3d}  "
          f"{rec:7.3f} {fpr:6.3f} {ba:8.3f}")

# 0) Baseline = current behaviour
def baseline_reject(sec):
    # current: reject iff vetting says is_false_positive (in practice)
    # but we don't know the current rule from sec alone, so use the recorded
    # outcome instead. We'll do this differently: pass baseline as current.
    return False  # "never reject" == accept all sectors -> any() always true

# Special baseline: use recorded accepted_candidate
def baseline_rule(name="current (recorded accepted_candidate)"):
    tp=fn=fp=tn=0
    for r in rows:
        if r.get("error"): continue
        lab = label_of(r)
        accepted = bool(r.get("accepted_candidate"))
        if lab == "planet":
            (tp if accepted else fn)
            if accepted: tp+=1
            else: fn+=1
        else:
            if accepted: fp+=1
            else: tn+=1
    rec = tp/(tp+fn) if (tp+fn) else 0
    fpr = fp/(fp+tn) if (fp+tn) else 0
    ba = (rec + (1-fpr))/2
    print(f"  {name:<55s} {tp:3d} {fn:3d} {fp:3d} {tn:3d}  "
          f"{rec:7.3f} {fpr:6.3f} {ba:8.3f}")

baseline_rule()

# Rule: reject if vetting_is_false_positive
apply_rule(lambda s: bool(s.get("vetting_is_false_positive")),
           "reject sector if vetting_is_false_positive")

# Rule: reject if n_fail >= 1
apply_rule(lambda s: (s.get("vetting_n_fail") or 0) >= 1,
           "reject sector if n_fail >= 1")

# Rule: reject if n_fail >= 2
apply_rule(lambda s: (s.get("vetting_n_fail") or 0) >= 2,
           "reject sector if n_fail >= 2")

# Rule: reject if class == D
apply_rule(lambda s: str(s.get("quality_class") or "").endswith("D"),
           "reject sector if class == D")

# Rule: reject if class in {C, D}
apply_rule(lambda s: str(s.get("quality_class") or "").endswith(("C","D")),
           "reject sector if class in {C, D}")

# Rule: reject if fpp > 0.2 / 0.3 / 0.4
for thr in (0.15, 0.2, 0.3, 0.4, 0.5):
    apply_rule(lambda s, t=thr: (s.get("vetting_fpp") or 0) > t,
               f"reject sector if fpp > {thr}")

# Rule: reject if secondary_eclipse_snr >= 2
apply_rule(lambda s: (s.get("metric_secondary_eclipse_snr") or 0) >= 2,
           "reject sector if sec_ecl_snr >= 2")

# Rule: reject if secondary_eclipse_depth > 100 ppm
apply_rule(lambda s: (s.get("metric_secondary_eclipse_depth_ppm") or 0) > 100,
           "reject sector if sec_ecl_depth > 100 ppm")

# Rule: reject if odd_even_mismatch > 3
apply_rule(lambda s: (s.get("metric_odd_even_mismatch") or 0) > 3,
           "reject sector if odd_even > 3")

# Rule: reject if shape_correlation < -0.75
apply_rule(lambda s: (s.get("metric_shape_correlation") or 0) < -0.75,
           "reject sector if shape_corr < -0.75")

# Rule: reject if LS peak > 0.5
apply_rule(lambda s: (s.get("metric_lomb_scargle_peak") or 0) > 0.5,
           "reject sector if LS peak > 0.5")

# Combination: reject if n_fail >= 1 OR fpp > 0.3
apply_rule(lambda s: ((s.get("vetting_n_fail") or 0) >= 1) or ((s.get("vetting_fpp") or 0) > 0.3),
           "reject sector if n_fail>=1 OR fpp>0.3")

# Combination: reject if class D OR fpp > 0.3
apply_rule(lambda s: str(s.get("quality_class") or "").endswith("D") or ((s.get("vetting_fpp") or 0) > 0.3),
           "reject sector if class==D OR fpp>0.3")

# Combination: reject if class D OR (n_fail>=1)
apply_rule(lambda s: str(s.get("quality_class") or "").endswith("D") or ((s.get("vetting_n_fail") or 0) >= 1),
           "reject sector if class==D OR n_fail>=1")

# Combination: reject if class in {C,D} OR n_fail>=1
apply_rule(lambda s: str(s.get("quality_class") or "").endswith(("C","D")) or ((s.get("vetting_n_fail") or 0) >= 1),
           "reject sector if class in {C,D} OR n_fail>=1")

# Combination: reject if class D OR (n_fail>=1 AND fpp>0.2)
apply_rule(lambda s: str(s.get("quality_class") or "").endswith("D") or
                     ((s.get("vetting_n_fail") or 0) >= 1 and (s.get("vetting_fpp") or 0) > 0.2),
           "reject if class==D OR (n_fail>=1 AND fpp>0.2)")

# Combination: class D OR n_fail>=2
apply_rule(lambda s: str(s.get("quality_class") or "").endswith("D") or ((s.get("vetting_n_fail") or 0) >= 2),
           "reject if class==D OR n_fail>=2")

# Combination: class D OR fpp>0.25
apply_rule(lambda s: str(s.get("quality_class") or "").endswith("D") or ((s.get("vetting_fpp") or 0) > 0.25),
           "reject if class==D OR fpp>0.25")

# Rule: reject if class D AND fpp>0.3
apply_rule(lambda s: str(s.get("quality_class") or "").endswith("D") and ((s.get("vetting_fpp") or 0) > 0.3),
           "reject if class==D AND fpp>0.3")

print()
print("=" * 78)
print("NOTES")
print("=" * 78)
print("""
- 'current' = recorded accepted_candidate (the pipeline as-is).
- 'TP' = planet correctly accepted, 'TN' = fp correctly rejected.
- 'bal_acc' = (recall + (1-fpr)) / 2. Higher is better; 1.0 is perfect.
- All rules are target-level: accept target iff ANY sector passes.
- No tuning on blind; this is development-side analysis.
""")
PY

echo
echo "== DIAGNOSE DONE =="
