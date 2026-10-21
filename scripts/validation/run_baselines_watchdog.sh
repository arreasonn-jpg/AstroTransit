#!/usr/bin/env bash
# Baselines koşucusu için v5 watchdog: KALP ATIŞI temelli.
# v4 faciasının protokolü: cache-mtime ölçütü, 45 dk'lık meşru görevleri
# 25 dk'da kesiyordu (işin ortasında pkill). v5 ölçütü: heartbeat +
# cache mtime ikisinin en genci; eşik = task_timeout + 15 dk penceresi —
# sağlıklı uzun görev ASLA ölmez; yalnız gerçekten donmuş koşucu kesilir.
#
# Kullanım: bash scripts/validation/run_baselines_watchdog.sh <task_timeout_min>
set -u
cd /home/erdem/AstroTransit
OUT=validation_runs/final_acceptance_v1/baselines
TASK_TIMEOUT_MIN=${1:-90}
LOG=$OUT/runner_loop.log

collect_descendants() {
  # ananın tüm torunlarını (geceden torunaklık) PID listesi olarak verir
  local parent="$1" child
  for child in $(ps -eo pid,ppid --no-headers | awk -v r="$parent" '$2 == r {print $1}'); do
    echo "$child"
    collect_descendants "$child"
  done
}

echo "[$(date '+%F %T')] WATCHDOG v5 başlıyor (task_timeout=${TASK_TIMEOUT_MIN} dk)" >> "$LOG"
while true; do
  sleep 120
  RUNNER=$(pgrep -f 'run_baselines_ablations.py' | head -1)
  if [ -z "$RUNNER" ]; then
    echo "[$(date '+%F %T')] WATCHDOG: koşucu yok — v5 çıkıyor" >> "$LOG"
    break
  fi
  NOW=$(date +%s)
  H=0; C=0
  [ -f "$OUT/heartbeat" ] && H=$(stat -c %Y "$OUT/heartbeat")
  [ -f "$OUT/runs_cache.jsonl" ] && C=$(stat -c %Y "$OUT/runs_cache.jsonl")
  LAST=$(( H > C ? H : C ))
  AGE=$(( (NOW - LAST) / 60 ))
  LIMIT=$(( TASK_TIMEOUT_MIN + 15 ))
  if [ "$AGE" -ge "$LIMIT" ]; then
    echo "[$(date '+%F %T')] WATCHDOG: ilerleme ${AGE} dk durdu (eşik ${LIMIT} dk) — koşucu + işçileri kesiliyor (v5)" >> "$LOG"
    { echo "$RUNNER"; collect_descendants "$RUNNER"; } | sort -u | xargs -r kill -9
    sleep 2
    # yetim işçileri garantiye al (ölen ananın çocukları da gitsin)
    { echo "$RUNNER"; collect_descendants "$RUNNER"; } | sort -u | xargs -r kill -9 2>/dev/null || true
    break
  fi
done
echo "[$(date '+%F %T')] WATCHDOG v5 bitti" >> "$LOG"
