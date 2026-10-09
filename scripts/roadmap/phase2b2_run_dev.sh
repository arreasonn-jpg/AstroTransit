#!/usr/bin/env bash
# FAZ 2b.2: run the development corpus with the instrumented runner,
# then diagnose leak patterns using per-sector vetting detail.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b2_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== PHASE 2b.2: dev corpus run + diagnose =="
echo "log: $LOG"
echo "started: $(date -Iseconds)"

MANIFEST="validation_runs/final_acceptance_v1/dev_holdout/dev_manifest.json"
CONFIG="configs/benchmark_fp.toml"
SCRATCH="outputs/dev-holdout-v1-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$SCRATCH/shards" "$SCRATCH/logs"
echo "$SCRATCH" > /tmp/phase2b2_dev_scratch
echo "scratch: $SCRATCH"

# ---------- 0) Pre-flight ----------
echo
echo "########## 0) Pre-flight ##########"
[ -f "$MANIFEST" ] || { echo "FATAL: dev manifest missing"; exit 1; }
python -c "import json; d=json.load(open('$MANIFEST')); print(f'  manifest n_cases={len(d[\"cases\"])} split={d.get(\"split\")}')"
echo "  runner help:"
python scripts/validation/run_blind_holdout.py run-shard --help 2>&1 | head -3

# Offline test with dev manifest — must succeed (proves runner accepts it)
echo "  offline test with dev manifest:"
TMP_OFF="$(mktemp -d)/s00.json"
python scripts/validation/run_blind_holdout.py run-shard \
    --manifest "$MANIFEST" --shard-index 0 --shard-count 1 --offline \
    --output "$TMP_OFF" 2>&1 | tail -3
[ -f "$TMP_OFF" ] && echo "  offline OK ($(stat -c%s $TMP_OFF) bytes)" || { echo "  FATAL: offline failed"; exit 1; }

# ---------- 1) Clean outputs ----------
echo
echo "########## 1) Clean outputs ##########"
rm -f outputs/parquet/astrotransit_candidates.parquet outputs/csv/astrotransit_candidates.csv 2>/dev/null || true
for i in 0 1 2 3 4 5 6 7 8 9 10 11; do
  SHARD_TMP="/tmp/dev-shard-$i"
  rm -rf "$SHARD_TMP"; mkdir -p "$SHARD_TMP/outputs" "$SHARD_TMP/tmp"
  python - "$CONFIG" "/tmp/dev-config-$i.toml" "$SHARD_TMP/outputs" "$SHARD_TMP/tmp" <<'PY'
import sys, toml
src, dst, out_dir, tmp_dir = sys.argv[1:5]
cfg = toml.load(src)
cfg.setdefault("general", {})
cfg["general"]["output_dir"] = out_dir
cfg["general"]["temp_dir"] = tmp_dir
toml.dump(cfg, open(dst, "w"))
PY
done
echo "  per-shard configs written"

# ---------- 2) Run shards in batches of 3 ----------
echo
echo "########## 2) Run 12 shards (batches of 3) ##########"
run_shard() {
  local i=$1
  local out="$SCRATCH/shards/shard-$(printf '%02d' "$i").json"
  local log="$SCRATCH/logs/shard-$i.log"
  echo "  [$(date +%H:%M:%S)] shard-$i starting"
  python scripts/validation/run_blind_holdout.py run-shard \
      --manifest "$MANIFEST" --shard-index "$i" --shard-count 12 \
      --config "/tmp/dev-config-$i.toml" --output "$out" \
      > "$log" 2>&1
  echo "$?" > "$SCRATCH/logs/shard-$i.exit"
  echo "  [$(date +%H:%M:%S)] shard-$i done (exit=$(cat $SCRATCH/logs/shard-$i.exit))"
}

START=$(date +%s)
for batch in 0 3 6 9; do
  echo
  echo "--- Batch: shards $batch-$((batch+2)) ---"
  for k in 0 1 2; do run_shard "$((batch+k))" & done
  wait
done
END=$(date +%s)
echo
echo "  total time: $((END-START))s (~$(( (END-START)/60 )) min)"

# ---------- 3) Final status ----------
echo
echo "########## 3) Final shard status ##########"
FAIL=0
for i in 0 1 2 3 4 5 6 7 8 9 10 11; do
  f="$SCRATCH/shards/shard-$(printf '%02d' "$i").json"
  if [ -f "$f" ]; then
    echo "  shard-$i OK ($(stat -c%s "$f") bytes)"
  else
    echo "  shard-$i MISSING"
    FAIL=$((FAIL+1))
  fi
done
[ "$FAIL" -eq 0 ] || echo "  WARNING: $FAIL shards missing"

