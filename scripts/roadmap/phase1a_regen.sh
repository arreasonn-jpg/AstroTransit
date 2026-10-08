#!/usr/bin/env bash
# PHASE 1A: Regenerate stale rows.jsonl + verify 38/48 reproduces.
# Backs up frozen artifacts before any write. Uses the CI commands verbatim.

set -uo pipefail
REPO="$HOME/AstroTransit"
cd "$REPO" || { echo "FATAL: $REPO missing"; exit 1; }
source .venv/bin/activate || { echo "FATAL: .venv activate"; exit 1; }

LOG="$HOME/phase1a_regen_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

echo "=========================================="
echo " PHASE 1A: Regenerate adversarial FP rows"
echo " Log: $LOG"
echo "=========================================="

echo
echo "########## 1) Runner --help ##########"
python scripts/validation/run_adversarial_fp_controls.py --help 2>&1 | head -40 || true

echo
echo "########## 2) run --help ##########"
python scripts/validation/run_adversarial_fp_controls.py run --help 2>&1 | head -60 || true

echo
echo "########## 3) run-shard --help ##########"
python scripts/validation/run_adversarial_fp_controls.py run-shard --help 2>&1 | head -60 || true

echo
echo "########## 4) aggregate --help ##########"
python scripts/validation/run_adversarial_fp_controls.py aggregate --help 2>&1 | head -60 || true

echo
echo "########## 5) Back up frozen artifacts ##########"
BACKUP="validation_runs/final_acceptance_v1/adversarial_fp/frozen_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP"
cp validation_runs/final_acceptance_v1/adversarial_fp/report.json "$BACKUP/report.json" && echo "  report.json → $BACKUP/"
cp validation_runs/final_acceptance_v1/adversarial_fp/rows.jsonl   "$BACKUP/rows.jsonl"   && echo "  rows.jsonl  → $BACKUP/"
echo "  backup dir: $BACKUP"
echo "$BACKUP" > /tmp/phase1a_backup_dir

echo
echo "########## 6) Run full grid via 8 parallel shards ##########"
SCRATCH="outputs/adv-fp-regen-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$SCRATCH/shards" "$SCRATCH/logs"
echo "  scratch: $SCRATCH"
echo "$SCRATCH" > /tmp/phase1a_scratch_dir

START=$(date +%s)
for i in 0 1 2 3 4 5 6 7; do
  (python scripts/validation/run_adversarial_fp_controls.py run-shard \
      --corpus-manifest validation_runs/final_acceptance_v1/adversarial_fp/corpus_manifest.json \
      --config configs/benchmark_fp.toml \
      --shard-index "$i" \
      --shard-count 8 \
      --output "$SCRATCH/shards/shard-$(printf '%02d' "$i").json" \
      > "$SCRATCH/logs/shard-$i.log" 2>&1; echo "$?" > "$SCRATCH/logs/shard-$i.exit") &
done
wait
END=$(date +%s)
echo "  all shards done in $((END-START)) seconds"

echo
echo "########## 7) Shard exit codes + tails ##########"
FAIL=0
for i in 0 1 2 3 4 5 6 7; do
  ec=$(cat "$SCRATCH/logs/shard-$i.exit" 2>/dev/null || echo "?")
  [ "$ec" != "0" ] && FAIL=$((FAIL+1))
  echo "--- shard-$i exit=$ec ---"
  tail -8 "$SCRATCH/logs/shard-$i.log" || true
done
echo "  total failed shards: $FAIL"

