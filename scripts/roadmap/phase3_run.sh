#!/usr/bin/env bash
# FAZ 3 run: FP + Quiet campaign locally, 4-parallel batches of 20 shards.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase3_run_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 3 FP+Quiet run =="
echo "log: $LOG"
echo "started: $(date -Iseconds)"
echo "self PID: $$"

SCRATCH="outputs/fp-quiet-v1-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$SCRATCH/shards" "$SCRATCH/logs" "$SCRATCH/out" "$SCRATCH/tmp"
echo "$SCRATCH" > /tmp/phase3_scratch
echo "scratch: $SCRATCH"

CONFIG="configs/benchmark_fp.toml"
LABELLED="benchmarks/corpora/tfop_disposition_corpus_v1.json"
FP_SUBSET="benchmarks/corpora/fp_run_subset_v1.json"
QUIET_POOL="benchmarks/discovery_targets_v4_small_cool_1000_dedup.csv"
PRIOR_HOSTS="validation_runs/v1_injection_recovery/real_noise_v1/input/quiet_hosts.json"

# Per-shard config (isolated outputs)
for i in $(seq 0 19); do
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

run_shard() {
  local i=$1
  local out="$SCRATCH/shards/shard-$(printf '%02d' "$i").json"
  local log="$SCRATCH/logs/shard-$i.log"
  echo "  [$(date +%H:%M:%S)] shard-$i starting"
  timeout --signal=TERM --kill-after=60s 7200 \
    python scripts/validation/run_false_positive_controls.py run-shard \
        --labelled-corpus "$LABELLED" \
        --fp-subset "$FP_SUBSET" \
        --quiet-pool "$QUIET_POOL" \
        --prior-hosts "$PRIOR_HOSTS" \
        --config "$SCRATCH/out/config-$i.toml" \
        --shard-index "$i" --shard-count 20 \
        --output "$out" \
        > "$log" 2>&1
  local rc=$?
  echo "$rc" > "$SCRATCH/logs/shard-$i.exit"
  echo "  [$(date +%H:%M:%S)] shard-$i done (exit=$rc)"
}

START=$(date +%s)
BATCH=4
for base in $(seq 0 $BATCH 19); do
  echo
  echo "--- batch: $base .. $((base+BATCH-1)) ---"
  for ((k=0; k<BATCH && base+k<20; k++)); do
    run_shard "$((base+k))" &
  done
  wait
done
END=$(date +%s)
echo
echo "total: $((END-START))s (~$(( (END-START)/60 )) min)"

echo
echo "########## Aggregate ##########"
python scripts/validation/run_false_positive_controls.py aggregate \
    --shards "$SCRATCH/shards" \
    --shard-count 20 \
    --output "$SCRATCH/report.json" \
    --rows "$SCRATCH/rows.jsonl" 2>&1 | tail -30

echo
echo "########## Summary ##########"
if [ -f "$SCRATCH/report.json" ]; then
  python - "$SCRATCH/report.json" <<'PY'
import json, sys
from pathlib import Path
r = json.loads(Path(sys.argv[1]).read_text())
print(json.dumps(r, indent=2)[:3000])
PY
  mkdir -p validation_runs/final_acceptance_v1/false_positive_controls
  cp "$SCRATCH/report.json" validation_runs/final_acceptance_v1/false_positive_controls/report.json
  echo "  copied to canonical path"
fi

echo
echo "== DONE =="
echo "scratch: $SCRATCH"
