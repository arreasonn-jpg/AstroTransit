#!/usr/bin/env bash
# PHASE 1A RECOVERY: unstick parent, aggregate existing shards, compare vs frozen.
# The 8 shard JSONs are already on disk; we do NOT re-run them.

set -uo pipefail
REPO="$HOME/AstroTransit"
cd "$REPO" || { echo "FATAL: $REPO missing"; exit 1; }
source .venv/bin/activate || { echo "FATAL: .venv activate"; exit 1; }

LOG="$HOME/phase1a_recover_$(date +%Y%m%d_%H%M%S).log"
# IMPORTANT: file redirect only — no tee, no pipe to terminal.
exec >>"$LOG" 2>&1

echo "=========================================="
echo " PHASE 1A RECOVERY"
echo " Log: $LOG"
echo "=========================================="

# ---------- Step 1: unstick the stuck parent ----------
echo
echo "########## 1) Unstick parent bash + tee ##########"
PARENT_BASH=$(pgrep -f "phase1a_regen.sh" || true)
PARENT_TEE=$(pgrep -f "tee -a /home/erdem/phase1a_regen_" || true)
echo "stuck bash: ${PARENT_BASH:-none}"
echo "stuck tee : ${PARENT_TEE:-none}"
for pid in $PARENT_BASH $PARENT_TEE; do
  if kill -0 "$pid" 2>/dev/null; then
    echo "  TERM pid=$pid"
    kill -TERM "$pid" 2>/dev/null || true
  fi
done
sleep 2
for pid in $PARENT_BASH $PARENT_TEE; do
  if kill -0 "$pid" 2>/dev/null; then
    echo "  still alive, KILL pid=$pid"
    kill -KILL "$pid" 2>/dev/null || true
  fi
done
echo "  done."

# ---------- Step 2: locate scratch + frozen backup ----------
echo
echo "########## 2) Locate scratch + backup ##########"
SCRATCH=$(ls -td "$REPO/outputs/adv-fp-regen-"* 2>/dev/null | head -1 || true)
BACKUP=$(ls -td "$REPO/validation_runs/final_acceptance_v1/adversarial_fp/frozen_"* 2>/dev/null | head -1 || true)
echo "scratch: $SCRATCH"
echo "backup : $BACKUP"
if [ -z "$SCRATCH" ] || [ ! -d "$SCRATCH/shards" ]; then
  echo "FATAL: no shard dir"; exit 1
fi
SHARDS=$(ls "$SCRATCH/shards/shard-"?*.json 2>/dev/null | sort)
N_SHARDS=$(echo "$SHARDS" | wc -l)
echo "shard files: $N_SHARDS"
for s in $SHARDS; do echo "  $s ($(wc -c <"$s") bytes)"; done

# ---------- Step 3: aggregate with correct --shard syntax ----------
echo
echo "########## 3) Aggregate (explicit file list, NOT dir) ##########"
FRESH_REPORT="$SCRATCH/report.json"
python scripts/validation/run_adversarial_fp_controls.py aggregate \
    --corpus-manifest validation_runs/final_acceptance_v1/adversarial_fp/corpus_manifest.json \
    --shard $SHARDS \
    --output "$FRESH_REPORT"
echo "exit=$?"
[ -f "$FRESH_REPORT" ] && echo "fresh report: $(wc -c <"$FRESH_REPORT") bytes" || echo "FRESH REPORT MISSING"

# ---------- Step 4: compare fresh vs frozen ----------
echo
echo "########## 4) FRESH vs FROZEN ##########"
python - "$FRESH_REPORT" "$BACKUP/report.json" <<'PY'
import json, sys
from pathlib import Path
fp = Path(sys.argv[1]); zp = Path(sys.argv[2])
if not fp.exists():
    print("fresh missing"); raise SystemExit
fresh = json.loads(fp.read_text())
frozen = json.loads(zp.read_text()) if zp.exists() else {}
def show(label, rep):
    print(f"=== {label} ===")
    if not rep:
        print("  (missing)"); return
    ov = rep.get("overall", {})
    print("  status:", rep.get("status"))
    print(f"  rejection: {ov.get('adversarial_rejected')}/{ov.get('adversarial_scenarios')} = {ov.get('adversarial_rejection_rate')}")
    print(f"  control:   {ov.get('control_accepted')}/{ov.get('control_scenarios')} = {ov.get('control_acceptance_rate')}")
    print("  by stage:", json.dumps(ov.get("adversarial_rejected_by_stage", {})))
    print("  blocking:", rep.get("blocking_reasons"))
    print("  per-family rejection (adversarial only):")
    for fam, blk in sorted(rep.get("families", {}).items()):
        if blk.get("expected") == "false_positive":
            print(f"    {fam:35s} n={blk.get('n_evaluated')} rate={blk.get('rejection_rate')}")
    print()
show("FRESH", fresh)
show("FROZEN", frozen)
fr = fresh.get("overall", {}).get("adversarial_rejected")
zr = frozen.get("overall", {}).get("adversarial_rejected") if frozen else None
print(f"=== MATCH: fresh={fr}/48 frozen={zr}/48 -> {'YES' if fr == zr else 'NO'} ===")
PY

# ---------- Step 5: write fresh rows.jsonl ----------
echo
echo "########## 5) Reconstruct rows.jsonl from shards ##########"
python - "$SCRATCH" <<'PY'
import json, sys
from pathlib import Path
scratch = Path(sys.argv[1])
shards = sorted((scratch/"shards").glob("shard-?*.json"))
all_rows = []
for sp in shards:
    d = json.loads(sp.read_text())
    if isinstance(d, list):
        all_rows.extend(d)
    elif isinstance(d, dict):
        if isinstance(d.get("rows"), list):
            all_rows.extend(d["rows"])
        elif isinstance(d.get("scenarios"), list):
            all_rows.extend(d["scenarios"])
        elif isinstance(d.get("results"), list):
            all_rows.extend(d["results"])
        else:
            all_rows.append(d)
print(f"collected {len(all_rows)} rows")
if all_rows:
    out = scratch/"rows.jsonl"
    with out.open("w") as fh:
        for r in all_rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    print(f"wrote {out}")
    from collections import Counter
    print("outcome distribution:")
    for k, v in sorted(Counter(str(r.get("outcome")) for r in all_rows).items()):
        print(f"  {k:35s} {v}")
    print()
    print("family x outcome:")
    for (fam, out_), n in sorted(Counter((str(r.get("family")), str(r.get("outcome"))) for r in all_rows).items()):
        print(f"  {fam:32s} {out_:35s} {n}")
PY

# ---------- Step 6: sanity-check the log tail of the stuck parent ----------
echo
echo "########## 6) Last 20 lines of stuck parent's log ##########"
STUCK_LOG=$(ls -t /home/erdem/phase1a_regen_*.log 2>/dev/null | head -1 || true)
echo "log: $STUCK_LOG"
[ -n "$STUCK_LOG" ] && tail -20 "$STUCK_LOG" || echo "(none)"

# ---------- Step 7: state summary ----------
echo
echo "########## 7) Where we are ##########"
echo "fresh report : $FRESH_REPORT"
echo "fresh rows   : $SCRATCH/rows.jsonl"
echo "frozen backup: $BACKUP"
echo
echo "=== RECOVERY COMPLETE ==="
echo "Log: $LOG"