# ---------- 4) Aggregate ----------
echo
echo "########## 4) Aggregate ##########"
SHARD_FILES=$(ls "$SCRATCH/shards/shard-"?*.json 2>/dev/null | sort)
python scripts/validation/run_blind_holdout.py aggregate \
    --manifest "$MANIFEST" --rows $SHARD_FILES --config "$CONFIG" \
    --output "$SCRATCH/report.json" 2>&1 | tail -40
echo "  aggregate exit=$?"

# ---------- 5) Summary ----------
echo
echo "########## 5) Summary ##########"
if [ -f "$SCRATCH/report.json" ]; then
    python - "$SCRATCH/report.json" <<'PY'
import json, sys
from pathlib import Path
r = json.loads(Path(sys.argv[1]).read_text())
print(f"  status:   {r.get('status')}")
print(f"  data:     {json.dumps(r.get('data', {}), indent=2)}")
print(f"  overall:  {json.dumps(r.get('overall', {}), indent=2)}")
print(f"  strata:")
for name, blk in sorted(r.get('strata', {}).items()):
    print(f"    {name:24s} n={blk.get('n')} recall={blk.get('recall')} fpr={blk.get('false_positive_rate')}")
PY
fi

# ---------- 6) DIAGNOSTIC — per_sector detail ----------
echo
echo "########## 6) DIAGNOSTIC — why FPs leak ##########"
python - "$SCRATCH" <<'PY'
import json, sys
from pathlib import Path
from collections import Counter, defaultdict

scratch = Path(sys.argv[1])
rows = []
for sp in sorted((scratch/"shards").glob("shard-*.json")):
    d = json.loads(sp.read_text())
    rows.extend(d.get("rows", []))

print(f"total rows: {len(rows)}")
print(f"rows with per_sector: {sum(1 for r in rows if 'per_sector' in r)}")
print()

# ---- A) Stratum-level summary using per_sector ----
def target_verdict(r):
    """Reduce per-target to a single verdict string."""
    if r.get("error"):
        return "error"
    if r.get("accepted_candidate"):
        return "accepted"
    if r.get("accepted_candidate") is False:
        return "rejected"
    return "unknown"

by_stratum = defaultdict(lambda: {"n": 0, "accepted": 0, "rejected": 0, "error": 0})
for r in rows:
    s = r.get("stratum", "?")
    v = target_verdict(r)
    by_stratum[s]["n"] += 1
    by_stratum[s][v] += 1

print("=== Per-stratum target verdicts ===")
for s in sorted(by_stratum):
    b = by_stratum[s]
    n = b["n"]
    print(f"  {s:24s} n={n:3d}  accepted={b['accepted']:3d}  rejected={b['rejected']:3d}  error={b['error']:2d}")

# ---- B) For each FP stratum, look at per_sector diagnostics ----
def sector_summary(sec):
    return {
        "class": sec.get("quality_class"),
        "score": sec.get("quality_score"),
        "n_fail": sec.get("vetting_n_fail"),
        "n_warn": sec.get("vetting_n_warn"),
        "n_pass": sec.get("vetting_n_pass"),
        "flags": tuple(sec.get("vetting_fp_flags") or []),
        "fpp": sec.get("vetting_fpp"),
        "is_fp": sec.get("vetting_is_false_positive"),
        "sec_depth": sec.get("metric_secondary_eclipse_depth_ppm"),
        "sec_snr": sec.get("metric_secondary_eclipse_snr"),
        "oe": sec.get("metric_odd_even_mismatch"),
        "oe_h": sec.get("metric_odd_even_harmonic"),
        "shape": sec.get("metric_shape_correlation"),
        "var_amp": sec.get("metric_variability_amplitude_ppm"),
        "ls_peak": sec.get("metric_lomb_scargle_peak"),
    }

print()
print("=== FP:APC accepted targets — what would have rejected them? ===")
apc_acc = [r for r in rows if r.get("stratum") == "false_positive:APC"
           and r.get("accepted_candidate") and not r.get("error")]
print(f"count: {len(apc_acc)}")
print()
flag_counts = Counter()
verdict_by_test = defaultdict(lambda: Counter())
for r in apc_acc:
    for sec in r.get("per_sector", []):
        for f in (sec.get("vetting_fp_flags") or []):
            flag_counts[f] += 1
        for t in (sec.get("vetting_tests") or []):
            verdict_by_test[t["name"]][t["verdict"]] += 1

print("  fp_flags frequency across all sectors of accepted APC:")
for k, v in flag_counts.most_common():
    print(f"    {k:35s} {v}")
print()
print("  per-test verdict counts (accepted APC):")
for name in sorted(verdict_by_test):
    print(f"    {name:35s} {dict(verdict_by_test[name])}")

print()
print("=== FP:FP accepted targets ===")
fp_acc = [r for r in rows if r.get("stratum") == "false_positive:FP"
          and r.get("accepted_candidate") and not r.get("error")]
