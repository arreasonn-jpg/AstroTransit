#!/usr/bin/env bash
set -euo pipefail
cd ~/AstroTransit
mkdir -p validation logs
LOG=logs/gaia_full_$(date +%Y%m%d_%H%M%S).log
python scripts/roadmap/phase2b5_poc_gaia_full.py 2>&1 | tee "$LOG"
echo "LOG: $LOG"
