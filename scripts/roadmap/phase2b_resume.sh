#!/usr/bin/env bash
# PHASE 2B RESUME: kill stuck shards, restart with 3-parallel batches.
# Reuses shard files already written; only runs missing shards.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b_resume_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== PHASE 2B RESUME =="
echo "log: $LOG"
echo "started: $(date -Iseconds)"

SCRATCH=$(cat /tmp/phase2b_full_scratch)
echo "scratch: $SCRATCH"

echo
echo "########## 1) Kill stuck processes ##########"
# Kill python run-shard children
pkill -TERM -f "run_blind_holdout.py run-shard" 2>/dev/null || true
# Kill phase2b_full.sh and children
pkill -TERM -f "phase2b_full.sh" 2>/dev/null || true
sleep 3
# Force kill stragglers
pkill -KILL -f "run_blind_holdout.py run-shard" 2>/dev/null || true
pkill -KILL -f "phase2b_full.sh" 2>/dev/null || true
sleep 2

echo "--- remaining python/phase2b procs ---"
ps -eo pid,stat,cmd | grep -E "run_blind_holdout|phase2b_full" | grep -v grep || echo "  none"

echo
echo "########## 2) Detect completed shards ##########"
MANIFEST="validation_runs/final_acceptance_v1/blind_holdout/holdout_manifest.json"
CONFIG="configs/benchmark_fp.toml"
mkdir -p "$SCRATCH/shards" "$SCRATCH/logs"

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

echo
echo "########## 3) Clear partial logs for TODO shards ##########"
for i in "${TODO[@]}"; do
  rm -f "$SCRATCH/logs/shard-$i.log" "$SCRATCH/logs/shard-$i.exit"
done
echo "  cleared"

echo
echo "########## 4) Run TODO shards in batches of 3 ##########"

run_shard() {
  local i=$1
  echo "  [$(date +%H:%M:%S)] shard-$i starting"
  python scripts/validation/run_blind_holdout.py run-shard \
      --manifest "$MANIFEST" \
      --shard-index "$i" \
      --shard-count 12 \
      --config "$CONFIG" \
      --output "$SCRATCH/shards/shard-$(printf '%02d' "$i").json" \
      > "$SCRATCH/logs/shard-$i.log" 2>&1
  local rc=$?
  echo "$rc" > "$SCRATCH/logs/shard-$i.exit"
  echo "  [$(date +%H:%M:%S)] shard-$i done (exit=$rc)"
}

BATCH_SIZE=3
N=${#TODO[@]}
START=$(date +%s)

for ((base=0; base<N; base+=BATCH_SIZE)); do
  echo
  echo "--- Batch $((base/BATCH_SIZE + 1)): TODO[$base..$((base+BATCH_SIZE-1))] ---"
  for ((k=0; k<BATCH_SIZE && base+k<N; k++)); do
    i="${TODO[$((base+k))]}"
    run_shard "$i" &
  done
  wait
  echo "  [$(date +%H:%M:%S)] batch done"
done

END=$(date +%s)
echo
echo "########## Total remaining duration: $((END-START))s (~$(( (END-START)/60 )) min) ##########"

echo
echo "########## 5) Final shard status ##########"
for i in 0 1 2 3 4 5 6 7 8 9 10 11; do
  f="$SCRATCH/shards/shard-$(printf '%02d' "$i").json"
  e="$SCRATCH/logs/shard-$i.exit"
  if [ -f "$f" ]; then
    echo "  shard-$i: DONE ($(stat -c%s "$f") bytes) exit=$(cat $e 2>/dev/null || echo '?')"
  else
    echo "  shard-$i: MISSING"
  fi
done

echo
echo "########## 6) Aggregate ##########"
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
fi

echo
echo "########## 8) Copy report to validation_runs ##########"
if [ -f "$SCRATCH/report.json" ]; then
    mkdir -p validation_runs/final_acceptance_v1/blind_holdout
    cp "$SCRATCH/report.json" validation_runs/final_acceptance_v1/blind_holdout/report.json
    echo "  copied"
fi

echo
echo "== PHASE 2B RESUME DONE =="
echo "finished: $(date -Iseconds)"