echo
echo "########## 8) Inspect shard output format ##########"
python - "$SCRATCH" <<'PY'
import json, sys
from pathlib import Path
scratch = Path(sys.argv[1])
shards = sorted((scratch / "shards").glob("shard-*.json"))
print(f"shard files: {len(shards)}")
for sp in shards[:1]:
    d = json.loads(sp.read_text())
    print(f"{sp.name} type: {type(d).__name__}")
    if isinstance(d, dict):
        print("  keys:", sorted(d.keys())[:20])
        for k in d:
            v = d[k]
            if isinstance(v, list):
                print(f"  {k}: list[{len(v)}]")
                if v and isinstance(v[0], dict):
                    print(f"    first-item keys: {sorted(v[0].keys())[:20]}")
            elif isinstance(v, dict):
                print(f"  {k}: dict{{{len(v)}}}")
            else:
                print(f"  {k}: {v}")
    elif isinstance(d, list):
        print(f"  list of {len(d)} items")
        if d and isinstance(d[0], dict):
            print(f"    first-item keys: {sorted(d[0].keys())[:20]}")
PY

echo
echo "########## 9) Aggregate ##########"
python scripts/validation/run_adversarial_fp_controls.py aggregate \
    --corpus-manifest validation_runs/final_acceptance_v1/adversarial_fp/corpus_manifest.json \
    --shard "$SCRATCH/shards" \
    --output "$SCRATCH/report.json" || echo "  aggregate FAILED"

echo
echo "########## 10) Compare fresh vs frozen ##########"
python - "$SCRATCH/report.json" <<'PY'
import json, sys
from pathlib import Path
fresh_p = Path(sys.argv[1])
frozen_p = Path("validation_runs/final_acceptance_v1/adversarial_fp/report.json")
if not fresh_p.exists():
    print("fresh report missing"); raise SystemExit
fresh = json.loads(fresh_p.read_text())
frozen = json.loads(frozen_p.read_text())

for label, rep in [("FRESH", fresh), ("FROZEN", frozen)]:
    print(f"=== {label} ===")
    print("  status:", rep.get("status"))
    ov = rep.get("overall", {})
    print(f"  rejection: {ov.get('adversarial_rejected')}/{ov.get('adversarial_scenarios')} = {ov.get('adversarial_rejection_rate')}")
    print(f"  control:   {ov.get('control_accepted')}/{ov.get('control_scenarios')} = {ov.get('control_acceptance_rate')}")
    print("  by-stage:", json.dumps(ov.get("adversarial_rejected_by_stage", {})))
    print("  blocking:", rep.get("blocking_reasons"))
    print("  family rejection rates:")
    for fam, blk in sorted(rep.get("families", {}).items()):
        if blk.get("expected") == "false_positive":
            print(f"    {fam:35s} n={blk.get('n_evaluated')} rate={blk.get('rejection_rate')}")
    print()
f_r = fresh["overall"]["adversarial_rejected"]
z_r = frozen["overall"]["adversarial_rejected"]
print(f"=== MATCH: fresh={f_r}/48 frozen={z_r}/48 → {'YES' if f_r == z_r else 'NO'} ===")
PY

echo
echo "########## 11) If fresh report exists, build fresh rows.jsonl from shards ##########"
python - "$SCRATCH" <<'PY'
import json, sys
from pathlib import Path
scratch = Path(sys.argv[1])
shards = sorted((scratch / "shards").glob("shard-*.json"))
if not shards:
    print("no shards"); raise SystemExit
# Detect structure: shard may be {rows:[...]}, [...] , or single row
all_rows = []
for sp in shards:
    d = json.loads(sp.read_text())
    if isinstance(d, list):
        all_rows.extend(d)
    elif isinstance(d, dict):
        if "rows" in d and isinstance(d["rows"], list):
            all_rows.extend(d["rows"])
        elif "scenarios" in d and isinstance(d["scenarios"], list):
            all_rows.extend(d["scenarios"])
        else:
            all_rows.append(d)
print(f"collected {len(all_rows)} rows from {len(shards)} shards")
if all_rows:
    out = scratch / "rows.jsonl"
    with out.open("w") as fh:
        for r in all_rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    print(f"wrote {out}")
    # Sanity: outcome distribution
    from collections import Counter
    print("outcome distribution:")
    for k, v in sorted(Counter(str(r.get("outcome")) for r in all_rows).items()):
        print(f"  {k:35s} {v}")
PY

echo
echo "=========================================="
echo " PHASE 1A complete."
echo " Log: $LOG"
echo "=========================================="
