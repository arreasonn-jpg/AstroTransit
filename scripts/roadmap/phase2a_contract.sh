#!/usr/bin/env bash
# PHASE 2A: offline contract check + manifest inspection for blind holdout.
# Read-only + one offline subprocess. No MAST access.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2a_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== PHASE 2A: blind holdout contract =="
echo "log: $LOG"
echo "started: $(date -Iseconds)"

echo
echo "########## 1) Runner CLI (all subcommands) ##########"
python scripts/validation/run_blind_holdout.py --help 2>&1 | head -50 || true
echo
echo "--- check --help ---"
python scripts/validation/run_blind_holdout.py check --help 2>&1 | head -30 || true
echo
echo "--- run-shard --help ---"
python scripts/validation/run_blind_holdout.py run-shard --help 2>&1 | head -40 || true
echo
echo "--- aggregate --help ---"
python scripts/validation/run_blind_holdout.py aggregate --help 2>&1 | head -30 || true

echo
echo "########## 2) Manifest summary — structural detail ##########"
python - <<'PY'
import json
from collections import Counter
from pathlib import Path

m = json.loads(Path("validation_runs/final_acceptance_v1/blind_holdout/holdout_manifest.json").read_text())
print(f"top keys: {sorted(m.keys())}")
print(f"status: {m.get('status')}")
print(f"holdout_sha256: {m.get('holdout_sha256')}")
print(f"corpus: {m.get('corpus')}")
print(f"split: {m.get('split')}")
print(f"counts: {m.get('counts')}")
print(f"stratum_counts: {m.get('stratum_counts')}")
print(f"pool_sizes: {m.get('pool_sizes')}")
print(f"quotas: {m.get('quotas')}")
print(f"rejection_counts: {m.get('rejection_counts')}")
print(f"floors: {m.get('floors')}")
print()
cases = m["cases"]
print(f"cases: {len(cases)}")
print(f"first case keys: {sorted(cases[0].keys())}")
print()
# Sector histogram — cost estimate for MAST
sector_counts = Counter()
n_sectors_total = 0
empty_sectors = 0
for c in cases:
    s = c.get("sectors") or []
    sector_counts[len(s)] += 1
    n_sectors_total += len(s)
    if not s:
        empty_sectors += 1
print(f"total sector-downloads across 144 cases: {n_sectors_total}")
print(f"cases with 0 sectors listed: {empty_sectors}")
print(f"sectors-per-case histogram: {dict(sorted(sector_counts.items()))}")
print()
# Sample 3 cases
print("sample cases (first 3):")
for c in cases[:3]:
    print(json.dumps({k: c[k] for k in ("target_id", "label", "stratum", "sectors", "selection_rank")}, indent=2))
print()
# Per-stratum sample
per_stratum = {}
for c in cases:
    s = c["stratum"]
    per_stratum.setdefault(s, []).append(c["target_id"])
for s in sorted(per_stratum):
    print(f"  {s}: {len(per_stratum[s])} targets (sample: {per_stratum[s][:3]})")
PY

echo
echo "########## 3) Offline contract check (must agree with program.json) ##########"
python scripts/validation/run_blind_holdout.py check 2>&1 | tail -40
CHECK_EXIT=$?
echo "  check exit=$CHECK_EXIT"

echo
echo "########## 4) Offline shard (must refuse to claim measurement) ##########"
mkdir -p outputs/blind-holdout-contract
rm -f outputs/blind-holdout-contract/shard-00.json
python scripts/validation/run_blind_holdout.py run-shard \
    --shard-index 0 --shard-count 1 --offline \
    --output outputs/blind-holdout-contract/shard-00.json 2>&1 | tail -20
SHARD_EXIT=$?
echo "  run-shard --offline exit=$SHARD_EXIT"

echo
echo "--- aggregate (should exit 3, status pending_run) ---"
python scripts/validation/run_blind_holdout.py aggregate \
    --rows outputs/blind-holdout-contract \
    --output outputs/blind-holdout-contract/report.json 2>&1 | tail -20
AGG_EXIT=$?
echo "  aggregate exit=$AGG_EXIT"

if [ -f outputs/blind-holdout-contract/report.json ]; then
    python - <<'PY'
import json
r = json.load(open("outputs/blind-holdout-contract/report.json"))
print(f"  status: {r.get('status')}")
print(f"  blocking_reasons: {r.get('blocking_reasons')}")
PY
fi

echo
echo "########## 5) Unit tests for blind holdout ##########"
python -m pytest tests/test_blind_holdout.py tests/test_validation_blind_holdout_full.py -q 2>&1 | tail -8

echo
echo "########## 6) .cache/ content — do we have prior TESS downloads? ##########"
find .cache/astrotransit -type f 2>/dev/null | head -20 || echo "(empty)"
echo "file count: $(find .cache/astrotransit -type f 2>/dev/null | wc -l)"

echo
echo "########## 7) Current program.json gate status for blind ##########"
python - <<'PY'
import json
d = json.load(open("validation_runs/final_acceptance_v1/program.json"))
for g in d["gates"]:
    if g["id"] == "blind_domain_holdout":
        print(f"  status: {g['status']}")
        print(f"  required_output: {g['required_output']}")
        print(f"  n_acceptance_checks: {len(g['acceptance_checks'])}")
        for c in g["acceptance_checks"][:8]:
            print(f"    {c['path']} {c['operator']} {c['value']}")
        print(f"    ... (+{len(g['acceptance_checks'])-8} more)")
PY

echo
echo "== PHASE 2A DONE =="
echo "finished: $(date -Iseconds)"
