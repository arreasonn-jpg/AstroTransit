#!/usr/bin/env bash
# FAZ 2b.3a.3: rerun dev corpus shard 0 with the metric fix, verify that
# secondary_eclipse_snr is now nonzero on real TESS data.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b3a3_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 2b.3a.3: verify metric fix on real TESS =="
echo "log: $LOG"
echo "started: $(date -Iseconds)"

# ---- 0) Small commit for the leftover fixlint scripts ----
echo
echo "########## 0) Commit leftover fixlint scripts ##########"
GITID=(-c user.email="validation@astrotransit.local" -c user.name="AstroTransit Validation")
git add scripts/roadmap/phase2b3a2_fixlint*.sh
if git status --short | grep -q "scripts/roadmap/phase2b3a2_fixlint"; then
    git "${GITID[@]}" commit -m "chore(roadmap): track fixlint helper scripts" || echo "  (nothing to commit)"
fi
git --no-pager log -1 --format="%h %s"

# ---- 1) Sanity check on metrics fix ----
echo
echo "########## 1) Sanity check: _dip_amplitude behavior ##########"
python - <<'PY'
import numpy as np
from astrotransit.quality.metrics import QualityMetricsCalculator

# Shallow TESS-like case
rng = np.random.default_rng(42)
n = 100
flux = 1.0 + rng.normal(0, 3000e-6, n)
m = np.zeros(n, dtype=bool); m[10:24] = True
o = np.zeros(n, dtype=bool); o[30:90] = True
flux[m] -= 2000e-6
depth, se = QualityMetricsCalculator._dip_amplitude(flux, m, o)
z = depth / se if se > 0 else 0
print(f"  shallow case: depth={depth*1e6:.1f} ppm, SE={se*1e6:.1f} ppm, z={z:.2f}")
assert z > 1.0, "fix not applied — z should be > 1"
print("  fix verified in metrics.py")
PY

# ---- 2) Check state of prior dev run ----
echo
echo "########## 2) State of prior dev run ##########"
OLD_SCRATCH=$(cat /tmp/phase2b2_dev_scratch 2>/dev/null || echo "")
echo "old scratch: $OLD_SCRATCH"
if [ -n "$OLD_SCRATCH" ] && [ -d "$OLD_SCRATCH" ]; then
    echo "  prior shards:"
    ls -la "$OLD_SCRATCH/shards/" 2>/dev/null || true
fi

# ---- 3) Prepare fresh run dir ----
echo
echo "########## 3) Fresh run dir ##########"
SCRATCH="outputs/dev-holdout-fixv1-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$SCRATCH/shards" "$SCRATCH/logs" "$SCRATCH/out" "$SCRATCH/tmp"
echo "$SCRATCH" > /tmp/phase2b3a3_scratch
echo "scratch: $SCRATCH"

# Per-shard config for isolation
python - configs/benchmark_fp.toml "$SCRATCH/out/config-0.toml" "$SCRATCH/out" "$SCRATCH/tmp" <<'PY'
import sys, toml
src, dst, out_dir, tmp_dir = sys.argv[1:5]
cfg = toml.load(src)
cfg.setdefault("general", {})
cfg["general"]["output_dir"] = out_dir
cfg["general"]["temp_dir"] = tmp_dir
toml.dump(cfg, open(dst, "w"))
print(f"  config: {dst}")
PY

# ---- 4) Run shard 0 ----
echo
echo "########## 4) Run shard 0/12 (12 targets) ##########"
echo "  started: $(date -Iseconds)"
START=$(date +%s)

python scripts/validation/run_blind_holdout.py run-shard \
    --manifest validation_runs/final_acceptance_v1/dev_holdout/dev_manifest.json \
    --shard-index 0 --shard-count 12 \
    --config "$SCRATCH/out/config-0.toml" \
    --output "$SCRATCH/shards/shard-00.json" \
    > "$SCRATCH/logs/shard-0.log" 2>&1
RC=$?

END=$(date +%s)
echo "  done: $(date -Iseconds)"
echo "  exit=$RC, elapsed=$((END-START))s (~$(( (END-START)/60 )) min)"

