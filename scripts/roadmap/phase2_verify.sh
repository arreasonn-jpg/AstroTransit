#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase2_verify_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== PHASE 2 VERIFY =="

echo
echo "########## 1) Report summary ##########"
python - <<'PY'
import json, hashlib
from pathlib import Path
p = Path("validation_runs/final_acceptance_v1/blind_holdout/report.json")
r = json.loads(p.read_text())
print(f"  sha256:   {hashlib.sha256(p.read_bytes()).hexdigest()}")
print(f"  status:   {r.get('status')}")
print(f"  campaign: {r.get('campaign')}")
print(f"  blocking ({len(r.get('blocking_reasons', []))}):")
for b in r.get("blocking_reasons", []):
    print(f"    - {b}")
print(f"  corpus:   {json.dumps(r.get('corpus', {}), indent=2)}")
print(f"  data:     {json.dumps(r.get('data', {}), indent=2)}")
print(f"  overall:  {json.dumps(r.get('overall', {}), indent=2)}")
print(f"  strata:")
for k, v in sorted(r.get("strata", {}).items()):
    print(f"    {k:24s} {json.dumps(v)}")
PY

echo
echo "########## 2) Shard files ##########"
SCRATCH=$(cat /tmp/phase2b_full_scratch)
ls -la "$SCRATCH/shards/"
echo "total shard files: $(ls $SCRATCH/shards/shard-*.json 2>/dev/null | wc -l)"

echo
echo "########## 3) Error rows — which 9 targets failed? ##########"
python - "$SCRATCH" <<'PY'
import json, sys
from pathlib import Path
scratch = Path(sys.argv[1])
all_rows = []
for sp in sorted((scratch/"shards").glob("shard-*.json")):
    d = json.loads(sp.read_text())
    if isinstance(d, dict) and "rows" in d:
        all_rows.extend(d["rows"])
    elif isinstance(d, list):
        all_rows.extend(d)
print(f"total rows: {len(all_rows)}")
errors = [r for r in all_rows if r.get("outcome") == "error" or r.get("error")]
print(f"error rows: {len(errors)}")
for r in errors:
    print(f"  {r.get('target_id'):>12s}  {r.get('stratum', '?'):24s}  err={r.get('error', '')[:80]}")
PY

echo
echo "########## 4) Unit tests still green? ##########"
python -m pytest tests/test_blind_holdout.py tests/test_validation_blind_holdout_full.py -q 2>&1 | tail -5

echo
echo "== DONE =="
