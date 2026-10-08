#!/usr/bin/env bash
# Non-destructive diagnostic. Run in a SEPARATE terminal while phase1a_regen.sh
# is still running (or hung). Read-only.

set -uo pipefail

echo "========== 1) Python processes (CPU-time, stat, wchan) =========="
ps -eo pid,ppid,stat,etimes,time,pcpu,pmem,wchan:24,cmd \
   | awk 'NR==1 || /run_adversarial_fp_controls|run-shard|astrotransit/'
echo

echo "========== 2) Process tree =========="
if command -v pstree >/dev/null 2>&1; then
  pstree -p -a 2>/dev/null | grep -i -E "regen|adversarial|run-shard" | head -30 || true
fi
echo

echo "========== 3) Newest scratch dir =========="
SCRATCH=$(ls -td ~/AstroTransit/outputs/adv-fp-regen-* 2>/dev/null | head -1 || true)
echo "scratch: $SCRATCH"
if [ -n "$SCRATCH" ]; then
  echo
  echo "--- shards/ contents ---"
  ls -la "$SCRATCH/shards/" 2>/dev/null || echo "(no shards dir)"
  echo
  echo "--- logs/ contents ---"
  ls -la "$SCRATCH/logs/" 2>/dev/null || echo "(no logs dir)"
  echo
  echo "--- per-shard exit codes ---"
  for i in 0 1 2 3 4 5 6 7; do
    f="$SCRATCH/logs/shard-$i.exit"
    [ -f "$f" ] && echo "  shard-$i exit=$(cat "$f")" || echo "  shard-$i exit=(none)"
  done
  echo
  echo "--- tail of each shard log (10 lines) ---"
  for i in 0 1 2 3 4 5 6 7; do
    f="$SCRATCH/logs/shard-$i.log"
    if [ -f "$f" ]; then
      echo "===== shard-$i (size=$(wc -c <"$f") bytes) ====="
      tail -10 "$f" || true
    else
      echo "===== shard-$i (no log) ====="
    fi
  done
fi
echo

echo "========== 4) Open FDs of any hung python (first live PID) =========="
PID=$(pgrep -f "run_adversarial_fp_controls" | head -1 || true)
echo "first PID: ${PID:-none}"
if [ -n "${PID:-}" ]; then
  echo "--- /proc/$PID/status (state + threads) ---"
  grep -E "^(State|Threads|VmRSS)" /proc/"$PID"/status 2>/dev/null || true
  echo "--- /proc/$PID/wchan (kernel wait channel) ---"
  cat /proc/"$PID"/wchan 2>/dev/null || true
  echo
  echo "--- last 20 lines of /proc/$PID/stack (if permitted) ---"
  sudo -n cat /proc/"$PID"/stack 2>/dev/null | tail -20 || echo "  (no permission or not available)"
  echo
  echo "--- open network connections for this PID ---"
  (command -v ss >/dev/null 2>&1 && ss -tanp 2>/dev/null | grep "pid=$PID" ) || echo "  (ss not available or no sockets)"
fi
echo

echo "========== 5) System load + top CPU =========="
uptime
echo
ps -eo pid,pcpu,pmem,etimes,cmd --sort=-pcpu | head -12
echo

echo "========== 6) Disk / I/O wait =========="
(command -v iostat >/dev/null 2>&1 && iostat -x 1 2 | tail -20) || \
  (cat /proc/loadavg; echo; vmstat 1 2 | tail -4)
echo

echo "========== 7) Recent dmesg (OOM / hung task) =========="
(dmesg 2>/dev/null | tail -30) || (sudo -n dmesg 2>/dev/null | tail -30) || echo "  (dmesg not accessible)"
echo
echo "========== DONE =========="