# ---- 5) Verify sec_snr is nonzero now ----
echo
echo "########## 5) Verification: sec_snr in new shard ##########"
if [ -f "$SCRATCH/shards/shard-00.json" ]; then
    python - "$SCRATCH/shards/shard-00.json" <<'PY'
import json, sys
from pathlib import Path
d = json.loads(Path(sys.argv[1]).read_text())
rows = d.get("rows", [])
print(f"  rows: {len(rows)}")
print()
print(f"  {'target':>10s}  {'stratum':24s}  {'accepted':>8s}  "
      f"{'class':>3s}  {'score':>6s}  {'sec_snr':>8s}  {'sec_dep':>8s}  "
      f"{'shape':>6s}  {'ls_pk':>6s}  {'n_fail':>5s}  flags")
nonzero_sec = 0
for r in rows:
    if r.get("error"):
        print(f"  {r['target_id']:>10s}  error: {r['error'][:60]}")
        continue
    for sec in r.get("per_sector", []):
        sec_snr = sec.get("metric_secondary_eclipse_snr") or 0.0
        if sec_snr > 0:
            nonzero_sec += 1
        flags = ",".join(sec.get("vetting_fp_flags") or []) or "-"
        print(f"  {r['target_id']:>10s}  {r.get('stratum',''):24s}  "
              f"{str(bool(r.get('accepted_candidate'))):>8s}  "
              f"{str(sec.get('quality_class','')):>3s}  "
              f"{sec.get('quality_score') or 0:6.1f}  "
              f"{sec_snr:8.3f}  "
              f"{sec.get('metric_secondary_eclipse_depth_ppm') or 0:8.1f}  "
              f"{sec.get('metric_shape_correlation') or 0:6.2f}  "
              f"{sec.get('metric_lomb_scargle_peak') or 0:6.3f}  "
              f"{sec.get('vetting_n_fail') or 0:5d}  {flags}")
print()
print(f"  sectors with sec_snr > 0: {nonzero_sec}")
if nonzero_sec > 0:
    print("  ✅ FIX VERIFIED on real TESS: sec_snr is now nonzero")
else:
    print("  ❌ sec_snr still zero everywhere — need further investigation")
PY
else
    echo "  shard-00.json missing"
    echo "  --- log tail ---"
    tail -30 "$SCRATCH/logs/shard-0.log"
fi

# ---- 6) Compare old vs new sec_snr for the same targets ----
echo
echo "########## 6) Compare old (pre-fix) vs new (post-fix) ##########"
OLD_SCRATCH=$(cat /tmp/phase2b2_dev_scratch 2>/dev/null || echo "")
if [ -n "$OLD_SCRATCH" ] && [ -f "$OLD_SCRATCH/shards/shard-00.json" ] && [ -f "$SCRATCH/shards/shard-00.json" ]; then
    python - "$OLD_SCRATCH/shards/shard-00.json" "$SCRATCH/shards/shard-00.json" <<'PY'
import json, sys
from pathlib import Path
old = json.loads(Path(sys.argv[1]).read_text()).get("rows", [])
new = json.loads(Path(sys.argv[2]).read_text()).get("rows", [])
old_by_id = {r["target_id"]: r for r in old}
new_by_id = {r["target_id"]: r for r in new}
print(f"  {'target':>10s}  {'stratum':24s}  {'old_sec':>8s}  {'new_sec':>8s}  {'delta':>8s}")
for tid in sorted(set(old_by_id) & set(new_by_id)):
    old_r = old_by_id[tid]
    new_r = new_by_id[tid]
    old_sec = (old_r.get("per_sector") or [{}])[0].get("metric_secondary_eclipse_snr") or 0.0
    new_sec = (new_r.get("per_sector") or [{}])[0].get("metric_secondary_eclipse_snr") or 0.0
    delta = new_sec - old_sec
    print(f"  {tid:>10s}  {new_r.get('stratum',''):24s}  "
          f"{old_sec:8.3f}  {new_sec:8.3f}  {delta:+8.3f}")
PY
else
    echo "  (old or new shard missing; skipping comparison)"
fi

echo
echo "== FAZ 2b.3a.3 DONE =="
echo "finished: $(date -Iseconds)"
echo "scratch: $SCRATCH"
