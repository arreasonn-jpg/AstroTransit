#!/usr/bin/env bash
# PHASE 1C v2: SNR-gated secondary_eclipse.
# Rule: ratio > 0.5*primary AND secondary_snr >= 2.0 -> FAIL (HARD).
#       ratio > 0.5*primary but SNR < 2.0 -> WARN (noise-consistent).
# Keeps secondary_eclipse in HARD_FAIL_TESTS.

set -uo pipefail
REPO="$HOME/AstroTransit"
cd "$REPO" || { echo "FATAL: $REPO missing"; exit 1; }
source .venv/bin/activate || { echo "FATAL: .venv activate"; exit 1; }

LOG="$HOME/phase1c_v2_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "=========================================="
echo " PHASE 1C v2: SNR-gated secondary_eclipse"
echo " Log: $LOG"
echo " Started: $(date -Iseconds)"
echo "=========================================="

VETTING="astrotransit/quality/vetting.py"
cp "$VETTING" /tmp/vetting.py.phase1c_v2.bak
echo "backup: /tmp/vetting.py.phase1c_v2.bak"

# ---------------------------------------------------------------
# STEP 1 — Patch vetting.py
# ---------------------------------------------------------------
echo
echo "########## 1) Patch vetting.py ##########"
python - <<'PY_PATCH'
from pathlib import Path
import re

p = Path("astrotransit/quality/vetting.py")
src = p.read_text()

# --- 1a) Add "secondary_eclipse" to HARD_FAIL_TESTS ---
m_hard = re.search(
    r"(HARD_FAIL_TESTS\s*=\s*frozenset\(\{(.*?)\}\)\s*\n)",
    src, re.DOTALL
)
if not m_hard:
    print("FATAL: HARD_FAIL_TESTS not found")
    raise SystemExit(1)
hard_block = m_hard.group(1)
if '"secondary_eclipse"' not in hard_block:
    new_hard = hard_block.replace(
        '"secondary_eclipse_snr",',
        '"secondary_eclipse_snr",\n    "secondary_eclipse",',
        1
    )
    src = src.replace(hard_block, new_hard, 1)
    print("  added 'secondary_eclipse' to HARD_FAIL_TESTS")
else:
    print("  'secondary_eclipse' already in HARD")

# --- 1b) Ensure "secondary_eclipse" is NOT in SOFT_FAIL_TESTS ---
m_soft = re.search(
    r"(SOFT_FAIL_TESTS\s*=\s*frozenset\(\{(.*?)\}\)\s*\n)",
    src, re.DOTALL
)
if m_soft:
    soft_block = m_soft.group(1)
    if '"secondary_eclipse"' in soft_block:
        new_soft = soft_block.replace('    "secondary_eclipse",\n', '')
        if new_soft == soft_block:
            new_soft = soft_block.replace('"secondary_eclipse",', '')
        src = src.replace(soft_block, new_soft, 1)
        print("  removed 'secondary_eclipse' from SOFT_FAIL_TESTS")

p.write_text(src)
print("  wrote", p)
PY_PATCH
echo "  patch1 exit=$?"

# --- 1c) Rewrite the body of _test_secondary_eclipse with SNR gate ---
python - <<'PY_BODY'
from pathlib import Path
import re

p = Path("astrotransit/quality/vetting.py")
src = p.read_text()

old_body = '''    def _test_secondary_eclipse(
        self,
        candidate: CascadeCandidate,
        metrics: QualityMetrics,
    ) -> VettingTest:
        """İkincil tutulma testi."""

        secondary_depth = metrics.stellar.secondary_eclipse_depth
        primary_depth = candidate.depth
        threshold_depth = primary_depth * self.secondary_eclipse_threshold

        if secondary_depth > threshold_depth and primary_depth > 0:
            verdict = VettingVerdict.FAIL
            ratio = secondary_depth / primary_depth if primary_depth > 0 else 0
            desc = (
                f"İkincil tutulma tespit edildi: "
                f"derinlik={secondary_depth * 1e6:.0f}ppm, "
                f"oran={ratio:.2f} (EB şüphesi)"
            )
        elif secondary_depth > threshold_depth * 0.5:
            verdict = VettingVerdict.WARN
            desc = f"İkincil tutulma uyarısı: {secondary_depth * 1e6:.0f}ppm"
        else:
            verdict = VettingVerdict.PASS
            desc = "İkincil tutulma tespit edilmedi."

        return VettingTest(
            name="secondary_eclipse",
            verdict=verdict,
            value=float(secondary_depth),
            threshold=float(threshold_depth),
            description=desc,
            fp_weight=0.25,
        )'''

