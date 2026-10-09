#!/usr/bin/env bash
# PHASE 2B-PILOT: run 1 shard (12 targets) of the blind holdout to measure
# timing, cache hit rate, and per-target success before the full 12-shard run.
# Logs file-only (no tee) to avoid the FAZ 1A hang.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b_pilot_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== PHASE 2B PILOT =="
echo "log: $LOG"
echo "started: $(date -Iseconds)"

SCRATCH="outputs/blind-holdout-pilot-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$SCRATCH"
echo "$SCRATCH" > /tmp/phase2b_pilot_scratch

echo
echo "########## 0) Cache state before ##########"
CACHE_DIR=".cache/astrotransit/tess"
BEFORE_COUNT=$(find "$CACHE_DIR" -type f 2>/dev/null | wc -l)
BEFORE_BYTES=$(du -sb "$CACHE_DIR" 2>/dev/null | cut -f1)
echo "  cache files: $BEFORE_COUNT"
echo "  cache bytes: $BEFORE_BYTES"

echo
echo "########## 1) Sanity: offline check again ##########"
python scripts/validation/run_blind_holdout.py check 2>&1 | tail -5

echo
echo "########## 2) Run shard 0/12 (12 targets, LIVE — MAST access) ##########"
echo "  started: $(date -Iseconds)"
START=$(date +%s)

# Run in foreground so we see the pipeline output in real time in the log
python scripts/validation/run_blind_holdout.py run-shard \
    --shard-index 0 \
    --shard-count 12 \
    --config configs/benchmark_fp.toml \
    --output "$SCRATCH/shard-00.json"
SHARD_EXIT=$?

END=$(date +%s)
DURATION=$((END-START))
echo "  finished: $(date -Iseconds)"
echo "  exit=$SHARD_EXIT"
echo "  duration=${DURATION}s (~$((DURATION/60)) min)"

echo
echo "########## 3) Cache state after ##########"
AFTER_COUNT=$(find "$CACHE_DIR" -type f 2>/dev/null | wc -l)
AFTER_BYTES=$(du -sb "$CACHE_DIR" 2>/dev/null | cut -f1)
echo "  cache files: $AFTER_COUNT (+$((AFTER_COUNT - BEFORE_COUNT)))"
echo "  cache bytes: $AFTER_BYTES (+$((AFTER_BYTES - BEFORE_BYTES)))"

echo
echo "########## 4) Shard output — outcome distribution ##########"
if [ -f "$SCRATCH/shard-00.json" ]; then
    python - "$SCRATCH/shard-00.json" <<'PY'
import json, sys
from pathlib import Path
from collections import Counter
d = json.loads(Path(sys.argv[1]).read_text())
if isinstance(d, dict):
    rows = d.get("rows") or d.get("cases") or d.get("results") or []
elif isinstance(d, list):
    rows = d
else:
    rows = []
print(f"  rows: {len(rows)}")
print(f"  outcome distribution: {dict(Counter(str(r.get('outcome')) for r in rows))}")
print()
print("  per-row detail (12 targets):")
for r in rows:
    tid = r.get("target_id")
    label = r.get("label")
    stratum = r.get("stratum")
    outcome = r.get("outcome")
    err = r.get("error") or ""
    found = r.get("candidate_found", r.get("detected", "?"))
    print(f"    {tid:12s} {label:14s} {stratum:20s} outcome={outcome:25s} "
          f"found={found} err={err[:60]}")
PY
else
    echo "  FAILED: no shard output at $SCRATCH/shard-00.json"
fi

echo
echo "########## 5) Aggregate pilot ##########"
python scripts/validation/run_blind_holdout.py aggregate \
    --rows "$SCRATCH/shard-00.json" \
    --config configs/benchmark_fp.toml \
    --output "$SCRATCH/report.json" 2>&1 | tail -40
AGG_EXIT=$?
echo "  aggregate exit=$AGG_EXIT"

echo
echo "########## 6) Summary ##########"
if [ -f "$SCRATCH/report.json" ]; then
    python - "$SCRATCH/report.json" <<'PY'
import json, sys
from pathlib import Path
r = json.loads(Path(sys.argv[1]).read_text())
print(f"  status: {r.get('status')}")
print(f"  blocking: {r.get('blocking_reasons')}")
print(f"  data: {json.dumps(r.get('data', {}), indent=2)}")
print(f"  overall: {json.dumps(r.get('overall', {}), indent=2)}")
PY
fi

echo
echo "########## 7) Do we have internet? (MAST reachable) ##########"
timeout 8 python -c "
import urllib.request
try:
    with urllib.request.urlopen('https://mast.stsci.edu', timeout=6) as r:
        print('  MAST reachable, status:', r.status)
except Exception as e:
    print('  MAST unreachable:', type(e).__name__, str(e)[:120])
" || echo "  (timeout or error)"

echo
echo "== PHASE 2B PILOT DONE =="
echo "finished: $(date -Iseconds)"
echo "scratch: $SCRATCH"
