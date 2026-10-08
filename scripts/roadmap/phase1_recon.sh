#!/usr/bin/env bash
# AstroTransit 10/10 Roadmap — PHASE 1 RECON (read-only)
# No file mutations. Prints everything we need to design FAZ 1 fixes.

set -uo pipefail

REPO="$HOME/AstroTransit"
cd "$REPO" || { echo "FATAL: $REPO not found"; exit 1; }
source .venv/bin/activate || { echo "FATAL: .venv activate failed"; exit 1; }

LOG="$HOME/phase1_recon_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

echo "=========================================="
echo " PHASE 1 RECON (read-only)"
echo " Log: $LOG"
echo "=========================================="

echo
echo "########## A) adversarial_fp.py structure ##########"
python - <<'PY_A'
from pathlib import Path
p = Path("astrotransit/validation/adversarial_fp.py")
if not p.exists():
    print("MISSING:", p); raise SystemExit
src = p.read_text()
print("total lines:", len(src.splitlines()))
print("size:", len(src), "bytes")
print()
print("--- top-level defs / classes / constants ---")
for i, line in enumerate(src.splitlines(), 1):
    s = line.strip()
    if (s.startswith("def ") or s.startswith("class ")
        or s.startswith("ADVERSARIAL") or s.startswith("MIN_")
        or s.startswith("REJECT") or s.startswith("THRESHOLD")
        or s.startswith("DEFAULT_") or s.startswith("FAMILY")
        or s.startswith("SCENARIO")):
        print(f"{i:4d} | {line}")
PY_A

echo
echo "########## B) adversarial_fp.py — full head (1-120) ##########"
sed -n '1,120p' astrotransit/validation/adversarial_fp.py || true

echo
echo "########## C) adversarial_fp.py — decision / reject logic (grep) ##########"
grep -n -E "def |reject|leak|rejection|decision|_verdict|family|scenario|threshold|>=|<=|>" \
    astrotransit/validation/adversarial_fp.py | head -150 || true

echo
echo "########## D) adversarial_fp.py — full body 120-end ##########"
sed -n '120,999p' astrotransit/validation/adversarial_fp.py || true

echo
echo "########## E) eb_coorbital_discriminator.py — full ##########"
if [ -f astrotransit/quality/eb_coorbital_discriminator.py ]; then
  wc -l astrotransit/quality/eb_coorbital_discriminator.py
  echo "---"
  cat astrotransit/quality/eb_coorbital_discriminator.py
else
  echo "MISSING eb_coorbital_discriminator.py"
fi

echo
echo "########## F) Where is eb_coorbital_discriminator imported? ##########"
grep -rn "eb_coorbital" --include='*.py' astrotransit cli dashboard tests 2>/dev/null || echo "(no imports found)"

echo
echo "########## G) Vetting pipeline — where is final decision made? ##########"
find astrotransit -type f -name '*.py' | xargs grep -ln "def vet\|vetting\|final_decision\|classif" 2>/dev/null | sort

echo
echo "########## H) validation_runs/ tree ##########"
find validation_runs -type f 2>/dev/null | sort | head -80

echo
echo "########## I) adversarial FP outputs anywhere? ##########"
find . -type f \( -name '*adversarial*' -o -name '*fp_v1*' -o -name '*leak*' \) \
    -not -path './.venv/*' -not -path './.git/*' -not -path './.cache/*' \
    -not -path '*/__pycache__/*' 2>/dev/null | sort

echo
echo "########## J) outputs/ ##########"
find outputs -maxdepth 3 -type f 2>/dev/null | sort | head -60

echo
echo "########## K) adversarial-fp-v1.yml workflow ##########"
cat .github/workflows/adversarial-fp-v1.yml 2>/dev/null || true

echo
echo "########## L) CLI entry points for adversarial fp ##########"
grep -rn "adversarial" cli/ scripts/ 2>/dev/null | head -40 || true

echo
echo "########## M) Current 56-scenario corpus definition ##########"
grep -rn -E "scenario|family|adversarial|corpus" \
    astrotransit/validation/adversarial_fp.py \
    astrotransit/validation/corpus.py 2>/dev/null | head -80 || true

echo
echo "########## N) Run existing adversarial FP test (if any) ##########"
if python -c "import astrotransit.validation.adversarial_fp" 2>/dev/null; then
  echo "module imports OK"
  python - <<'PY_N'
import inspect
from astrotransit.validation import adversarial_fp as afp
print("--- public names ---")
for name in dir(afp):
    if not name.startswith("_"):
        obj = getattr(afp, name)
        kind = type(obj).__name__
        print(f"  {name:35s} {kind}")
print()
print("--- signatures of functions/classes ---")
for name in dir(afp):
    if name.startswith("_"): continue
    obj = getattr(afp, name)
    if inspect.isfunction(obj) or inspect.isclass(obj):
        try:
            print(f"  {name}{inspect.signature(obj)}")
        except Exception:
            print(f"  {name} (no signature)")
PY_N
else
  echo "module import FAILED"
fi

echo
echo "=========================================="
echo " PHASE 1 RECON complete."
echo " Log: $LOG"
echo "=========================================="