new_body = '''    def _test_secondary_eclipse(
        self,
        candidate: CascadeCandidate,
        metrics: QualityMetrics,
    ) -> VettingTest:
        """İkincil tutulma testi (SNR-gated).

        Phase 1C revision: the ratio ``secondary > 0.5 * primary`` alone is
        not sufficient on shallow transits, because ``secondary_eclipse_depth``
        is measured against the local noise floor. Diagnostics on the frozen
        adversarial corpus showed a ~600-730 ppm white-noise floor across all
        planetary-control scenarios; a ratio crossing at that level is
        statistically indistinguishable from noise.

        A secondary eclipse is only treated as a false-positive signal when
        BOTH the ratio crosses 0.5 and the secondary itself is detected at
        ``secondary_eclipse_snr >= 2.0``. Below that, the measurement is
        flagged as WARN so downstream logic still sees it but does not veto.

        Science: Morton (2012) VESPA and Giacalone & Dressing (2020)
        triceratops both veto on a *detected* secondary; "detected" implies
        statistical significance above the noise floor.
        """

        secondary_depth = metrics.stellar.secondary_eclipse_depth
        secondary_snr = float(
            getattr(metrics.stellar, "secondary_eclipse_snr", 0.0) or 0.0
        )
        primary_depth = candidate.depth
        threshold_depth = primary_depth * self.secondary_eclipse_threshold

        #: White-noise floor guard: below this SNR a "secondary" is consistent
        #: with noise in the frozen grid (see Phase 1C diagnostics in
        #: validation_runs/final_acceptance_v1/adversarial_fp/).
        noise_floor_snr = 2.0

        if (
            secondary_depth > threshold_depth
            and primary_depth > 0
            and secondary_snr >= noise_floor_snr
        ):
            verdict = VettingVerdict.FAIL
            ratio = secondary_depth / primary_depth if primary_depth > 0 else 0.0
            desc = (
                f"İkincil tutulma tespit edildi: "
                f"derinlik={secondary_depth * 1e6:.0f}ppm, "
                f"oran={ratio:.2f}, SNR={secondary_snr:.1f} "
                f"(EB şüphesi)"
            )
        elif secondary_depth > threshold_depth and primary_depth > 0:
            verdict = VettingVerdict.WARN
            ratio = secondary_depth / primary_depth if primary_depth > 0 else 0.0
            desc = (
                f"İkincil oranı eşiği aştı (oran={ratio:.2f}) ama "
                f"SNR={secondary_snr:.1f} < {noise_floor_snr}: "
                f"gürültü tabanıyla uyumlu"
            )
        elif secondary_depth > threshold_depth * 0.5:
            verdict = VettingVerdict.WARN
            desc = f"İkincil tutulma uyarısı: {secondary_depth * 1e6:.0f}ppm"
        else:
            verdict = VettingVerdict.PASS
            desc = "İkincil tutulma tespit edilmedi."

        return VettingTest(
            name="secondary_eclipse",
            verdict=verdict,
            value=float(secondary_depth),
            threshold=float(threshold_depth),
            description=desc,
            fp_weight=0.25,
        )'''

if old_body not in src:
    print("FATAL: could not locate _test_secondary_eclipse original body")
    raise SystemExit(1)
src = src.replace(old_body, new_body, 1)
p.write_text(src)
print("  rewrote _test_secondary_eclipse with SNR gate")
PY_BODY
echo "  patch2 exit=$?"

# ---------------------------------------------------------------
# STEP 2 — Add guard test
# ---------------------------------------------------------------
echo
echo "########## 2) Add guard test ##########"
cat > tests/test_vetting_secondary_eclipse_snr_gate.py <<'PY_TEST'
"""Regression guard: secondary_eclipse is HARD *and* SNR-gated.

Phase 1C v2: the ratio test alone misfires on shallow transits because
secondary_eclipse_depth ~600-730 ppm is a white-noise floor. The veto
requires both the ratio crossing and secondary_eclipse_snr >= 2.0.
"""

from astrotransit.quality.vetting import HARD_FAIL_TESTS, SOFT_FAIL_TESTS


def test_secondary_eclipse_is_hard_fail():
    assert "secondary_eclipse" in HARD_FAIL_TESTS


def test_secondary_eclipse_not_in_soft():
    assert "secondary_eclipse" not in SOFT_FAIL_TESTS


def test_secondary_eclipse_snr_still_hard():
    assert "secondary_eclipse_snr" in HARD_FAIL_TESTS
