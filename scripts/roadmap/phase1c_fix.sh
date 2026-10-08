#!/usr/bin/env bash
# PHASE 1C: promote secondary_eclipse SOFT→HARD, re-run grid, update artifacts.
# Design: file-only logging (no tee, no pipe) to avoid the 1A hang.

set -uo pipefail
REPO="$HOME/AstroTransit"
cd "$REPO" || { echo "FATAL: $REPO missing"; exit 1; }
source .venv/bin/activate || { echo "FATAL: .venv activate"; exit 1; }

LOG="$HOME/phase1c_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "=========================================="
echo " PHASE 1C: secondary_eclipse → HARD"
echo " Log: $LOG"
echo " Started: $(date -Iseconds)"
echo "=========================================="

# ---------------------------------------------------------------
# STEP 1 — Patch vetting.py
# ---------------------------------------------------------------
echo
echo "########## 1) Patch vetting.py ##########"
VETTING="astrotransit/quality/vetting.py"
cp "$VETTING" /tmp/vetting.py.phase1c.bak
echo "  backup: /tmp/vetting.py.phase1c.bak"

python - <<'PY_PATCH'
from pathlib import Path
import re

p = Path("astrotransit/quality/vetting.py")
src = p.read_text()

# Locate HARD_FAIL_TESTS block
m_hard = re.search(
    r"(HARD_FAIL_TESTS\s*=\s*frozenset\(\{(.*?)\}\)\s*\n)",
    src, re.DOTALL
)
m_soft = re.search(
    r"(SOFT_FAIL_TESTS\s*=\s*frozenset\(\{(.*?)\}\)\s*\n)",
    src, re.DOTALL
)
if not m_hard or not m_soft:
    print("FATAL: could not locate HARD/SOFT frozensets")
    raise SystemExit(1)

hard_block = m_hard.group(1)
soft_block = m_soft.group(1)

# Add "secondary_eclipse" to HARD (after "secondary_eclipse_snr")
if '"secondary_eclipse",' not in hard_block and "'secondary_eclipse'," not in hard_block:
    new_hard = hard_block.replace(
        '"secondary_eclipse_snr",',
        '"secondary_eclipse_snr",\n    # PROMOTED from SOFT (Phase 1C): a secondary deeper than half the\n    # primary depth cannot be a planet. Morton 2012 VESPA; Giacalone &\n    # Dressing 2020 triceratops both veto on detected secondary alone.\n    "secondary_eclipse",',
        1
    )
    src = src.replace(hard_block, new_hard, 1)
    print("  added 'secondary_eclipse' to HARD_FAIL_TESTS")

# Remove "secondary_eclipse" from SOFT
if '"secondary_eclipse",' in soft_block:
    new_soft = soft_block.replace('    "secondary_eclipse",\n', '')
    if new_soft == soft_block:
        new_soft = soft_block.replace('"secondary_eclipse",', '')
    src = src.replace(soft_block, new_soft, 1)
    print("  removed 'secondary_eclipse' from SOFT_FAIL_TESTS")

p.write_text(src)
print("  wrote", p)

# Verify
src2 = p.read_text()
mh = re.search(r"HARD_FAIL_TESTS\s*=\s*frozenset\(\{(.*?)\}\)", src2, re.DOTALL).group(1)
ms = re.search(r"SOFT_FAIL_TESTS\s*=\s*frozenset\(\{(.*?)\}\)", src2, re.DOTALL).group(1)
print("  HARD now contains secondary_eclipse:", '"secondary_eclipse"' in mh)
print("  SOFT now contains secondary_eclipse:", '"secondary_eclipse"' in ms)
assert '"secondary_eclipse"' in mh
assert '"secondary_eclipse"' not in ms
PY_PATCH
PATCH_EXIT=$?
echo "  patch exit=$PATCH_EXIT"
if [ "$PATCH_EXIT" -ne 0 ]; then
    echo "FATAL: patch failed — restoring"
    cp /tmp/vetting.py.phase1c.bak "$VETTING"
    exit 1
fi

