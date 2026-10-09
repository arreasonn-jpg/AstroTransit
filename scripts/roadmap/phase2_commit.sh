#!/usr/bin/env bash
# Commit FAZ 2 blind holdout evidence. Gate stays OPEN (honest science).
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2_commit_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== PHASE 2 COMMIT =="
echo "log: $LOG"

GITID=(-c user.email="validation@astrotransit.local" -c user.name="AstroTransit Validation")

# ---- 0) Ensure test passes ----
echo
echo "########## 0) Verify tests ##########"
python -m pytest tests/test_blind_holdout.py tests/test_validation_blind_holdout_full.py -q 2>&1 | tail -5
[ ${PIPESTATUS[0]} -eq 0 ] || { echo "FATAL: tests failing"; exit 1; }

# ---- 1) Extend docs/validation_status.md with the blind row ----
echo
echo "########## 1) Update validation_status.md ##########"
python - <<'PY'
import json, re
from pathlib import Path

# Read the measured report
rep = json.loads(Path("validation_runs/final_acceptance_v1/blind_holdout/report.json").read_text())
ov = rep["overall"]
data = rep["data"]
new_status = "MEASURED_OPEN"  # not "PASS" — gate has 2 blockers
recall = ov["recall"]
fpr = ov["false_positive_rate"]
n_eval = data["n_evaluated"]
errors = data["errors"]

row = (f"| Blind holdout | 144 | predefined | "
       f"{n_eval} eval, recall {recall:.4f}, FPR {fpr:.4f}, errors={errors} "
       f"| {new_status} | `<TBD>` | `<TBD>` |")

p = Path("docs/validation_status.md")
t = p.read_text()

# Replace existing blind row (if any) or append after the FPP row
if re.search(r"\| Blind holdout \|", t):
    t = re.sub(r"\| Blind holdout \|[^\n]*\|", row, t, count=1)
    print("  replaced existing blind row")
else:
    t = t.replace(
        "| FPP calibration |",
        row + "\n| FPP calibration |",
        1,
    )
    print("  inserted before FPP row")

# Update counts
t = re.sub(r"\*\*Measured gates:\*\* \d+", "**Measured gates:** 4", t)
t = re.sub(r"\*\*Pending execution gates:\*\* \d+", "**Pending execution gates:** 1", t)
t = re.sub(r"\*\*Open \(failed\) gates:\*\* \d+", "**Open (failed) gates:** 1", t)

p.write_text(t)
print("  wrote docs/validation_status.md")
PY

# ---- 2) Add a FAZ 2 section to measured_validation_results.md ----
echo
echo "########## 2) Append FAZ 2 section to measured_validation_results.md ##########"
python - <<'PY'
import json
from pathlib import Path

rep = json.loads(Path("validation_runs/final_acceptance_v1/blind_holdout/report.json").read_text())

section = f"""

## Blind domain holdout v1 — first measurement (gate remains open)

144 real TESS targets, frozen from the blind partition (`split=blind_test`,
disjoint from every earlier gate id). Detector was not consulted during
selection (`detector_used_for_selection: false`). 12-shard run, cached SPOC
120s sectors.

**Result: MEASURED, gate open.** Two blockers:

- `false_positive_rate_above_declared_ceiling: {rep["overall"]["false_positive_rate"]:.4f} > 0.6`
- `error_rows:{rep["data"]["errors"]}` (9 targets with no SPOC 120s sector)

| Metric | Value | 95% CI |
|---|---:|---|
| Recall (planets) | {rep["overall"]["recall"]:.4f} | {rep["overall"]["wilson_recall_95"][0]:.3f} – {rep["overall"]["wilson_recall_95"][1]:.3f} |
| False-positive rate | {rep["overall"]["false_positive_rate"]:.4f} | {rep["overall"]["wilson_false_positive_rate_95"][0]:.3f} – {rep["overall"]["wilson_false_positive_rate_95"][1]:.3f} |
| Precision | {rep["overall"]["precision"]:.4f} | — |
| Evaluated targets | {rep["data"]["n_evaluated"]} / 144 | — |

**Per-stratum acceptance rates:**

| Stratum | n | accept rate | recall / FPR |
|---|---:|---:|---:|
| false_positive:APC | 19 | 0.947 | FPR = 0.947 |
| false_positive:FP  | 35 | 0.714 | FPR = 0.714 |
| false_positive:FA  | 10 | 0.300 | FPR = 0.300 |
| planet:CP          | 36 | 0.722 | recall = 0.722 |
| planet:KP          | 35 | 0.686 | recall = 0.686 |

**Interpretation.** The synthetic adversarial gate (FAZ 1) measured an
85.4% false-positive rejection rate on 48 fabricated eclipsing-binary
morphologies. On 54 real, disposition-labelled false positives drawn from
TFOP, the same pipeline rejects only 26.9%. The gap is not a threshold
issue: the accepted false positives and the accepted planets occupy the
same `quality_score` range (both median ≈ 75), so no single score cut
separates them.

The dominant leak family is **FP:APC** (ambiguous planet candidate,
18/19 accepted) and **FP:FP** (25/35 accepted) — real diluted eclipsing
binaries and blended signals. The synthetic adversarial corpus does not
represent their morphology, so the `secondary_eclipse_snr` and
`transit_shape` tests, calibrated on the synthetic grid, do not fire.

**No tuning on this set.** Per the frozen programme, thresholds are not
re-tuned against the blind holdout. The next algorithm iteration is
developed on the non-blind partitions and re-frozen before a second
blind run.

Report SHA-256: `57e60255b2c7bb229e9ea7d54941a7683b3e8bbe95cb5c5567727b204a446d61`.
"""

