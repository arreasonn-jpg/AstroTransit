#!/usr/bin/env bash
# FAZ 2b.3a.4: full dev-corpus rerun with the metric fix.
# Batches of 3 shards; per-shard config; file-only logging.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b3a4_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 2b.3a.4: full dev rerun with fix =="
echo "log: $LOG"
echo "started: $(date -Iseconds)"

MANIFEST="validation_runs/final_acceptance_v1/dev_holdout/dev_manifest.json"
CONFIG="configs/benchmark_fp.toml"
SCRATCH="outputs/dev-holdout-fixv2-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$SCRATCH/shards" "$SCRATCH/logs" "$SCRATCH/out" "$SCRATCH/tmp"
echo "$SCRATCH" > /tmp/phase2b3a4_scratch
echo "scratch: $SCRATCH"

# 0) Clean global parquet (deadlock source from before)
rm -f outputs/parquet/astrotransit_candidates.parquet outputs/csv/astrotransit_candidates.csv 2>/dev/null || true

# Per-shard config
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
echo "per-shard configs ready"

# Run shards in batches of 3
run_shard() {
  local i=$1
  local out="$SCRATCH/shards/shard-$(printf '%02d' "$i").json"
  local log="$SCRATCH/logs/shard-$i.log"
  echo "  [$(date +%H:%M:%S)] shard-$i starting"
  python scripts/validation/run_blind_holdout.py run-shard \
      --manifest "$MANIFEST" --shard-index "$i" --shard-count 12 \
      --config "$SCRATCH/out/config-$i.toml" --output "$out" \
      > "$log" 2>&1
  echo "$?" > "$SCRATCH/logs/shard-$i.exit"
  echo "  [$(date +%H:%M:%S)] shard-$i done (exit=$(cat $SCRATCH/logs/shard-$i.exit))"
}

START=$(date +%s)
for base in 0 3 6 9; do
  echo
  echo "--- batch: shards $base-$((base+2)) ---"
  for k in 0 1 2; do run_shard "$((base+k))" & done
  wait
done
END=$(date +%s)
echo
echo "total time: $((END-START))s (~$(( (END-START)/60 )) min)"

echo
echo "== DONE — run diagnose next =="
echo "scratch: $SCRATCH"