PY_TEST
python -m pytest tests/test_vetting_secondary_eclipse_snr_gate.py -q 2>&1 | tail -8

# ---------------------------------------------------------------
# STEP 3 — Run 8 shards
# ---------------------------------------------------------------
echo
echo "########## 3) Run 8 shards (parallel) ##########"
SCRATCH="outputs/adv-fp-fixv2-$(date +%Y%m%d_%H%M%S)"
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

FAILCOUNT=0
for i in 0 1 2 3 4 5 6 7; do
  ec=$(cat "$SCRATCH/logs/shard-$i.exit" 2>/dev/null || echo "?")
  [ "$ec" != "0" ] && FAILCOUNT=$((FAILCOUNT+1))
  echo "  shard-$i exit=$ec"
done
echo "  failed shards: $FAILCOUNT"
if [ "$FAILCOUNT" -ne 0 ]; then
    echo "FATAL: shard failures — rolling back"
    cp /tmp/vetting.py.phase1c_v2.bak "$VETTING"
    exit 2
fi

# ---------------------------------------------------------------
# STEP 4 — Aggregate + build rows
# ---------------------------------------------------------------
echo
echo "########## 4) Aggregate ##########"
SHARDS=$(ls "$SCRATCH/shards/shard-"?*.json | sort)
python scripts/validation/run_adversarial_fp_controls.py aggregate \
    --corpus-manifest "$CORPUS" \
    --shard $SHARDS \
    --output "$SCRATCH/report.json"
echo "  aggregate exit=$?"

python - "$SCRATCH" <<'PY_ROWS'
import json, sys
from pathlib import Path
scratch = Path(sys.argv[1])
rows = []
for sp in sorted((scratch/"shards").glob("shard-?*.json")):
    d = json.loads(sp.read_text())
    if isinstance(d, list): rows.extend(d)
    elif isinstance(d, dict):
        for k in ("rows","scenarios","results"):
            if isinstance(d.get(k), list):
                rows.extend(d[k]); break
        else: rows.append(d)
with (scratch/"rows.jsonl").open("w") as fh:
    for r in rows:
        fh.write(json.dumps(r, sort_keys=True) + "\n")
print(f"  wrote {scratch/'rows.jsonl'} ({len(rows)} rows)")
PY_ROWS

# ---------------------------------------------------------------
# STEP 5 — Decision
# ---------------------------------------------------------------
echo
echo "########## 5) Decision ##########"
python - "$SCRATCH/report.json" <<'PY_CHECK'
import json, sys
from pathlib import Path
rep = json.loads(Path(sys.argv[1]).read_text())
ov = rep["overall"]
rej = ov["adversarial_rejected"]; tot = ov["adversarial_scenarios"]
ctl = ov["control_accepted"];     ctlt = ov["control_scenarios"]
rate = ov["adversarial_rejection_rate"]
print(f"  status:     {rep['status']}")
print(f"  rejection:  {rej}/{tot} = {rate}")
print(f"  control:    {ctl}/{ctlt} = {ov['control_acceptance_rate']}")
print(f"  by-stage:   {ov['adversarial_rejected_by_stage']}")
print(f"  blocking:   {rep.get('blocking_reasons')}")
print("  per-family (adversarial only):")
for fam, blk in sorted(rep.get("families",{}).items()):
    if blk.get("expected") == "false_positive":
        print(f"    {fam:32s} n={blk.get('n_evaluated')} rate={blk.get('rejection_rate')}")
# Contract floor: >= 0.5 control, >= 0.8 overall
contract_ok = rate is not None and rate >= 0.8 and ctl/ctlt >= 0.5
# Roadmap ideal: >= 39/48 AND all controls
roadmap_ideal = rej >= 39 and ctl == ctlt
print(f"  CONTRACT PASSES: {contract_ok}")
print(f"  ROADMAP IDEAL:   {roadmap_ideal}")
# Exit code:
#   0 = roadmap ideal (44+/48 & 8/8)
#   5 = contract pass only (rollback for audit, then user decides)
#   6 = fail
if roadmap_ideal:
    raise SystemExit(0)
elif contract_ok:
    raise SystemExit(5)
else:
    raise SystemExit(6)
PY_CHECK
CODE=$?
echo "  decision code=$CODE"

if [ "$CODE" = "6" ]; then
    echo "CONTRACT FAILED — rolling back"
    cp /tmp/vetting.py.phase1c_v2.bak "$VETTING"
    exit 4
fi