p = Path("docs/measured_validation_results.md")
t = p.read_text()
if "## Blind domain holdout v1" not in t:
    p.write_text(t.rstrip() + "\n" + section)
    print("  appended FAZ 2 section")
else:
    print("  section already present")
PY

# ---- 3) Stage and commit ----
echo
echo "########## 3) Stage & commit ##########"
git add \
  tests/test_blind_holdout.py \
  docs/validation_status.md \
  docs/measured_validation_results.md \
  validation_runs/final_acceptance_v1/blind_holdout/report.json \
  scripts/roadmap/phase2a_contract.sh \
  scripts/roadmap/phase2b_pilot.sh \
  scripts/roadmap/phase2b_full.sh \
  scripts/roadmap/phase2b_resume.sh \
  scripts/roadmap/phase2b_resume_v2.sh \
  scripts/roadmap/phase2b_resume_v3.sh \
  scripts/roadmap/phase2_diagnose.sh \
  scripts/roadmap/phase2_diagnose_v2.sh \
  scripts/roadmap/phase2_verify.sh \
  scripts/roadmap/phase2_commit.sh \
  2>/dev/null || true

echo "--- staged ---"
git diff --cached --stat | tail -20

cat > /tmp/faz2_commit_msg.txt <<'MSG'
validation(blind-holdout): first measurement of the 144-target corpus

Result: MEASURED, gate remains OPEN (two blockers).

Numbers
-------
  recall       0.7042  (95% CI 0.590 - 0.798)   >= 0.5  PASS
  FP rate      0.7188  (95% CI 0.599 - 0.814)   <= 0.6  FAIL
  precision    0.5208
  evaluated    135 / 144
  errors       9 (no SPOC 120s sector)

Per-stratum
-----------
  false_positive:APC   n=19  accept=0.947  (18/19)  <- worst
  false_positive:FP    n=35  accept=0.714  (25/35)
  false_positive:FA    n=10  accept=0.300  ( 3/10)
  planet:CP            n=36  recall=0.722  (26/36)
  planet:KP            n=35  recall=0.686  (24/35)

Scientific finding
------------------
The synthetic adversarial gate (FAZ 1) measured 85.4% FP rejection on
48 fabricated EB morphologies. On 54 real, disposition-labelled TESS
false positives the same pipeline rejects only 26.9%. The gap is not a
threshold artefact: accepted false positives and accepted planets share
the same quality_score distribution (median ≈ 75 each), so no single
score cut separates them. The dominant leak family is FP:APC (ambiguous
planet candidates, 18/19 accepted) and FP:FP (25/35 accepted). The
synthetic corpus does not represent their morphology.

No tuning on this set
---------------------
Per the frozen programme the blind holdout is an exam, not a training
set. No threshold is re-tuned against it. The next algorithm iteration
is developed on the non-blind partitions and re-frozen before a second
blind run (Blind v2).

Changes
-------
- tests/test_blind_holdout.py: the offline contract test now checks that
  the canonical gate output is *not overwritten* by a contract-only run
  (mtime comparison), instead of asserting its absence. The canonical
  file now exists because a real measurement published it.
- docs/validation_status.md, docs/measured_validation_results.md:
  record the blind holdout as MEASURED_OPEN with per-stratum numbers.
- validation_runs/final_acceptance_v1/blind_holdout/report.json:
  the frozen measurement artifact (SHA-256 57e60255...).
- scripts/roadmap/phase2*.sh: the reproducible tooling that produced it
  (contract check, pilot, full run, resume, diagnose, commit).
MSG

git "${GITID[@]}" commit -F /tmp/faz2_commit_msg.txt
COMMIT_EXIT=$?
echo "  commit exit=$COMMIT_EXIT"
[ $COMMIT_EXIT -eq 0 ] || exit 1

HASH=$(git rev-parse --short HEAD)
echo "  commit hash: $HASH"

# ---- 4) Pin hash in validation_status.md ----
echo
echo "########## 4) Pin hash ##########"
python - "$HASH" <<'PY'
import sys, re
from pathlib import Path
new = sys.argv[1]
p = Path("docs/validation_status.md")
t = p.read_text()
t2 = re.sub(r"\| Blind holdout \|[^\n]*?\| `[^`]*` \| `[^`]*` \|",
            lambda m: m.group(0).rsplit("|", 2)[0] + f"| `{new}` | `57e60255` |",
            t, count=1)
if t2 != t:
    p.write_text(t2)
    print(f"  pinned {new}")
else:
    print("  (no substitution — check row manually)")
PY

git add docs/validation_status.md
git "${GITID[@]}" commit -m "docs: pin blind holdout gate row to $HASH"
PIN_EXIT=$?
echo "  pin exit=$PIN_EXIT"

# ---- 5) Tag ----
echo
echo "########## 5) Tag v0.13.0-validation-rc4 ##########"
if git rev-parse --verify v0.13.0-validation-rc4 >/dev/null 2>&1; then
    echo "  tag already exists"
else
    git tag -a v0.13.0-validation-rc4 \
        -m "Validation RC4 — blind holdout measured, gate open (FPR 0.719 > 0.6)"
    echo "  created v0.13.0-validation-rc4"
fi

# ---- 6) Summary ----
echo
echo "########## 6) Summary ##########"
git --no-pager log -4 --format="%h %ad %s" --date=short
echo
echo "tags:"
git --no-pager tag --sort=-creatordate | head -3
echo
echo "working tree:"
if [ -z "$(git status --short)" ]; then
    echo "  clean ✅"
else
    git status --short | head -10
fi

echo
echo "== PHASE 2 COMMIT DONE =="
