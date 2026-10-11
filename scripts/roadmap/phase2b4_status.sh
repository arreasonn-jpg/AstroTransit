#!/usr/bin/env bash
S=$(cat /tmp/phase2b4_scratch 2>/dev/null)
echo "scratch: $S"
echo
printf "%-10s %-10s %-10s %-12s\n" "shard" "size" "rows" "mtime"
for i in 0 1 2 3 4 5 6 7 8 9 10 11; do
  f="$S/shards/shard-$(printf '%02d' $i).json"
  if [ -f "$f" ]; then
    size=$(stat -c%s "$f")
    mtime=$(stat -c%y "$f" | cut -d. -f1 | cut -d' ' -f2)
    python3 -c "
import json
try:
    d = json.load(open('$f'))
    print(f'  shard-$i  $size  {d.get(\"case_count\", 0):>3}  $mtime  partial={d.get(\"partial\", False)}')
except Exception as ex:
    print(f'  shard-$i  $size  ?    $mtime  (unreadable: {ex})')
"
  else
    echo "  shard-$i  (missing)"
  fi
done
echo
echo "=== running processes ==="
ps -eo pid,pcpu,etimes,cmd | grep -E "run_blind_holdout" | grep -v grep | awk '{printf "  pid=%s cpu=%s%% elapsed=%ss shard=%s\n", $1, $2, $3, $NF}'
echo
echo "=== last 5 lines of resume log ==="
LATEST=$(ls -t ~/phase2b4_blindv2_*.log | head -1)
tail -5 "$LATEST"
