#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase3_resume_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 3 resume =="
echo "started: $(date -Iseconds)"

OLD="outputs/fp-quiet-v1-20261014_150405"
NEW="outputs/fp-quiet-v1-resume-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$NEW/shards" "$NEW/logs" "$NEW/out" "$NEW/tmp"
echo "$NEW" > /tmp/phase3_scratch
echo "new scratch: $NEW"

for i in 00 04 05 06; do
  cp "$OLD/shards/shard-$i.json" "$NEW/shards/"
done
echo "copied 4 complete shards"

for i in $(seq 0 19); do
  mkdir -p "$NEW/out/$i"
  python - "configs/benchmark_fp.toml" "$NEW/out/config-$i.toml" "$NEW/out/$i" "$NEW/tmp/$i" <<'PY'
import sys, toml
src, dst, out_dir, tmp_dir = sys.argv[1:5]
cfg = toml.load(src)
cfg.setdefault("general", {})
cfg["general"]["output_dir"] = out_dir
cfg["general"]["temp_dir"] = tmp_dir
toml.dump(cfg, open(dst, "w"))
PY
done
echo "configs ready"

TODO=(1 2 3 7 8 9 10 11 12 13 14 15 16 17 18 19)
echo "TODO: ${TODO[*]}"

run_shard() {
  local i=$1
  local out="$NEW/shards/shard-$(printf '%02d' "$i").json"
  local log="$NEW/logs/shard-$i.log"
  echo "  [$(date +%H:%M:%S)] shard-$i starting"
  timeout --signal=TERM --kill-after=60s 5400 \
    python scripts/validation/run_false_positive_controls.py run-shard \
        --labelled-corpus benchmarks/corpora/tfop_disposition_corpus_v1.json \
        --fp-subset benchmarks/corpora/fp_run_subset_v1.json \
        --quiet-pool benchmarks/discovery_targets_v4_small_cool_1000_dedup.csv \
        --prior-hosts validation_runs/v1_injection_recovery/real_noise_v1/input/quiet_hosts.json \
        --config "$NEW/out/config-$i.toml" \
        --shard-index "$i" --shard-count 20 \
        --output "$out" \
        > "$log" 2>&1
  local rc=$?
  echo "$rc" > "$NEW/logs/shard-$i.exit"
  local n=""
  [ -f "$out" ] && n=$(python -c "import json; print(json.load(open('$out')).get('case_count', '?'))" 2>/dev/null || echo '?')
  echo "  [$(date +%H:%M:%S)] shard-$i done (exit=$rc, rows=$n)"
}

START=$(date +%s)
N=${#TODO[@]}
for ((base=0; base<N; base+=4)); do
  echo "--- batch: idx $base..$((base+3)) of $N ---"
  for ((k=0; k<4 && base+k<N; k++)); do
    run_shard "${TODO[$((base+k))]}" &
  done
  wait
done
END=$(date +%s)
echo "total: $((END-START))s (~$(( (END-START)/60 )) min)"
echo "== DONE =="
echo "scratch: $NEW"