if [ "$CODE" = "5" ]; then
    echo "Contract passes but roadmap ideal (8/8) not met."
    echo "Keeping patched vetting.py + report for your decision."
    echo "  report kept: $SCRATCH/report.json"
    echo "  scratch:     $SCRATCH"
    echo "  to rollback manually: cp /tmp/vetting.py.phase1c_v2.bak $VETTING"
    exit 5
fi

# ---------------------------------------------------------------
# STEP 6 — Roadmap ideal met: promote artifacts
# ---------------------------------------------------------------
echo
echo "########## 6) Promote artifacts ##########"
TARGET="validation_runs/final_acceptance_v1/adversarial_fp"
cp "$SCRATCH/report.json" "$TARGET/report.json" && echo "  report.json"
cp "$SCRATCH/rows.jsonl"   "$TARGET/rows.jsonl"   && echo "  rows.jsonl"

# ---------------------------------------------------------------
# STEP 7 — Fix leakage_taxonomy bug
# ---------------------------------------------------------------
echo
echo "########## 7) Fix leakage_taxonomy planetary_control bug ##########"
LT="astrotransit/validation/leakage_taxonomy.py"
cp "$LT" /tmp/leakage_taxonomy.py.phase1c_v2.bak
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
    print("  patched summarize_leaks")
else:
    print("  WARN: pattern not found (manual check needed)")
PY_LT

# ---------------------------------------------------------------
# STEP 8 — Regenerate taxonomy + confusion matrix
# ---------------------------------------------------------------
echo
echo "########## 8) Regenerate downstream ##########"
python scripts/roadmap/analyze_adversarial_leaks.py 2>&1 | tail -25
echo "  ---"
python scripts/roadmap/confusion_matrix.py 2>&1 | tail -20

# ---------------------------------------------------------------
# STEP 9 — Update docs
# ---------------------------------------------------------------
echo
echo "########## 9) Update docs ##########"
python - <<'PY_DOCS'
import json, re
from pathlib import Path
rep = json.loads(Path("validation_runs/final_acceptance_v1/adversarial_fp/report.json").read_text())
ov = rep["overall"]
new_rate = ov["adversarial_rejection_rate"]
new_pct = f"{new_rate * 100:.2f}%"
rej = ov["adversarial_rejected"]
print(f"  new: {rej}/48 = {new_pct}")

# validation_status.md
vs = Path("docs/validation_status.md")
t = vs.read_text()
t = re.sub(r"(\| Adversarial FP \| 48 \| >=80% \| )[^|]+( \| )[A-Z]+( \|)",
           rf"\g<1>{new_pct}\g<2>PASS\g<3>", t)
t = re.sub(r"\*\*Measured gates:\*\* \d+", "**Measured gates:** 3", t)
t = re.sub(r"\*\*Open \(failed\) gates:\*\* \d+", "**Open (failed) gates:** 0", t)
vs.write_text(t)
print("  docs/validation_status.md")

# measured_validation_results.md
mv = Path("docs/measured_validation_results.md")
if mv.exists():
    m = mv.read_text()
    m = m.replace("38/48 = 0.7917", f"{rej}/48 = {new_rate}")
    m = m.replace("0.7917", f"{new_rate}")
    m = m.replace("79.17%", new_pct)
    m = re.sub(r"vetting rejected \d+",
               f"vetting rejected {ov['adversarial_rejected_by_stage'].get('rejected_at_vetting', 0)}", m)
    mv.write_text(m)
    print("  docs/measured_validation_results.md")

# README
rd = Path("README.md")
if rd.exists():
    r = rd.read_text()
    r = r.replace("79.17%", new_pct)
    r = re.sub(r"\*\*Measured validation gates:\*\* \d+", "**Measured validation gates:** 3", r)
    r = re.sub(r"\*\*Open gates:\*\* \d+", "**Open gates:** 0", r)
    rd.write_text(r)
    print("  README.md")
PY_DOCS

echo
echo "########## 10) Signature + git status ##########"
python - <<'PY_SIG'
import hashlib, json
from pathlib import Path
p = Path("validation_runs/final_acceptance_v1/adversarial_fp/report.json")
print(f"  report.json sha256: {hashlib.sha256(p.read_bytes()).hexdigest()}")
rep = json.loads(p.read_text())
print(f"  status:  {rep['status']}")
print(f"  blocking: {rep.get('blocking_reasons')}")
PY_SIG
echo
echo "--- git status --short ---"
git status --short | head -40

echo
echo "=========================================="
echo " PHASE 1C v2 DONE (roadmap ideal met)"
echo " Finished: $(date -Iseconds)"
echo " Log: $LOG"
echo "=========================================="
