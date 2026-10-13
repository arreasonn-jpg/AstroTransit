#!/usr/bin/env bash
S=$(cat /tmp/phase3_scratch 2>/dev/null)
echo "scratch: $S"
echo
printf "%-10s %-10s\n" "shard" "rows"
for i in $(seq 0 19); do
  f="$S/shards/shard-$(printf '%02d' $i).json"
  if [ -f "$f" ]; then
    size=$(stat -c%s "$f")
    python3 -c "
import json
try:
    d = json.load(open('$f'))
    print(f'  shard-$i   rows={d.get(\"case_count\",\"?\")}  ({$size} bytes)')
except Exception:
    print(f'  shard-$i   (partial, {$size} bytes)')
"
  else
    echo "  shard-$i   ..."
  fi
done
echo
echo "=== latest run log ==="
LATEST=$(ls -t ~/phase3_run_*.log | head -1)
tail -10 "$LATEST"
