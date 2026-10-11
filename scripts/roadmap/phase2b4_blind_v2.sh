#!/usr/bin/env bash
# FAZ 2b.4: Blind v2 — rerun the 144-target blind corpus with the class
# gate active. Uses the hardened runner (per-target timeout, incremental
# checkpoint, accepted_for_gate()).
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b4_blindv2_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 2b.4: blind v2 =="
echo "log: $LOG"
echo "started: $(date -Iseconds)"
echo "self PID: $$"

# ---- 0) Kill leftovers (narrow patterns) ----
echo
echo "########## 0) Kill leftovers ##########"
SELF=$$
for pid in $(pgrep -f "run_blind_holdout.py run-shard" 2>/dev/null || true); do
  [ "$pid" = "$SELF" ] && continue
  kill -KILL "$pid" 2>/dev/null || true
done
sleep 2
echo "  clean"

# ---- 1) Archive blind v1 report ----
echo
echo "########## 1) Archive blind v1 ##########"
V1_REPORT="validation_runs/final_acceptance_v1/blind_holdout/report.json"
V1_ARCHIVE="validation_runs/final_acceptance_v1/blind_holdout/report_v1.json"
if [ -f "$V1_REPORT" ] && [ ! -f "$V1_ARCHIVE" ]; then
  cp "$V1_REPORT" "$V1_ARCHIVE"
  echo "  archived: $V1_REPORT -> $V1_ARCHIVE"
else
  echo "  (already archived or missing)"
fi

# ---- 2) New scratch ----
echo
echo "########## 2) New scratch ##########"
SCRATCH="outputs/blind-holdout-v2-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$SCRATCH/shards" "$SCRATCH/logs" "$SCRATCH/out" "$SCRATCH/tmp"
echo "$SCRATCH" > /tmp/phase2b4_scratch
echo "scratch: $SCRATCH"

MANIFEST="validation_runs/final_acceptance_v1/blind_holdout/holdout_manifest.json"
CONFIG="configs/benchmark_fp.toml"

for i in 0 1 2 3 4 5 6 7 8 9 10 11; do
  mkdir -p "$SCRATCH/out/$i"
  python - "$CONFIG" "$SCRATCH/out/config-$i.toml" "$SCRATCH/out/$i" "$SCRATCH/tmp/$i" <<'PY'
import sys, toml
src, dst, out_dir, tmp_dir = sys.argv[1:5]
cfg = toml.load(src)
cfg.setdefault("general", {})
cfg["general"]["output_dir"] = out_dir
cfg["general"]["temp_dir"] = tmp_dir
toml.dump(cfg, open(dst, "w"))
PY
done
echo "  per-shard configs ready"

# ---- 3) Run 12 shards, 3-parallel, 90-min shard timeout ----
SHARD_TIMEOUT=5400
echo
echo "########## 3) Run 12 shards (3-parallel, ${SHARD_TIMEOUT}s timeout) ##########"

run_shard() {
  local i=$1
  local out="$SCRATCH/shards/shard-$(printf '%02d' "$i").json"
  local log="$SCRATCH/logs/shard-$i.log"
  echo "  [$(date +%H:%M:%S)] shard-$i starting"
  timeout --signal=TERM --kill-after=60s "$SHARD_TIMEOUT" \
    python scripts/validation/run_blind_holdout.py run-shard \
        --manifest "$MANIFEST" \
        --shard-index "$i" --shard-count 12 \
        --config "$SCRATCH/out/config-$i.toml" \
        --output "$out" \
        > "$log" 2>&1
  local rc=$?
  echo "$rc" > "$SCRATCH/logs/shard-$i.exit"
  local rows=""
  [ -f "$out" ] && rows=$(python -c "import json; print(json.load(open('$out')).get('case_count', '?'))" 2>/dev/null || echo '?')
  if [ "$rc" = "124" ]; then
    echo "  [$(date +%H:%M:%S)] shard-$i TIMEOUT (rows=$rows)"
  else
    echo "  [$(date +%H:%M:%S)] shard-$i done (exit=$rc, rows=$rows)"
  fi
}

START=$(date +%s)
for base in 0 3 6 9; do
  echo
  echo "--- batch: shards $base-$((base+2)) ---"
  for k in 0 1 2; do
    run_shard "$((base+k))" &
  done
  wait
done
END=$(date +%s)
echo
echo "total time: $((END-START))s (~$(( (END-START)/60 )) min)"

# ---- 4) Aggregate ----
echo
echo "########## 4) Aggregate ##########"
SHARD_FILES=$(ls "$SCRATCH/shards/shard-"?*.json 2>/dev/null | sort)
echo "  shard files: $(echo "$SHARD_FILES" | wc -l)"

python scripts/validation/run_blind_holdout.py aggregate \
    --manifest "$MANIFEST" \
    --rows $SHARD_FILES \
    --config "$CONFIG" \
    --output "$SCRATCH/report.json" 2>&1 | tail -40
AGG=$?
echo "  aggregate exit=$AGG"

# ---- 5) Summary ----
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
print(f"  blocking ({len(r.get('blocking_reasons', []))}):")
for b in r.get('blocking_reasons', []):
    print(f"    - {b}")
PY

  # Copy to canonical gate path
  mkdir -p validation_runs/final_acceptance_v1/blind_holdout
  cp "$SCRATCH/report.json" validation_runs/final_acceptance_v1/blind_holdout/report.json
  echo "  copied to canonical gate path"
fi

# ---- 6) Audit ----
echo
echo "########## 6) Audit vs program.json ##########"
python scripts/validation/final_acceptance_audit.py \
    --program validation_runs/final_acceptance_v1/program.json \
    --output "$SCRATCH/program_audit.json" 2>&1 | tail -5

if [ -f "$SCRATCH/program_audit.json" ]; then
  python - "$SCRATCH/program_audit.json" <<'PY'
import json, sys
from pathlib import Path
a = json.loads(Path(sys.argv[1]).read_text())
for g in a.get("gates", []):
    if g["id"] == "blind_domain_holdout":
        print(json.dumps({
            "closed": g.get("closed"),
            "evidence_status": g.get("evidence_status"),
            "acceptance_status": g.get("acceptance_status"),
            "failed_checks": [c["path"] for c in g.get("acceptance_results", []) if not c.get("passed")],
        }, indent=2))
PY
fi

echo
echo "== DONE =="
echo "scratch: $SCRATCH"
