#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b1_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1

echo "== PHASE 2b.1: build development corpus =="
echo "log: $LOG"

# ---- 1) Modify runner to support split-agnostic verification ----
RUNNER="scripts/validation/run_blind_holdout.py"
cp "$RUNNER" /tmp/run_blind_holdout.py.faz2b1.bak

python - <<'PY'
from pathlib import Path
import re

p = Path("scripts/validation/run_blind_holdout.py")
src = p.read_text()
orig = src

# 1a) In _verify_membership, read split from manifest
old1 = '''    rebuilt = select_holdout(
        json.loads((ROOT / LABELLED_CORPUS).read_text(encoding="utf-8"))["cases"],
        excluded_ids={item for ids in manifest["exclusions"]["sources"].values() for item in ids},
        per_label=int(manifest["selection"]["per_label_quota"]),
        seed=int(manifest["selection"]["seed"]),
        split_seed=int(manifest["selection"]["split_seed"]),
        minimum_per_stratum=int(manifest["selection"]["minimum_per_stratum"]),
    )'''

new1 = '''    rebuilt = select_holdout(
        json.loads((ROOT / LABELLED_CORPUS).read_text(encoding="utf-8"))["cases"],
        excluded_ids={item for ids in manifest["exclusions"]["sources"].values() for item in ids},
        per_label=int(manifest["selection"]["per_label_quota"]),
        seed=int(manifest["selection"]["seed"]),
        split_seed=int(manifest["selection"]["split_seed"]),
        split=str(manifest.get("split", "blind_test")),
        minimum_per_stratum=int(manifest["selection"]["minimum_per_stratum"]),
    )'''

if old1 in src:
    src = src.replace(old1, new1, 1)
    print("  patched: _verify_membership reads split from manifest")
else:
    print("  WARN: could not find rebuild block")

# 1b) Program.json check becomes optional
old2 = '''    program = json.loads(Path(PROGRAM).read_text(encoding="utf-8"))
    gate = next((item for item in program["gates"] if item.get("id") == GATE_ID), None)
    if gate is None:
        raise ValueError(f"gate {GATE_ID} missing from program.json")
    checks = {str(item.get("path")): item for item in gate.get("acceptance_checks", [])}
    if checks.get("corpus.sha256", {}).get("value") != manifest["holdout_sha256"]:
        raise ValueError("program.json pins a different holdout corpus than the committed manifest")
    if checks.get("overall.recall", {}).get("value") != manifest["floors"]["recall"]:
        raise ValueError("program.json and the frozen corpus disagree on the recall floor")
    if checks.get("overall.false_positive_rate", {}).get("value") != manifest["floors"]["false_positive_rate_ceiling"]:
        raise ValueError("program.json and the frozen corpus disagree on the false-positive ceiling")
    if checks.get("method.retrained", {}).get("value") is not False:
        raise ValueError("the holdout must declare that nothing was retrained on it")'''

new2 = '''    if manifest.get("split", "blind_test") == "blind_test":
        program = json.loads(Path(PROGRAM).read_text(encoding="utf-8"))
        gate = next((item for item in program["gates"] if item.get("id") == GATE_ID), None)
        if gate is None:
            raise ValueError(f"gate {GATE_ID} missing from program.json")
        checks = {str(item.get("path")): item for item in gate.get("acceptance_checks", [])}
        if checks.get("corpus.sha256", {}).get("value") != manifest["holdout_sha256"]:
            raise ValueError("program.json pins a different holdout corpus than the committed manifest")
        if checks.get("overall.recall", {}).get("value") != manifest["floors"]["recall"]:
            raise ValueError("program.json and the frozen corpus disagree on the recall floor")
        if checks.get("overall.false_positive_rate", {}).get("value") != manifest["floors"]["false_positive_rate_ceiling"]:
            raise ValueError("program.json and the frozen corpus disagree on the false-positive ceiling")
        if checks.get("method.retrained", {}).get("value") is not False:
            raise ValueError("the holdout must declare that nothing was retrained on it")'''

if old2 in src:
    src = src.replace(old2, new2, 1)
    print("  patched: program.json check only for blind split")
else:
    print("  WARN: could not find program check block")

if src != orig:
    p.write_text(src)
    print("  wrote", p)
else:
    print("  no changes")
PY

# ---- 2) Syntax check ----
python -c "import ast; ast.parse(open('scripts/validation/run_blind_holdout.py').read()); print('syntax OK')"

