#!/usr/bin/env bash
# PHASE 2B RESUME v2: clean corrupted outputs, then run only missing shards.
# Uses per-shard isolation via env vars so parquet contention does not recur.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b_resume_v2_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== PHASE 2B RESUME v2 =="
echo "log: $LOG"
echo "started: $(date -Iseconds)"

SCRATCH=$(cat /tmp/phase2b_full_scratch)
echo "scratch: $SCRATCH"

MANIFEST="validation_runs/final_acceptance_v1/blind_holdout/holdout_manifest.json"
CONFIG="configs/benchmark_fp.toml"

echo
echo "########## 0) Kill any stragglers ##########"
pkill -KILL -f "run_blind_holdout.py run-shard" 2>/dev/null || true
pkill -KILL -f "phase2b" 2>/dev/null || true
sleep 2
ps -eo pid,cmd | grep -E "run_blind_holdout|phase2b" | grep -v grep || echo "  clean"

echo
echo "########## 1) Clean corrupted output files ##########"
mkdir -p /tmp/broken_outputs_backup
for f in \
  outputs/parquet/astrotransit_candidates.parquet \
  outputs/csv/astrotransit_candidates.csv ; do
  if [ -f "$f" ]; then
    mv "$f" "/tmp/broken_outputs_backup/$(basename $f).$(date +%s)" && echo "  moved $f"
  fi
done
rm -f outputs/json/*.json 2>/dev/null || true
echo "  outputs/parquet/: $(ls outputs/parquet/ 2>/dev/null | wc -l) files"
echo "  outputs/csv/:     $(ls outputs/csv/ 2>/dev/null | wc -l) files"
echo "  outputs/json/:    $(ls outputs/json/ 2>/dev/null | wc -l) files"

echo
echo "########## 2) Detect remaining missing shards ##########"
DONE=()
TODO=()
for i in 0 1 2 3 4 5 6 7 8 9 10 11; do
  f="$SCRATCH/shards/shard-$(printf '%02d' "$i").json"
  if [ -f "$f" ] && [ "$(stat -c%s "$f")" -gt 100 ]; then
    DONE+=("$i")
    echo "  shard-$i DONE ($(stat -c%s "$f") bytes)"
  else
    TODO+=("$i")
    echo "  shard-$i TODO"
  fi
done
echo
echo "done: ${DONE[*]:-none}"
echo "todo: ${TODO[*]:-none}"

if [ "${#TODO[@]}" -eq 0 ]; then
  echo "Nothing to run — jumping to aggregate"
else
  echo
  echo "########## 3) Run TODO shards in batches of 3 ##########"

  run_shard() {
    local i=$1
    local shard_out="$SCRATCH/shards/shard-$(printf '%02d' "$i").json"
    local shard_log="$SCRATCH/logs/shard-$i.log"

    # Per-shard scratch for pipeline outputs — avoids parquet contention.
    local shard_tmp="/tmp/blind-shard-$i-$$"
    rm -rf "$shard_tmp"; mkdir -p "$shard_tmp"

    echo "  [$(date +%H:%M:%S)] shard-$i starting (tmp=$shard_tmp)"
    # Point outputs to a shard-private directory, so no two shards write the same parquet.
    ASTROTRANSIT_OUTPUT_DIR="$shard_tmp/outputs" \
    python scripts/validation/run_blind_holdout.py run-shard \
        --manifest "$MANIFEST" \
        --shard-index "$i" \
        --shard-count 12 \
        --config "$CONFIG" \
        --output "$shard_out" \
        > "$shard_log" 2>&1
    local rc=$?
    echo "$rc" > "$SCRATCH/logs/shard-$i.exit"
    echo "  [$(date +%H:%M:%S)] shard-$i done (exit=$rc)"
    rm -rf "$shard_tmp"
  }

  BATCH_SIZE=3
  N=${#TODO[@]}
  START=$(date +%s)

  for ((base=0; base<N; base+=BATCH_SIZE)); do
    echo
    echo "--- Batch $((base/BATCH_SIZE + 1)) ---"
    for ((k=0; k<BATCH_SIZE && base+k<N; k++)); do
      run_shard "${TODO[$((base+k))]}" &
    done
    wait
    echo "  [$(date +%H:%M:%S)] batch done"
  done

  END=$(date +%s)
  echo
  echo "########## Total remaining duration: $((END-START))s (~$(( (END-START)/60 )) min) ##########"
fi

echo
echo "########## 4) Final shard status ##########"
ALL_OK=1
for i in 0 1 2 3 4 5 6 7 8 9 10 11; do
  f="$SCRATCH/shards/shard-$(printf '%02d' "$i").json"
  e="$SCRATCH/logs/shard-$i.exit"
  if [ -f "$f" ]; then
    echo "  shard-$i: OK ($(stat -c%s "$f") bytes, exit=$(cat $e 2>/dev/null || echo '?'))"
  else
    echo "  shard-$i: MISSING"
    ALL_OK=0
  fi
done

if [ "$ALL_OK" -eq 0 ]; then
  echo
  echo "WARNING: some shards missing — aggregate will still run, gate will show blockers"
fi

echo
echo "########## 5) Aggregate ##########"
SHARD_FILES=$(ls "$SCRATCH/shards/shard-"?*.json 2>/dev/null | sort)
N_SHARDS=$(echo "$SHARD_FILES" | wc -l)
echo "  shard files: $N_SHARDS"

python scripts/validation/run_blind_holdout.py aggregate \
    --manifest "$MANIFEST" \
    --rows $SHARD_FILES \
    --config "$CONFIG" \
    --output "$SCRATCH/report.json" 2>&1 | tail -60
AGG_EXIT=$?
echo "  aggregate exit=$AGG_EXIT"

echo
echo "########## 6) Summary ##########"
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
fi

echo
echo "########## 7) Copy report to validation_runs ##########"
if [ -f "$SCRATCH/report.json" ]; then
    mkdir -p validation_runs/final_acceptance_v1/blind_holdout
    cp "$SCRATCH/report.json" validation_runs/final_acceptance_v1/blind_holdout/report.json
    echo "  copied to validation_runs/final_acceptance_v1/blind_holdout/report.json"
fi

echo
echo "== PHASE 2B RESUME v2 DONE =="
echo "finished: $(date -Iseconds)"
