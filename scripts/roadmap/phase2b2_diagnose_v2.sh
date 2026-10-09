#!/usr/bin/env bash
# FAZ 2b.2 diagnose v2: fix §4 crash, add detection vs classification baselines,
# add more metric columns, and cross-tab tests by label.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase2b2_diag_v2_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 2b.2 DIAGNOSE v2 =="
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

def label_of(r):
    return "planet" if str(r.get("stratum", "")).startswith("planet:") else "fp"

def target_verdict(r):
    if r.get("error"): return "error"
    if r.get("accepted_candidate"): return "accepted"
    if r.get("accepted_candidate") is False: return "rejected"
    return "unknown"

# ---- §1 Per-stratum verdict ----
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
          f"acc={c['accepted']:3d}  rej={c['rejected']:3d}  "
          f"err={c['error']:2d}  accept_rate={rate:.3f}")

# ---- §2 Two baselines: detection vs classification ----
print()
print("=" * 78)
print("2) TWO BASELINES: detection-level vs classification-level")
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
    print(f"  {name:<55s} TP={tp:3d} FN={fn:3d} FP={fp:3d} TN={tn:3d}  "
          f"recall={rec:.3f} fpr={fpr:.3f} ba={ba:.3f}")

# Baseline A: detection = cascade confirmed (what runner uses now)
evaluate("detection-level: accepted iff candidate_confirmed",
         lambda r: bool(r.get("accepted_candidate")))

# Baseline B: classification = cascade confirmed AND NOT vetting is_fp on any sector
def classification_accept(r):
    sectors = r.get("per_sector") or []
    if not sectors:
        return bool(r.get("accepted_candidate"))
    for s in sectors:
        if s.get("candidate_confirmed") and not s.get("vetting_is_false_positive"):
            return True
    return False
evaluate("classification-level: NOT vetting.is_false_positive",
         classification_accept)

# Baseline C: classification-level with n_fail>=2 (STRICT)
def strict_accept(r):
    sectors = r.get("per_sector") or []
    if not sectors:
        return False
    for s in sectors:
        if (s.get("candidate_confirmed")
                and not s.get("vetting_is_false_positive")
                and (s.get("vetting_n_fail") or 0) < 2):
            return True
    return False
evaluate("strict: NOT is_fp AND n_fail < 2",
         strict_accept)

# ---- §3 FP:APC detail (with more columns) ----
print()
print("=" * 78)
print("3) FP:APC accepted — per-sector diagnostic columns")
print("=" * 78)
apc_acc = [r for r in rows if r.get("stratum") == "false_positive:APC"
           and r.get("accepted_candidate") and not r.get("error")]
print(f"count: {len(apc_acc)}")
print()
print(f"  {'target':>10s}  {'cls':>3s}  {'score':>6s}  {'snr':>6s}  "
      f"{'depth_ppm':>9s}  {'sec_dep':>7s}  {'sec_snr':>7s}  "
      f"{'shape_r':>7s}  {'oe':>5s}  {'oe_h':>5s}  {'sym':>5s}  "
      f"{'var_amp':>7s}  {'ls_pk':>5s}  {'nf':>2s}  {'nw':>2s}  {'fpp':>5s}  flags")
for r in apc_acc:
    for sec in r.get("per_sector", []):
        flags = ",".join(sec.get("vetting_fp_flags") or []) or "-"
        print(f"  {r['target_id']:>10s}  {str(sec.get('quality_class')):>3s}  "
              f"{sec.get('quality_score') or 0:6.1f}  "
              f"{sec.get('candidate_snr_adopted') or 0:6.1f}  "
              f"{sec.get('candidate_depth_ppm') or 0:9.0f}  "
              f"{sec.get('metric_secondary_eclipse_depth_ppm') or 0:7.1f}  "
              f"{sec.get('metric_secondary_eclipse_snr') or 0:7.2f}  "
              f"{sec.get('metric_shape_correlation') or 0:7.2f}  "
              f"{sec.get('metric_odd_even_mismatch') or 0:5.2f}  "
              f"{sec.get('metric_odd_even_harmonic') or 0:5.2f}  "
              f"{sec.get('metric_transit_symmetry') or 0:5.2f}  "
              f"{sec.get('metric_variability_amplitude_ppm') or 0:7.0f}  "
              f"{sec.get('metric_lomb_scargle_peak') or 0:5.3f}  "
              f"{sec.get('vetting_n_fail') or 0:2d}  "
              f"{sec.get('vetting_n_warn') or 0:2d}  "
              f"{sec.get('vetting_fpp') or 0:5.3f}  {flags}")

# ---- §4 planet detail (for comparison) ----
print()
print("=" * 78)
print("4) Planet accepted — per-sector diagnostic columns (compare to §3)")
print("=" * 78)
pl_acc = [r for r in rows if label_of(r) == "planet"
          and r.get("accepted_candidate") and not r.get("error")]
print(f"count: {len(pl_acc)}")
print()
print(f"  {'target':>10s}  {'cls':>3s}  {'score':>6s}  {'snr':>6s}  "
      f"{'depth_ppm':>9s}  {'sec_dep':>7s}  {'sec_snr':>7s}  "
      f"{'shape_r':>7s}  {'oe':>5s}  {'oe_h':>5s}  {'sym':>5s}  "
      f"{'var_amp':>7s}  {'ls_pk':>5s}  {'nf':>2s}  {'nw':>2s}  {'fpp':>5s}  flags")
