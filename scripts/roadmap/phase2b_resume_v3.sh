#!/usr/bin/env bash
# PHASE 2B RESUME v3: fixed pkill self-kill + per-shard output isolation.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b_resume_v3_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== PHASE 2B RESUME v3 =="
echo "log: $LOG"
echo "started: $(date -Iseconds)"
echo "self PID: $$"

SCRATCH=$(cat /tmp/phase2b_full_scratch)
echo "scratch: $SCRATCH"

MANIFEST="validation_runs/final_acceptance_v1/blind_holdout/holdout_manifest.json"
BASE_CONFIG="configs/benchmark_fp.toml"

# ---- 0) Kill only python run-shard processes (NOT ourselves) ----
echo
echo "########## 0) Kill python run-shard processes only ##########"
SELF=$$
KILLED=0
for pid in $(pgrep -f "run_blind_holdout.py run-shard" 2>/dev/null || true); do
  if [ "$pid" != "$SELF" ]; then
    echo "  killing pid=$pid"
    kill -KILL "$pid" 2>/dev/null && KILLED=$((KILLED+1)) || true
  fi
done
echo "  killed $KILLED processes"
sleep 2

# Also kill the OLD phase2b_full.sh (specific match — will not match v3)
for pid in $(pgrep -f "phase2b_full.sh" 2>/dev/null || true); do
  echo "  killing old phase2b_full.sh pid=$pid"
  kill -KILL "$pid" 2>/dev/null || true
done
sleep 1

echo "--- remaining matching procs ---"
ps -eo pid,cmd | grep -E "run_blind_holdout|phase2b" | grep -v grep | grep -v "phase2b_resume_v3" || echo "  clean"

# ---- 1) Clean leftover parquet (the exit=1 root cause) ----
echo
echo "########## 1) Clean corrupted outputs ##########"
mkdir -p /tmp/broken_outputs_backup
for f in \
  outputs/parquet/astrotransit_candidates.parquet \
  outputs/csv/astrotransit_candidates.csv ; do
  if [ -f "$f" ]; then
    mv "$f" "/tmp/broken_outputs_backup/$(basename $f).$(date +%s)" && echo "  moved $f"
  fi
done
echo "  outputs/parquet/: $(ls outputs/parquet/ 2>/dev/null | wc -l) files"
echo "  outputs/csv/:     $(ls outputs/csv/ 2>/dev/null | wc -l) files"

# ---- 2) Detect missing shards ----
echo
echo "########## 2) Detect missing shards ##########"
TODO=()
for i in 0 1 2 3 4 5 6 7 8 9 10 11; do
  f="$SCRATCH/shards/shard-$(printf '%02d' "$i").json"
  if [ -f "$f" ] && [ "$(stat -c%s "$f")" -gt 100 ]; then
    echo "  shard-$i DONE"
  else
    echo "  shard-$i TODO"
    TODO+=("$i")
  fi
done
echo "todo: ${TODO[*]:-none}"

if [ "${#TODO[@]}" -eq 0 ]; then
  echo "nothing to run — jumping to aggregate"
else
  # ---- 3) Build per-shard config files (output isolation) ----
  echo
  echo "########## 3) Build per-shard config files ##########"
  for i in "${TODO[@]}"; do
    SHARD_TMP="/tmp/blind-shard-$i"
    rm -rf "$SHARD_TMP"; mkdir -p "$SHARD_TMP/outputs" "$SHARD_TMP/tmp"
    OUT="$SHARD_TMP/outputs"
    python - "$BASE_CONFIG" "/tmp/blind-config-$i.toml" "$OUT" "$SHARD_TMP/tmp" <<'PY'
import sys, toml
src, dst, out_dir, tmp_dir = sys.argv[1:5]
cfg = toml.load(src)
cfg.setdefault("general", {})
cfg["general"]["output_dir"] = out_dir
cfg["general"]["temp_dir"]   = tmp_dir
with open(dst, "w") as f:
    toml.dump(cfg, f)
print(f"  wrote {dst} (output_dir={out_dir})")
PY
  done

  # ---- 4) Run in batches of 3, per-shard config ----
  echo
  echo "########## 4) Run TODO shards (batch size 3, isolated outputs) ##########"

  run_shard() {
    local i=$1
    local shard_out="$SCRATCH/shards/shard-$(printf '%02d' "$i").json"
    local shard_log="$SCRATCH/logs/shard-$i.log"

    echo "  [$(date +%H:%M:%S)] shard-$i starting"
    python scripts/validation/run_blind_holdout.py run-shard \
        --manifest "$MANIFEST" \
        --shard-index "$i" \
        --shard-count 12 \
        --config "/tmp/blind-config-$i.toml" \
        --output "$shard_out" \
        > "$shard_log" 2>&1
    local rc=$?
    echo "$rc" > "$SCRATCH/logs/shard-$i.exit"
    echo "  [$(date +%H:%M:%S)] shard-$i done (exit=$rc)"
  }

  N=${#TODO[@]}
  BATCH=3
  START=$(date +%s)
  for ((base=0; base<N; base+=BATCH)); do
    echo
    echo "--- Batch $((base/BATCH + 1)) ---"
    for ((k=0; k<BATCH && base+k<N; k++)); do
      run_shard "${TODO[$((base+k))]}" &
    done
    wait
    echo "  [$(date +%H:%M:%S)] batch done"
  done
  END=$(date +%s)
  echo
  echo "########## Total remaining: $((END-START))s (~$(( (END-START)/60 )) min) ##########"
fi

# ---- 5) Final status ----
echo
echo "########## 5) Final shard status ##########"
for i in 0 1 2 3 4 5 6 7 8 9 10 11; do
  f="$SCRATCH/shards/shard-$(printf '%02d' "$i").json"
  e="$SCRATCH/logs/shard-$i.exit"
  if [ -f "$f" ]; then
    echo "  shard-$i OK ($(stat -c%s "$f") bytes, exit=$(cat $e 2>/dev/null || echo '?'))"
  else
    echo "  shard-$i MISSING"
  fi
done

# ---- 6) Aggregate ----
echo
echo "########## 6) Aggregate ##########"
SHARD_FILES=$(ls "$SCRATCH/shards/shard-"?*.json 2>/dev/null | sort)
echo "  shard files: $(echo "$SHARD_FILES" | wc -l)"

python scripts/validation/run_blind_holdout.py aggregate \
    --manifest "$MANIFEST" \
    --rows $SHARD_FILES \
    --config "$BASE_CONFIG" \
    --output "$SCRATCH/report.json" 2>&1 | tail -60
echo "  aggregate exit=$?"

# ---- 7) Summary ----
echo
echo "########## 7) Summary ##########"
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

    mkdir -p validation_runs/final_acceptance_v1/blind_holdout
    cp "$SCRATCH/report.json" validation_runs/final_acceptance_v1/blind_holdout/report.json
    echo "  copied to validation_runs/.../blind_holdout/report.json"
fi

echo
echo "== PHASE 2B RESUME v3 DONE =="
echo "finished: $(date -Iseconds)"
