#!/usr/bin/env bash
# PHASE 2B: full 12-shard blind holdout run.
# 6 shards in parallel (2 batches), file-only logging.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b_full_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== PHASE 2B FULL =="
echo "log: $LOG"
echo "started: $(date -Iseconds)"

SCRATCH="outputs/blind-holdout-v1-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$SCRATCH/shards" "$SCRATCH/logs"
echo "$SCRATCH" > /tmp/phase2b_full_scratch
echo "scratch: $SCRATCH"

MANIFEST="validation_runs/final_acceptance_v1/blind_holdout/holdout_manifest.json"
CONFIG="configs/benchmark_fp.toml"

# Free RAM before the run (cache + OS page cache)
sync
echo "--- free before ---"
free -h

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

START=$(date +%s)

echo
echo "########## Batch 1: shards 0-5 ##########"
for i in 0 1 2 3 4 5; do
  run_shard "$i" &
done
wait
echo "  [$(date +%H:%M:%S)] batch 1 done"

echo
echo "########## Batch 2: shards 6-11 ##########"
for i in 6 7 8 9 10 11; do
  run_shard "$i" &
done
wait
echo "  [$(date +%H:%M:%S)] batch 2 done"

END=$(date +%s)
echo
echo "########## Total duration: $((END-START))s (~$(( (END-START)/60 )) min) ##########"

echo
echo "########## Per-shard exit codes ##########"
FAIL=0
for i in 0 1 2 3 4 5 6 7 8 9 10 11; do
  ec=$(cat "$SCRATCH/logs/shard-$i.exit" 2>/dev/null || echo "?")
  echo "  shard-$i exit=$ec"
  [ "$ec" != "0" ] && FAIL=$((FAIL+1))
done
echo "  failed shards: $FAIL"

echo
echo "########## Cache state after ##########"
find .cache/astrotransit/tess -type f 2>/dev/null | wc -l | xargs echo "  cache files:"
du -sh .cache/astrotransit/tess 2>/dev/null | xargs echo "  cache size: "

echo
echo "########## Aggregate ##########"
SHARD_FILES=$(ls "$SCRATCH/shards/shard-"?*.json 2>/dev/null | sort)
N_SHARDS=$(echo "$SHARD_FILES" | wc -l)
echo "  shard files found: $N_SHARDS"
if [ "$N_SHARDS" -lt 12 ]; then
  echo "  WARNING: expected 12 shard files, got $N_SHARDS"
fi

mkdir -p validation_runs/final_acceptance_v1/blind_holdout
python scripts/validation/run_blind_holdout.py aggregate \
    --manifest "$MANIFEST" \
    --rows $SHARD_FILES \
    --config "$CONFIG" \
    --output "$SCRATCH/report.json" 2>&1 | tail -60
AGG_EXIT=$?
echo "  aggregate exit=$AGG_EXIT"

echo
echo "########## Summary ##########"
if [ -f "$SCRATCH/report.json" ]; then
    python - "$SCRATCH/report.json" <<'PY'
import json, sys
from pathlib import Path
r = json.loads(Path(sys.argv[1]).read_text())
print(f"  status:   {r.get('status')}")
print(f"  campaign: {r.get('campaign')}")
print(f"  corpus:   {json.dumps(r.get('corpus', {}), indent=2)[:400]}")
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
echo "########## Audit vs program.json ##########"
if [ -f "$SCRATCH/report.json" ]; then
    cp "$SCRATCH/report.json" validation_runs/final_acceptance_v1/blind_holdout/report.json
    python scripts/validation/final_acceptance_audit.py \
        --program validation_runs/final_acceptance_v1/program.json \
        --output "$SCRATCH/program_audit.json" 2>&1 | tail -20
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
fi

echo
echo "== PHASE 2B FULL DONE =="
echo "finished: $(date -Iseconds)"
echo "scratch: $SCRATCH"
