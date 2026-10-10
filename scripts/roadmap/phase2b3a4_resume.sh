#!/usr/bin/env bash
# FAZ 2b.3a.4-resume: run remaining 9 dev shards with the hardened runner.
# NOTE: kill patterns are deliberately narrow so this script never matches
# itself (see the FAZ 1 `phase2b_resume_v2.sh` incident).
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b3a4_resume_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 2b.3a.4-resume =="
echo "log: $LOG"
echo "started: $(date -Iseconds)"
echo "self PID: $$"

# ---- 1) Kill leftovers (NEVER matches this script) ----
echo
echo "########## 1) Kill leftover workers ##########"
# Only kill python workers and the old *_fullrun / *_recover scripts.
# Do NOT use a pattern that would match our own filename.
SELF=$$
for pid in $(pgrep -f "run_blind_holdout.py run-shard" 2>/dev/null || true); do
  [ "$pid" = "$SELF" ] && continue
  kill -KILL "$pid" 2>/dev/null || true
done
for name in "phase2b3a4_fullrun.sh" "phase2b3a4_recover.sh"; do
  for pid in $(pgrep -f "$name" 2>/dev/null || true); do
    [ "$pid" = "$SELF" ] && continue
    kill -KILL "$pid" 2>/dev/null || true
  done
done
sleep 2
echo "--- remaining ---"
ps -eo pid,cmd | grep -E "run_blind_holdout|phase2b3a4_(fullrun|recover)" | grep -v grep || echo "  clean"

# ---- 2) New scratch ----
echo
echo "########## 2) New scratch ##########"
OLD=$(cat /tmp/phase2b3a4_scratch 2>/dev/null || echo "")
echo "old scratch: $OLD"
SCRATCH="outputs/dev-holdout-fixv4-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$SCRATCH/shards" "$SCRATCH/logs" "$SCRATCH/out" "$SCRATCH/tmp"
echo "$SCRATCH" > /tmp/phase2b3a4_scratch
echo "new scratch: $SCRATCH"

if [ -n "$OLD" ] && [ -d "$OLD/shards" ]; then
  for f in "$OLD"/shards/shard-*.json; do
    if [ -f "$f" ]; then
      size=$(stat -c%s "$f")
      if [ "$size" -gt 5000 ]; then
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
echo "  per-shard configs ready"

# ---- 3) TODO detection ----
echo
echo "########## 3) TODO ##########"
TODO=()
for i in 0 1 2 3 4 5 6 7 8 9 10 11; do
  f="$SCRATCH/shards/shard-$(printf '%02d' "$i").json"
  if [ -f "$f" ] && [ "$(stat -c%s "$f")" -gt 5000 ]; then
    echo "  shard-$i: DONE"
  else
    TODO+=("$i")
    echo "  shard-$i: TODO"
  fi
done
echo "TODO: ${TODO[*]:-none}"

# ---- 4) Run ----
SHARD_TIMEOUT=5400
echo
echo "########## 4) Run (3-parallel, ${SHARD_TIMEOUT}s timeout) ##########"

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
  local rows=""
  [ -f "$out" ] && rows=$(python -c "import json; print(json.load(open('$out')).get('case_count', '?'))" 2>/dev/null || echo '?')
  if [ "$rc" = "124" ]; then
    echo "  [$(date +%H:%M:%S)] shard-$i TIMEOUT (rows=$rows)"
  else
    echo "  [$(date +%H:%M:%S)] shard-$i done (exit=$rc, rows=$rows)"
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
for i in 0 1 2 3 4 5 6 7 8 9 10 11; do
  f="$SCRATCH/shards/shard-$(printf '%02d' "$i").json"
  e="$SCRATCH/logs/shard-$i.exit"
  if [ -f "$f" ]; then
    python -c "
import json
try:
    d = json.load(open('$f'))
    n = d.get('case_count', '?')
    partial = d.get('partial', False)
    print(f'  shard-$i: rows={n} partial={partial} exit=$(cat $e 2>/dev/null || echo ?)')
except Exception as ex:
    print(f'  shard-$i: corrupt ({ex})')
"
  else
    echo "  shard-$i: MISSING"
  fi
done

echo
echo "== DONE =="
echo "scratch: $SCRATCH"