print(f"count: {len(fp_acc)}")
flag_counts2 = Counter()
for r in fp_acc:
    for sec in r.get("per_sector", []):
        for f in (sec.get("vetting_fp_flags") or []):
            flag_counts2[f] += 1
print("  fp_flags frequency:")
for k, v in flag_counts2.most_common():
    print(f"    {k:35s} {v}")

# ---- C) Rule sweep: which simple rules separate FP from planet? ----
print()
print("=== RULE SWEEP: candidate rules, dev-set impact ===")

def sector_level_records():
    """Flatten to sector-level records with target label."""
    recs = []
    for r in rows:
        if r.get("error"): continue
        label = "planet" if str(r.get("stratum","")).startswith("planet:") else "fp"
        for sec in r.get("per_sector", []):
            recs.append({"label": label, "sec": sec, "target_id": r.get("target_id")})
    return recs

recs = sector_level_records()
print(f"  sector-level records: {len(recs)}")

# Baseline: current behavior
def accept(r):
    return bool(r.get("accepted_candidate"))

# Candidate rules applied at sector level, then re-reduced to target
def apply_rule(rule_fn, name):
    """Rule: reject sector if rule_fn(sec) returns True.
    Target accepted iff ANY sector accepted."""
    tp = fn = fp = tn = 0
    for r in rows:
        if r.get("error"): continue
        label = "planet" if str(r.get("stratum","")).startswith("planet:") else "fp"
        any_ok = False
        for sec in r.get("per_sector", []):
            if not rule_fn(sec):
                any_ok = True
        if label == "planet":
            if any_ok: tp += 1
            else: fn += 1
        else:
            if any_ok: fp += 1
            else: tn += 1
    rec = tp/(tp+fn) if (tp+fn) else 0
    fpr = fp/(fp+tn) if (fp+tn) else 0
    ba = (rec + (1-fpr))/2
    print(f"  {name:55s} TP={tp:3d} FN={fn:3d} FP={fp:3d} TN={tn:3d}  recall={rec:.3f} fpr={fpr:.3f} ba={ba:.3f}")

# Rule 1: reject sector if vetting says is_false_positive
apply_rule(lambda s: bool(s.get("vetting_is_false_positive")), "reject if vetting_is_false_positive")

# Rule 2: reject if n_fail >= 1 (any FAIL)
apply_rule(lambda s: (s.get("vetting_n_fail") or 0) >= 1, "reject if n_fail >= 1")

# Rule 3: reject if n_fail >= 1 AND class is C/D
apply_rule(lambda s: (s.get("vetting_n_fail") or 0) >= 1 and
                     str(s.get("quality_class") or "").endswith(("C","D")),
           "reject if n_fail>=1 AND class in {C,D}")

# Rule 4: reject if secondary_eclipse_depth > 100 ppm
apply_rule(lambda s: (s.get("metric_secondary_eclipse_depth_ppm") or 0) > 100,
           "reject if secondary_eclipse_depth > 100 ppm")

# Rule 5: reject if secondary_eclipse_snr >= 2
apply_rule(lambda s: (s.get("metric_secondary_eclipse_snr") or 0) >= 2,
           "reject if secondary_eclipse_snr >= 2")

# Rule 6: reject if odd_even_mismatch > 3
apply_rule(lambda s: (s.get("metric_odd_even_mismatch") or 0) > 3,
           "reject if odd_even_mismatch > 3")

# Rule 7: reject if shape_correlation < -0.75 (V-shape)
apply_rule(lambda s: (s.get("metric_shape_correlation") or 0) < -0.75,
           "reject if shape_correlation < -0.75")

# Rule 8: reject if LS peak > 0.5
apply_rule(lambda s: (s.get("metric_lomb_scargle_peak") or 0) > 0.5,
           "reject if LS peak > 0.5")

# Rule 9: reject if fpp > 0.4
apply_rule(lambda s: (s.get("vetting_fpp") or 0) > 0.4,
           "reject if vetting_fpp > 0.4")

# Rule 10: reject if class is D
apply_rule(lambda s: str(s.get("quality_class") or "").endswith("D"),
           "reject if class == D")

# Rule 11: reject if class is C or D
apply_rule(lambda s: str(s.get("quality_class") or "").endswith(("C","D")),
           "reject if class in {C,D}")

# Rule 12: reject if is_false_positive OR class D
apply_rule(lambda s: bool(s.get("vetting_is_false_positive")) or
                     str(s.get("quality_class") or "").endswith("D"),
           "reject if is_fp OR class D")
PY

echo
echo "== PHASE 2b.2 DONE =="
echo "finished: $(date -Iseconds)"
echo "scratch: $SCRATCH"
