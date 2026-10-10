#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase2b3a4_diag_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== TIMEOUT DIAGNOSTIC =="
echo "log: $LOG"

S=$(cat /tmp/phase2b3a4_scratch)
echo "scratch: $S"

echo
echo "########## 1) Which shards timed out ##########"
for i in 0 1 2 3 4 5 6 7 8 9 10 11; do
  f="$S/shards/shard-$(printf '%02d' $i).json"
  e="$S/logs/shard-$i.exit"
  status="MISSING"
  [ -f "$f" ] && [ "$(stat -c%s $f)" -gt 1000 ] && status="OK"
  [ -f "$e" ] && [ "$(cat $e)" = "124" ] && status="TIMEOUT"
  echo "  shard-$i: $status (exit=$(cat $e 2>/dev/null || echo '?'))"
done

echo
echo "########## 2) How many targets each timed-out shard processed ##########"
for i in 1 2 3 4 5 6 9 10 11; do
  f="$S/logs/shard-$i.log"
  if [ -f "$f" ]; then
    n_pipelines=$(grep -c "TESS Pipeline başlıyor" "$f" 2>/dev/null || echo 0)
    n_completed=$(grep -c "TESS Pipeline tamamlandı" "$f" 2>/dev/null || echo 0)
    n_search=$(grep -c "TESS araması başlatılıyor" "$f" 2>/dev/null || echo 0)
    last_target=$(grep "TESS Pipeline başlıyor" "$f" 2>/dev/null | tail -1 | sed 's/.*— //')
    last_time=$(tail -1 "$f" 2>/dev/null | cut -d' ' -f1-2)
    echo "  shard-$i: pipelines_started=$n_pipelines, completed=$n_completed, searches=$n_search"
    echo "         last target: $last_target"
    echo "         last log line: $last_time"
  fi
done

echo
echo "########## 3) What is the LAST activity in each timed-out shard? ##########"
for i in 1 2 3 4 5 6 9 10 11; do
  f="$S/logs/shard-$i.log"
  if [ -f "$f" ]; then
    echo "  === shard-$i (last 3 lines) ==="
    tail -3 "$f" 2>/dev/null | sed 's/^/    /'
  fi
done

echo
echo "########## 4) Slowest target across all timed-out shards ##########"
python - "$S" <<'PY'
import re, sys
from pathlib import Path
scratch = Path(sys.argv[1])

# For each shard log, find the last "TESS Pipeline başlıyor" timestamp and
# the last log timestamp. The difference shows how long the target's been running.
pat_start = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*TESS Pipeline başlıyor — (TIC \d+)")
pat_any = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")

for i in [1, 2, 3, 4, 5, 6, 9, 10, 11]:
    p = scratch / "logs" / f"shard-{i}.log"
    if not p.exists():
        continue
    lines = p.read_text(errors="ignore").splitlines()
    last_start = None
    last_start_ts = None
    last_ts = None
    for ln in lines:
        m = pat_start.match(ln)
        if m:
            last_start_ts, last_start = m.group(1), m.group(2)
        m2 = pat_any.match(ln)
        if m2:
            last_ts = m2.group(1)
    if last_start_ts and last_ts:
        from datetime import datetime
        t0 = datetime.strptime(last_start_ts, "%Y-%m-%d %H:%M:%S")
        t1 = datetime.strptime(last_ts, "%Y-%m-%d %H:%M:%S")
        mins = (t1 - t0).total_seconds() / 60
        print(f"  shard-{i}: stuck on {last_start} for {mins:.0f} min (last activity {last_ts})")
    else:
        print(f"  shard-{i}: no pipeline start detected")
PY

echo
echo "########## 5) MAST current reachability ##########"
timeout 10 python - <<'PY'
import urllib.request, time
for url in ("https://mast.stsci.edu", "https://mast.stsci.edu/api/v0/invoke"):
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            print(f"  {url}: status={r.status}, elapsed={time.time()-t0:.2f}s")
    except Exception as e:
        print(f"  {url}: FAILED after {time.time()-t0:.2f}s: {type(e).__name__}")
PY

echo
echo "== DONE =="
