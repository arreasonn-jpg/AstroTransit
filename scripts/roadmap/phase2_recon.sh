#!/usr/bin/env bash
# PHASE 2 RECON (read-only). Blind holdout discovery.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2_recon_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== PHASE 2 RECON =="
echo "log: $LOG"
echo "started: $(date -Iseconds)"

echo
echo "########## A) blind_holdout.py — structure ##########"
python - <<'PY'
from pathlib import Path
p = Path("astrotransit/validation/blind_holdout.py")
if not p.exists():
    print("MISSING"); raise SystemExit
src = p.read_text()
print(f"lines: {len(src.splitlines())}, bytes: {len(src)}")
print()
print("--- top-level defs / classes / constants ---")
for i, line in enumerate(src.splitlines(), 1):
    s = line.strip()
    if (s.startswith("def ") or s.startswith("class ")
        or s.startswith("PER_") or s.startswith("DECLARED_")
        or s.startswith("HOLDOUT") or s.startswith("STRATA")
        or s.startswith("N_")):
        print(f"{i:4d} | {line}")
PY

echo
echo "########## B) blind_holdout.py — first 120 lines ##########"
sed -n '1,120p' astrotransit/validation/blind_holdout.py 2>/dev/null || echo "(missing)"

echo
echo "########## C) blind_holdout.py — public API ##########"
python - <<'PY'
import inspect
try:
    from astrotransit.validation import blind_holdout as bh
    print("import OK")
    for n in sorted(dir(bh)):
        if n.startswith("_"): continue
        o = getattr(bh, n)
        if inspect.isfunction(o) or inspect.isclass(o):
            try: print(f"  {n}{inspect.signature(o)}")
            except Exception: print(f"  {n}")
        elif isinstance(o, (str, int, float, tuple, frozenset)):
            print(f"  {n} = {o!r}"[:200])
        elif isinstance(o, dict):
            print(f"  {n}: dict{{{len(o)}}} keys={list(o.keys())[:8]}")
except Exception as e:
    print("import FAILED:", type(e).__name__, e)
PY

echo
echo "########## D) blind-holdout-v1.yml workflow ##########"
cat .github/workflows/blind-holdout-v1.yml 2>/dev/null || echo "(missing)"

echo
echo "########## E) Holdout manifest + data files ##########"
echo "--- files under validation_runs/final_acceptance_v1/blind_holdout ---"
find validation_runs/final_acceptance_v1/blind_holdout -type f 2>/dev/null | sort || echo "(dir missing)"
echo
echo "--- any blind holdout corpus/input data anywhere ---"
find . -type f \( -iname "*blind*" -o -iname "*holdout*" \) \
    -not -path "./.venv/*" -not -path "./.git/*" \
    -not -path "*/__pycache__/*" -not -path "./.cache/*" 2>/dev/null | sort

echo
echo "########## F) holdout manifest content ##########"
if [ -f validation_runs/final_acceptance_v1/blind_holdout/holdout_manifest.json ]; then
    python -c "
import json
d = json.load(open('validation_runs/final_acceptance_v1/blind_holdout/holdout_manifest.json'))
print('top keys:', list(d.keys())[:20])
for k in ('n_targets','n_scenarios','per_label','strata','labels','counts','frozen_selection','detector_used_for_selection'):
    if k in d: print(f'{k}:', json.dumps(d[k])[:400])
print()
# Look for target lists
for k, v in d.items():
    if isinstance(v, list):
        print(f'{k}: list[{len(v)}]')
        if v and isinstance(v[0], dict):
            print(f'  first: keys={list(v[0].keys())}')
    elif isinstance(v, dict) and len(str(v)) < 400:
        print(f'{k}: {v}')
"
else
    echo "(no holdout_manifest.json)"
fi

echo
echo "########## G) program.json — blind holdout gate declaration ##########"
python - <<'PY'
import json
from pathlib import Path
p = Path("validation_runs/final_acceptance_v1/program.json")
if not p.exists():
    print("MISSING"); raise SystemExit
d = json.loads(p.read_text())
for g in d.get("gates", []):
    gid = g.get("id", "")
    if "blind" in gid.lower() or "holdout" in gid.lower():
        print(json.dumps(g, indent=2))
PY

echo
echo "########## H) Dataset accessibility — do we have a data dir? ##########"
echo "--- benchmarks/ ---"
ls -la benchmarks/ 2>/dev/null | head -20 || echo "(none)"
echo
echo "--- benchmarks/corpora/ ---"
ls -la benchmarks/corpora/ 2>/dev/null || echo "(none)"
echo
echo "--- .cache/ (TESS cache) ---"
ls -la .cache/ 2>/dev/null | head -15 || echo "(none)"
echo
echo "--- data/ ---"
ls -la data/ 2>/dev/null | head -15 || echo "(none)"

echo
echo "########## I) Runner scripts for blind holdout ##########"
find scripts/ -type f \( -iname "*blind*" -o -iname "*holdout*" \) 2>/dev/null | sort || echo "(none)"
echo
echo "--- scripts/validation/ listing ---"
ls -la scripts/validation/ 2>/dev/null | head -30

echo
echo "########## J) Existing blind holdout runs ##########"
find outputs/ -maxdepth 3 -iname "*blind*" -o -maxdepth 3 -iname "*holdout*" 2>/dev/null | sort || echo "(none)"

echo
echo "########## K) Any test file for blind holdout ##########"
find tests/ -type f -iname "*blind*" -o -iname "*holdout*" 2>/dev/null | sort || echo "(none)"

echo
echo "== PHASE 2 RECON DONE =="
echo "finished: $(date -Iseconds)"