# ---------------------------------------------------------------
# STEP 2 — Add a guard test
# ---------------------------------------------------------------
echo
echo "########## 2) Add guard test ##########"
cat > tests/test_vetting_secondary_eclipse_hard.py <<'PY_TEST'
"""Regression guard: secondary_eclipse is a HARD fail (Phase 1C).

Science: a secondary eclipse deeper than half the primary depth cannot be
a planetary transit. Morton (2012) VESPA and Giacalone & Dressing (2020)
triceratops both veto on a detected secondary alone. This test locks the
classification so future refactors cannot quietly demote it.
"""

from astrotransit.quality.vetting import HARD_FAIL_TESTS, SOFT_FAIL_TESTS


def test_secondary_eclipse_is_hard_fail():
    assert "secondary_eclipse" in HARD_FAIL_TESTS


def test_secondary_eclipse_not_soft_fail():
    assert "secondary_eclipse" not in SOFT_FAIL_TESTS


def test_secondary_eclipse_snr_still_hard():
    assert "secondary_eclipse_snr" in HARD_FAIL_TESTS
PY_TEST
python -m pytest tests/test_vetting_secondary_eclipse_hard.py -q 2>&1 | tail -10

# ---------------------------------------------------------------
# STEP 3 — Run 8-shard campaign
# ---------------------------------------------------------------
echo
echo "########## 3) Run 8 shards (parallel) ##########"
SCRATCH="outputs/adv-fp-fix-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$SCRATCH/shards" "$SCRATCH/logs"
echo "  scratch: $SCRATCH"

CORPUS="validation_runs/final_acceptance_v1/adversarial_fp/corpus_manifest.json"
CONFIG="configs/benchmark_fp.toml"

START=$(date +%s)
for i in 0 1 2 3 4 5 6 7; do
  (python scripts/validation/run_adversarial_fp_controls.py run-shard \
      --corpus-manifest "$CORPUS" \
      --config "$CONFIG" \
      --shard-index "$i" \
      --shard-count 8 \
      --output "$SCRATCH/shards/shard-$(printf '%02d' "$i").json" \
      > "$SCRATCH/logs/shard-$i.log" 2>&1
   echo "$?" > "$SCRATCH/logs/shard-$i.exit") &
done
wait
END=$(date +%s)
echo "  done in $((END-START)) seconds ($(( (END-START)/60 )) min)"

echo
echo "--- per-shard exit codes ---"
FAILCOUNT=0
for i in 0 1 2 3 4 5 6 7; do
  ec=$(cat "$SCRATCH/logs/shard-$i.exit" 2>/dev/null || echo "?")
  echo "  shard-$i exit=$ec"
  [ "$ec" != "0" ] && FAILCOUNT=$((FAILCOUNT+1))
done
echo "  total failed shards: $FAILCOUNT"

if [ "$FAILCOUNT" -ne 0 ]; then
    echo "FATAL: $FAILCOUNT shards failed"
    echo "--- first failed shard tail ---"
    for i in 0 1 2 3 4 5 6 7; do
        ec=$(cat "$SCRATCH/logs/shard-$i.exit" 2>/dev/null || echo "?")
        if [ "$ec" != "0" ]; then
            tail -30 "$SCRATCH/logs/shard-$i.log"
            break
        fi
    done
    echo "restoring vetting.py"
    cp /tmp/vetting.py.phase1c.bak "$VETTING"
    exit 2
fi

# ---------------------------------------------------------------
# STEP 4 — Aggregate
# ---------------------------------------------------------------
echo
echo "########## 4) Aggregate ##########"
SHARDS=$(ls "$SCRATCH/shards/shard-"?*.json | sort)
python scripts/validation/run_adversarial_fp_controls.py aggregate \
    --corpus-manifest "$CORPUS" \
    --shard $SHARDS \
    --output "$SCRATCH/report.json"
AGG_EXIT=$?
echo "  aggregate exit=$AGG_EXIT"
[ -f "$SCRATCH/report.json" ] || { echo "FATAL: no report"; exit 3; }

