#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase3_build_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== build quiet controls =="

mkdir -p outputs/quiet_controls_v1

python scripts/validation/build_quiet_controls.py \
    --pool benchmarks/discovery_targets_v4_small_cool_1000_dedup.csv \
    --labelled-corpus benchmarks/corpora/tfop_disposition_corpus_v1.json \
    --prior-hosts validation_runs/v1_injection_recovery/real_noise_v1/input/quiet_hosts.json \
    --required 100 \
    --seed 20260912 \
    --output outputs/quiet_controls_v1/quiet_controls.json \
    --audit outputs/quiet_controls_v1/selection_audit.json

echo
echo "########## SHA check ##########"
python - <<'PY'
import hashlib
from pathlib import Path

p = Path("outputs/quiet_controls_v1/quiet_controls.json")
if not p.exists():
    print("  MISSING"); raise SystemExit(1)

sha = hashlib.sha256(p.read_bytes()).hexdigest()
expected = "a59e245487fc80e440fb9481734cf1f95e8778433de2b2ab9abe58f258974aea"
print(f"  actual:   {sha}")
print(f"  expected: {expected}")
print(f"  match:    {sha == expected}")

import json
d = json.loads(p.read_text())
print(f"  status: {d.get('status')}")
print(f"  selected_count: {d.get('selected_count')}")
print(f"  selection.detector_used_for_selection: {d.get('selection', {}).get('detector_used_for_selection')}")
PY

echo
echo "== DONE =="
