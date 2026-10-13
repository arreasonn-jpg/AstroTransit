#!/usr/bin/env bash
# FAZ 3 recon (read-only): FP + quiet controls discovery.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase3_recon_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 3 RECON =="
echo "log: $LOG"

echo
echo "########## 1) Runner CLI ##########"
python scripts/validation/run_false_positive_controls.py --help 2>&1 | head -40

echo
echo "########## 2) Corpus files available ##########"
ls -la benchmarks/corpora/ 2>/dev/null

echo
echo "########## 3) FP subset content ##########"
python - <<'PY'
import json
from pathlib import Path
p = Path("benchmarks/corpora/fp_run_subset_v1.json")
if not p.exists():
    print("MISSING"); raise SystemExit
d = json.loads(p.read_text())
print(f"top keys: {list(d.keys())}")
for k, v in d.items():
    if isinstance(v, list):
        print(f"  {k}: list[{len(v)}]")
        if v and isinstance(v[0], dict):
            print(f"    first item keys: {list(v[0].keys())}")
    elif isinstance(v, dict):
        print(f"  {k}: dict{list(v.keys())}")
    else:
        print(f"  {k}: {str(v)[:80]}")
PY

echo
echo "########## 4) Gate declaration in program.json ##########"
python - <<'PY'
import json
from pathlib import Path
d = json.loads(Path("validation_runs/final_acceptance_v1/program.json").read_text())
for g in d.get("gates", []):
    if g.get("id") == "labelled_fp_quiet_controls":
        print(json.dumps(g, indent=2))
PY

echo
echo "########## 5) Workflow: fp-quiet-controls-v1.yml ##########"
head -80 .github/workflows/fp-quiet-controls-v1.yml 2>/dev/null

echo
echo "########## 6) Workflow: quiet-controls-v1.yml ##########"
head -60 .github/workflows/quiet-controls-v1.yml 2>/dev/null

echo
echo "########## 7) Prior run dirs ##########"
find outputs/ -maxdepth 2 -type d -iname "*fp*" -o -maxdepth 2 -type d -iname "*quiet*" 2>/dev/null | sort
find validation_runs/ -maxdepth 3 -type d -iname "*fp*" -o -maxdepth 3 -type d -iname "*quiet*" 2>/dev/null | sort

echo
echo "########## 8) Prior evidence files ##########"
find validation_runs/final_acceptance_v1/false_positive_controls -type f 2>/dev/null | sort
find validation_runs/final_acceptance_v1/quiet_controls -type f 2>/dev/null | sort

echo
echo "== DONE =="