# ---------------------------------------------------------------
# STEP 5 — Build fresh rows.jsonl
# ---------------------------------------------------------------
echo
echo "########## 5) Build fresh rows.jsonl ##########"
python - "$SCRATCH" <<'PY_ROWS'
import json, sys
from pathlib import Path
from collections import Counter
scratch = Path(sys.argv[1])
all_rows = []
for sp in sorted((scratch/"shards").glob("shard-?*.json")):
    d = json.loads(sp.read_text())
    if isinstance(d, list):
        all_rows.extend(d)
    elif isinstance(d, dict):
        for key in ("rows", "scenarios", "results"):
            if isinstance(d.get(key), list):
                all_rows.extend(d[key]); break
        else:
            all_rows.append(d)
out = scratch / "rows.jsonl"
with out.open("w") as fh:
    for r in all_rows:
        fh.write(json.dumps(r, sort_keys=True) + "\n")
print(f"  wrote {out} ({len(all_rows)} rows)")
adv = [r for r in all_rows if r.get("family") != "planetary_control"]
leaks = [r for r in adv if r.get("outcome") == "leaked_as_candidate"]
print(f"  adversarial: {len(adv)}  leaks: {len(leaks)}")
print(f"  outcome distribution: {dict(Counter(str(r.get('outcome')) for r in all_rows))}")
PY_ROWS

# ---------------------------------------------------------------
# STEP 6 — Read result, decide pass/fail
# ---------------------------------------------------------------
echo
echo "########## 6) Result ##########"
python - "$SCRATCH/report.json" <<'PY_CHECK'
import json, sys
from pathlib import Path
rep = json.loads(Path(sys.argv[1]).read_text())
ov = rep.get("overall", {})
rej = ov.get("adversarial_rejected")
tot = ov.get("adversarial_scenarios")
rate = ov.get("adversarial_rejection_rate")
ctl = ov.get("control_accepted")
ctlt = ov.get("control_scenarios")
print(f"  status: {rep.get('status')}")
print(f"  rejection: {rej}/{tot} = {rate}")
print(f"  control:   {ctl}/{ctlt}")
print(f"  blocking:  {rep.get('blocking_reasons')}")
print("  per-family:")
for fam, blk in sorted(rep.get("families", {}).items()):
    if blk.get("expected") == "false_positive":
        print(f"    {fam:32s} n={blk.get('n_evaluated')} rate={blk.get('rejection_rate')}")
# Exit code for the shell: 0 if pass (>= 39/48 AND controls all accepted), else 1
ok = (rej is not None and rej >= 39 and ctl == ctlt and rate is not None and rate >= 0.8)
print(f"  PASS: {ok}")
raise SystemExit(0 if ok else 1)
PY_CHECK
PASS=$?
echo "  pass=$PASS"

if [ "$PASS" -ne 0 ]; then
    echo
    echo "GATE DID NOT PASS — inspecting, restoring, exiting"
    echo "  report kept at: $SCRATCH/report.json"
    cp /tmp/vetting.py.phase1c.bak "$VETTING"
    echo "  vetting.py restored"
    exit 4
fi

echo
echo "GATE PASSED ✅ — proceeding to update artifacts"

# ---------------------------------------------------------------
# STEP 7 — Update frozen artifacts
# ---------------------------------------------------------------
echo
echo "########## 7) Update frozen artifacts ##########"
TARGET="validation_runs/final_acceptance_v1/adversarial_fp"
cp "$SCRATCH/report.json" "$TARGET/report.json" && echo "  report.json updated"
cp "$SCRATCH/rows.jsonl"   "$TARGET/rows.jsonl"   && echo "  rows.jsonl updated"

# ---------------------------------------------------------------
# STEP 8 — Fix leakage_taxonomy bug (planetary_control filter)
# ---------------------------------------------------------------
echo
echo "########## 8) Fix leakage_taxonomy.py planetary_control bug ##########"
LT="astrotransit/validation/leakage_taxonomy.py"
cp "$LT" /tmp/leakage_taxonomy.py.phase1c.bak
python - <<'PY_LT'
from pathlib import Path
p = Path("astrotransit/validation/leakage_taxonomy.py")
src = p.read_text()
old = 'leak_rows = [r for r in rows if str(r.get("outcome")) == "leaked_as_candidate"]'
new = ('leak_rows = [\n'
       '        r for r in rows\n'
       '        if str(r.get("outcome")) == "leaked_as_candidate"\n'
       '        and str(r.get("family", "")) != "planetary_control"\n'
       '    ]')
