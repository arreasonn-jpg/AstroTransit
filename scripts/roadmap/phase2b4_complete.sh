#!/usr/bin/env bash
# FAZ 2b.4-complete: run only shards 4, 5, 8 sequentially to reach n_evaluated >= 120.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b4_complete_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 2b.4-complete =="
echo "log: $LOG"
echo "started: $(date -Iseconds)"
echo "self PID: $$"

SCRATCH=$(cat /tmp/phase2b4_scratch 2>/dev/null)
echo "scratch: $SCRATCH"

MANIFEST="validation_runs/final_acceptance_v1/blind_holdout/holdout_manifest.json"
CONFIG="configs/benchmark_fp.toml"

# Only shards 4, 5, 8
TODO=(4 5 8)
SHARD_TIMEOUT=10800   # 3 hours per shard (sequential)

run_shard() {
  local i=$1
  local out="$SCRATCH/shards/shard-$(printf '%02d' "$i").json"
  local log="$SCRATCH/logs/shard-$i.log"
  echo "  [$(date +%H:%M:%S)] shard-$i starting (sequential, 3h timeout)"
  timeout --signal=TERM --kill-after=120s "$SHARD_TIMEOUT" \
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
for i in "${TODO[@]}"; do
  run_shard "$i"
done
END=$(date +%s)
echo
echo "total: $((END-START))s (~$(( (END-START)/60 )) min)"

echo
echo "########## Final state ##########"
for i in 0 1 2 3 4 5 6 7 8 9 10 11; do
  f="$SCRATCH/shards/shard-$(printf '%02d' "$i").json"
  [ -f "$f" ] && rows=$(python -c "import json; print(json.load(open('$f')).get('case_count', '?'))" 2>/dev/null || echo "?") || rows="MISSING"
  echo "  shard-$i: rows=$rows"
done

echo
echo "########## Re-aggregate ##########"
SHARD_FILES=$(ls "$SCRATCH/shards/shard-"?*.json 2>/dev/null | sort)
python scripts/validation/run_blind_holdout.py aggregate \
    --manifest "$MANIFEST" \
    --rows $SHARD_FILES \
    --config "$CONFIG" \
    --output "$SCRATCH/report.json" 2>&1 | tail -30

echo
echo "== DONE =="
echo "scratch: $SCRATCH"