for r in pl_acc[:20]:
    for sec in r.get("per_sector", []):
        flags = ",".join(sec.get("vetting_fp_flags") or []) or "-"
        print(f"  {r['target_id']:>10s}  {str(sec.get('quality_class')):>3s}  "
              f"{sec.get('quality_score') or 0:6.1f}  "
              f"{sec.get('candidate_snr_adopted') or 0:6.1f}  "
              f"{sec.get('candidate_depth_ppm') or 0:9.0f}  "
              f"{sec.get('metric_secondary_eclipse_depth_ppm') or 0:7.1f}  "
              f"{sec.get('metric_secondary_eclipse_snr') or 0:7.2f}  "
              f"{sec.get('metric_shape_correlation') or 0:7.2f}  "
              f"{sec.get('metric_odd_even_mismatch') or 0:5.2f}  "
              f"{sec.get('metric_odd_even_harmonic') or 0:5.2f}  "
              f"{sec.get('metric_transit_symmetry') or 0:5.2f}  "
              f"{sec.get('metric_variability_amplitude_ppm') or 0:7.0f}  "
              f"{sec.get('metric_lomb_scargle_peak') or 0:5.3f}  "
              f"{sec.get('vetting_n_fail') or 0:2d}  "
              f"{sec.get('vetting_n_warn') or 0:2d}  "
              f"{sec.get('vetting_fpp') or 0:5.3f}  {flags}")

# ---- §5 PER-TEST verdict counts (fixed) ----
print()
print("=" * 78)
print("5) PER-TEST VERDICT COUNTS by label")
print("=" * 78)
test_verdicts = defaultdict(lambda: defaultdict(lambda: {"planet": 0, "fp": 0}))
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
        row_str.append(f"{v}=P{c['planet']}/F{c['fp']}")
    print(f"  {name:28s}  " + "  ".join(row_str))

# ---- §6 RULE SWEEP ----
print()
print("=" * 78)
print("6) RULE SWEEP — target-level accept iff ANY sector passes")
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

def baseline(name):
    tp=fn=fp=tn=0
    for r in rows:
        if r.get("error"): continue
        lab = label_of(r)
        accepted = bool(r.get("accepted_candidate"))
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

baseline("[A] detection-level: cascade confirmed")
rule("[B] reject if is_fp", lambda s: bool(s.get("vetting_is_false_positive")))
rule("[C] reject if is_fp OR n_fail>=1", lambda s: bool(s.get("vetting_is_false_positive")) or (s.get("vetting_n_fail") or 0) >= 1)
rule("[D] reject if is_fp OR n_fail>=2", lambda s: bool(s.get("vetting_is_false_positive")) or (s.get("vetting_n_fail") or 0) >= 2)
rule("[E] reject if class==D", lambda s: str(s.get("quality_class") or "").endswith("D"))
rule("[F] reject if class in {C,D}", lambda s: str(s.get("quality_class") or "").endswith(("C","D")))
for thr in (0.05, 0.1, 0.15, 0.2, 0.3):
    rule(f"[G] reject if fpp > {thr}", lambda s, t=thr: (s.get("vetting_fpp") or 0) > t)
rule("[H] reject if sec_snr >= 2", lambda s: (s.get("metric_secondary_eclipse_snr") or 0) >= 2)
rule("[I] reject if sec_depth > 100", lambda s: (s.get("metric_secondary_eclipse_depth_ppm") or 0) > 100)
rule("[J] reject if shape < -0.75", lambda s: (s.get("metric_shape_correlation") or 0) < -0.75)
rule("[K] reject if oe > 3", lambda s: (s.get("metric_odd_even_mismatch") or 0) > 3)
rule("[L] reject if class==D OR n_fail>=1",
     lambda s: str(s.get("quality_class") or "").endswith("D") or (s.get("vetting_n_fail") or 0) >= 1)
rule("[M] reject if class==D OR fpp>0.1",
     lambda s: str(s.get("quality_class") or "").endswith("D") or (s.get("vetting_fpp") or 0) > 0.1)
rule("[N] reject if class==D OR oe>1.5",
     lambda s: str(s.get("quality_class") or "").endswith("D") or (s.get("metric_odd_even_mismatch") or 0) > 1.5)
rule("[O] reject if class==D OR oe_h>0.3",
     lambda s: str(s.get("quality_class") or "").endswith("D") or (s.get("metric_odd_even_harmonic") or 0) > 0.3)
rule("[P] reject if class==D OR shape<-0.5",
     lambda s: str(s.get("quality_class") or "").endswith("D") or (s.get("metric_shape_correlation") or 0) < -0.5)
rule("[Q] reject if class==D OR var_amp>3000",
     lambda s: str(s.get("quality_class") or "").endswith("D") or (s.get("metric_variability_amplitude_ppm") or 0) > 3000)
rule("[R] reject if class==D OR (sec_snr<1 AND depth<2000)",
     lambda s: str(s.get("quality_class") or "").endswith("D") or
               ((s.get("metric_secondary_eclipse_snr") or 0) < 1 and (s.get("candidate_depth_ppm") or 0) < 2000))

print()
print("=" * 78)
print("NOTES")
print("=" * 78)
print("""
- [A] detection-level = current runner semantics (cascade confirmed).
- [B]-[R] show what happens if we add rejection rules on top.
- 'ba' = balanced accuracy = (recall + (1-fpr)) / 2; higher is better.
- No tuning on blind; this is development-side analysis.
""")
PY

echo
echo "== DIAGNOSE v2 DONE =="