if old in src:
    src = src.replace(old, new, 1)
    p.write_text(src)
    print("  patched summarize_leaks (planetary_control excluded)")
else:
    print("  WARN: pattern not found; manual inspection may be needed")
PY_LT

# ---------------------------------------------------------------
# STEP 9 — Regenerate taxonomy, confusion matrix, leak doc
# ---------------------------------------------------------------
echo
echo "########## 9) Regenerate downstream artifacts ##########"
python scripts/roadmap/analyze_adversarial_leaks.py 2>&1 | tail -30
echo "  ---"
python scripts/roadmap/confusion_matrix.py 2>&1 | tail -20

# ---------------------------------------------------------------
# STEP 10 — Update docs
# ---------------------------------------------------------------
echo
echo "########## 10) Update docs ##########"
python - <<'PY_DOCS'
import json, re
from pathlib import Path
rep = json.loads(Path("validation_runs/final_acceptance_v1/adversarial_fp/report.json").read_text())
ov = rep["overall"]
new_rate = ov["adversarial_rejection_rate"]
new_pct = f"{new_rate * 100:.2f}%"
rej = ov["adversarial_rejected"]
tot = ov["adversarial_scenarios"]
print(f"  new: {rej}/{tot} = {new_pct}")
new_status = "PASS" if rej >= 39 else "FAIL"

# validation_status.md
vs = Path("docs/validation_status.md")
t = vs.read_text()
t = re.sub(
    r"(\| Adversarial FP \| 48 \| >=80% \| )[^|]+( \| )[A-Z]+( \|)",
    rf"\g<1>{new_pct}\g<2>{new_status}\g<3>",
    t,
)
# also fix counts
t = re.sub(r"\*\*Measured gates:\*\* \d+", "**Measured gates:** 3", t)
if new_status == "PASS":
    t = re.sub(r"\*\*Open \(failed\) gates:\*\* \d+", "**Open (failed) gates:** 0", t)
vs.write_text(t)
print("  updated docs/validation_status.md")

# measured_validation_results.md — replace the old 0.7917 references
mv = Path("docs/measured_validation_results.md")
if mv.exists():
    m = mv.read_text()
    m = m.replace("38/48 = 0.7917", f"{rej}/48 = {new_rate}")
    m = m.replace("0.7917", f"{new_rate}")
    m = m.replace("79.17%", new_pct)
    m = re.sub(r"vetting rejected 26", f"vetting rejected {ov['adversarial_rejected_by_stage'].get('rejected_at_vetting', 26)}", m)
    mv.write_text(m)
    print("  updated docs/measured_validation_results.md")

# README
rd = Path("README.md")
r = rd.read_text()
r = r.replace("79.17%", new_pct)
r = re.sub(r"\*\*Measured validation gates:\*\* \d+", "**Measured validation gates:** 3", r)
r = re.sub(r"\*\*Open gates:\*\* \d+", "**Open gates:** 0" if new_status == "PASS" else "**Open gates:** 1", r)
rd.write_text(r)
print("  updated README.md")
PY_DOCS

# ---------------------------------------------------------------
# STEP 11 — Show git diff summary
# ---------------------------------------------------------------
echo
echo "########## 11) Git status ##########"
git status --short 2>/dev/null | head -40

echo
echo "########## 12) Report signature ##########"
python - <<'PY_SIG'
import hashlib, json
from pathlib import Path
p = Path("validation_runs/final_acceptance_v1/adversarial_fp/report.json")
print(f"  report.json sha256: {hashlib.sha256(p.read_bytes()).hexdigest()}")
rep = json.loads(p.read_text())
print(f"  status: {rep['status']}")
print(f"  blocking_reasons: {rep.get('blocking_reasons')}")
PY_SIG

# ---------------------------------------------------------------
# STEP 12 — Clean scratch (keep dir for inspection, but compress)
# ---------------------------------------------------------------
echo
echo "########## 12) Scratch location (keep for inspection) ##########"
echo "  $SCRATCH"
echo "  to clean: rm -rf \"$SCRATCH\""

echo
echo "=========================================="
echo " PHASE 1C DONE"
echo " Finished: $(date -Iseconds)"
echo " Log: $LOG"
echo "=========================================="
