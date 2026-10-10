#!/usr/bin/env bash
# FAZ 2b.3a.4-recover: kill stuck processes, resume with per-shard timeouts.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b3a4_recover_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 2b.3a.4-recover =="
echo "log: $LOG"
echo "started: $(date -Iseconds)"

# ---- 1) Kill stuck parents + children ----
echo
echo "########## 1) Kill stuck processes ##########"
pkill -TERM -f "phase2b3a4_fullrun.sh" 2>/dev/null || true
sleep 2
pkill -KILL -f "phase2b3a4_fullrun.sh" 2>/dev/null || true
pkill -KILL -f "run_blind_holdout.py run-shard.*dev-holdout-fixv2" 2>/dev/null || true
sleep 1
echo "--- remaining ---"
ps -eo pid,cmd | grep -E "phase2b3a4|dev-holdout-fixv2" | grep -v grep || echo "  clean"

# ---- 2) Prepare new scratch, copy completed shards ----
echo
echo "########## 2) Prepare new scratch ##########"
OLD=$(cat /tmp/phase2b3a4_scratch 2>/dev/null || echo "")
echo "old scratch: $OLD"
SCRATCH="outputs/dev-holdout-fixv3-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$SCRATCH/shards" "$SCRATCH/logs" "$SCRATCH/out" "$SCRATCH/tmp"
echo "$SCRATCH" > /tmp/phase2b3a4_scratch
echo "new scratch: $SCRATCH"

if [ -n "$OLD" ] && [ -d "$OLD/shards" ]; then
  for f in "$OLD"/shards/shard-*.json; do
    if [ -f "$f" ]; then
      size=$(stat -c%s "$f")
      if [ "$size" -gt 1000 ]; then
        cp "$f" "$SCRATCH/shards/"
        echo "  copied $(basename "$f") ($size bytes)"
      fi
    fi
  done
fi

for i in 0 1 2 3 4 5 6 7 8 9 10 11; do
  mkdir -p "$SCRATCH/out/$i"
  python - "configs/benchmark_fp.toml" "$SCRATCH/out/config-$i.toml" "$SCRATCH/out/$i" "$SCRATCH/tmp/$i" <<'PY'
import sys, toml
src, dst, out_dir, tmp_dir = sys.argv[1:5]
cfg = toml.load(src)
cfg.setdefault("general", {})
cfg["general"]["output_dir"] = out_dir
cfg["general"]["temp_dir"] = tmp_dir
toml.dump(cfg, open(dst, "w"))
PY
done
echo "per-shard configs ready"

# ---- 3) Determine TODO shards ----
echo
echo "########## 3) TODO detection ##########"
TODO=()
for i in 0 1 2 3 4 5 6 7 8 9 10 11; do
  f="$SCRATCH/shards/shard-$(printf '%02d' "$i").json"
  if [ -f "$f" ] && [ "$(stat -c%s "$f")" -gt 1000 ]; then
    echo "  shard-$i: DONE"
  else
    TODO+=("$i")
    echo "  shard-$i: TODO"
  fi
done
echo "TODO: ${TODO[*]:-none}"

# ---- 4) Run with timeout ----
SHARD_TIMEOUT=2400
echo
echo "########## 4) Run TODO shards (3-parallel, ${SHARD_TIMEOUT}s timeout) ##########"

run_shard() {
  local i=$1
  local out="$SCRATCH/shards/shard-$(printf '%02d' "$i").json"
  local log="$SCRATCH/logs/shard-$i.log"
  echo "  [$(date +%H:%M:%S)] shard-$i starting"
  timeout --signal=TERM --kill-after=60s "$SHARD_TIMEOUT" \
    python scripts/validation/run_blind_holdout.py run-shard \
        --manifest validation_runs/final_acceptance_v1/dev_holdout/dev_manifest.json \
        --shard-index "$i" --shard-count 12 \
        --config "$SCRATCH/out/config-$i.toml" --output "$out" \
        > "$log" 2>&1
  local rc=$?
  echo "$rc" > "$SCRATCH/logs/shard-$i.exit"
  if [ "$rc" = "124" ]; then
    echo "  [$(date +%H:%M:%S)] shard-$i TIMEOUT"
  else
    echo "  [$(date +%H:%M:%S)] shard-$i done (exit=$rc)"
  fi
}

START=$(date +%s)
N=${#TODO[@]}
if [ "$N" -gt 0 ]; then
  for ((base=0; base<N; base+=3)); do
    echo
    echo "--- batch: idx $base..$((base+2)) of $N ---"
    for ((k=0; k<3 && base+k<N; k++)); do
      run_shard "${TODO[$((base+k))]}" &
    done
    wait
  done
fi
END=$(date +%s)
echo
echo "total time: $((END-START))s (~$(( (END-START)/60 )) min)"

# ---- 5) Final status ----
echo
echo "########## 5) Final status ##########"
OK=0; MISS=0; TIMEOUT=0
for i in 0 1 2 3 4 5 6 7 8 9 10 11; do
  f="$SCRATCH/shards/shard-$(printf '%02d' "$i").json"
  e="$SCRATCH/logs/shard-$i.exit"
  if [ -f "$f" ] && [ "$(stat -c%s "$f")" -gt 1000 ]; then
    echo "  shard-$i: OK (exit=$(cat "$e" 2>/dev/null))"
    OK=$((OK+1))
  elif [ -f "$e" ] && [ "$(cat "$e")" = "124" ]; then
    echo "  shard-$i: TIMEOUT"
    TIMEOUT=$((TIMEOUT+1))
  else
    echo "  shard-$i: MISSING"
    MISS=$((MISS+1))
  fi
done
echo "  OK=$OK  TIMEOUT=$TIMEOUT  MISSING=$MISS"

echo
echo "== DONE =="
echo "scratch: $SCRATCH"