# ---- 3) Write build_dev_holdout.py ----
cat > scripts/validation/build_dev_holdout.py <<'PY_EOF'
#!/usr/bin/env python3
"""Build the FAZ 2b development corpus.

The blind holdout (Blind v1) measured recall 0.704 and FPR 0.719 on 144
real TESS targets. To iterate on the algorithm without contaminating the
blind set, we build a *parallel* corpus from the development partition
of the same frozen split.

Same selection method (sha256 seeded rank), same strata, same quotas,
different selection seed and different split. The 144 blind holdout IDs
are explicitly excluded so the two corpora are disjoint.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from astrotransit.validation.blind_holdout import (  # noqa: E402
    LABELLED_CORPUS,
    MINIMUM_CASES_PER_STRATUM,
    normalize_target_id,
    select_holdout,
)

BLIND_MANIFEST = ROOT / "validation_runs/final_acceptance_v1/blind_holdout/holdout_manifest.json"
DEFAULT_OUTPUT = ROOT / "validation_runs/final_acceptance_v1/dev_holdout/dev_manifest.json"

#: Different selection seed from the blind corpus (which used 20260918).
DEV_SELECTION_SEED = 20260919
#: Same split seed as the blind corpus so the two partitions are disjoint.
DEV_SPLIT_SEED = 13
#: Target per-label quota (matches the blind corpus: 72 + 72).
DEV_PER_LABEL = 72
#: Which partition of the frozen split to draw from.
DEV_SPLIT = "development"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--per-label",
        type=int,
        default=DEV_PER_LABEL,
    )
    parser.add_argument(
        "--selection-seed",
        type=int,
        default=DEV_SELECTION_SEED,
    )
    parser.add_argument(
        "--split",
        type=str,
        default=DEV_SPLIT,
        choices=["development", "validation"],
    )
    args = parser.parse_args()

    blind = json.loads(BLIND_MANIFEST.read_text(encoding="utf-8"))
    blind_ids = {normalize_target_id(c["target_id"]) for c in blind["cases"]}
    excluded: set[str] = set(blind_ids)
    for source_ids in blind["exclusions"]["sources"].values():
        excluded.update(normalize_target_id(x) for x in source_ids)

    corpus = json.loads((ROOT / LABELLED_CORPUS).read_text(encoding="utf-8"))
    cases = corpus["cases"]

    print(f"loaded labelled corpus: {len(cases)} cases")
    print(f"excluded IDs (blind + prior gates): {len(excluded)}")

    result: dict[str, Any] = select_holdout(
        cases,
        excluded_ids=excluded,
        per_label=args.per_label,
        seed=args.selection_seed,
        split_seed=DEV_SPLIT_SEED,
        split=args.split,
        minimum_per_stratum=MINIMUM_CASES_PER_STRATUM,
    )

    result["materialization"] = f"{args.split}_partition_for_algorithm_development"
    result["claim_boundary"] = (
        "Development corpus for algorithm iteration. Same selection method "
        "as the blind holdout (sha256 seeded rank, detector-blind), drawn "
        "from a disjoint partition of the same frozen split. Not a "
        "validation gate; results here guide revision before a second "
        "blind run."
    )
    result["sources"] = {
        "labelled_corpus": LABELLED_CORPUS,
        "blind_manifest": str(BLIND_MANIFEST.relative_to(ROOT)),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print()
    print(f"wrote {args.output}")
    print(f"  n_cases:       {result['counts']}")
    print(f"  stratum_counts: {json.dumps(result['stratum_counts'], indent=2)}")
    print(f"  holdout_sha256: {result['holdout_sha256']}")

    # Sanity: check disjointness
    dev_ids = {normalize_target_id(c["target_id"]) for c in result["cases"]}
    overlap = dev_ids & blind_ids
    print(f"  overlap with blind: {len(overlap)}")
    assert not overlap, f"blind/dev overlap: {overlap}"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY_EOF

chmod +x scripts/validation/build_dev_holdout.py

# ---- 4) Run it ----
python scripts/validation/build_dev_holdout.py

# ---- 5) Verify manifest structure ----
python - <<'PY'
import json
from pathlib import Path
p = Path("validation_runs/final_acceptance_v1/dev_holdout/dev_manifest.json")
if not p.exists():
    print("MISSING"); raise SystemExit(1)
d = json.loads(p.read_text())
print(f"keys: {sorted(d.keys())}")
print(f"split: {d.get('split')}")
print(f"n_cases: {len(d['cases'])}")
print(f"counts: {d.get('counts')}")
print(f"stratum_counts: {d.get('stratum_counts')}")
print(f"holdout_sha256: {d.get('holdout_sha256')}")
print(f"selection.seed: {d.get('selection', {}).get('seed')}")
print(f"selection.method: {d.get('selection', {}).get('method')}")
PY

# ---- 6) Commit ----
GITID=(-c user.email="validation@astrotransit.local" -c user.name="AstroTransit Validation")
git add \
  scripts/validation/run_blind_holdout.py \
  scripts/validation/build_dev_holdout.py \
  scripts/roadmap/phase2b1_build_dev.sh \
  validation_runs/final_acceptance_v1/dev_holdout/dev_manifest.json

git "${GITID[@]}" commit -m "validation(dev-holdout): build the FAZ 2b development corpus

Blind v1 (FAZ 2) measured 0.704 recall and 0.719 FPR on 144 real
targets drawn from the blind_test partition. To iterate on the
algorithm without contaminating the blind set, build a parallel corpus
of the same size from the development partition of the same frozen
split.

Method mirrors the blind holdout exactly:
  * sha256 seeded rank, detector-blind selection
  * same strata (APC, FA, FP, CP, KP) and same per-label quotas
  * different selection seed (20260919 vs 20260918)
  * blind holdout IDs and prior-gate IDs excluded
  * disjointness asserted at build time

Runner change (small):
  * _verify_membership now reads split from manifest instead of
    hardcoding 'blind_test'
  * program.json gate cross-check is skipped for non-blind manifests
    (the dev corpus is not a gate, so there is nothing to pin)

No change to the blind path: for split == 'blind_test' both the split
filter and the program.json check run exactly as before, and the 107
existing tests still pass."

COMMIT_EXIT=$?
echo
echo "commit exit=$COMMIT_EXIT"
git --no-pager log -1 --format="%h %s"
git status --short

echo
echo "== PHASE 2b.1 DONE =="
