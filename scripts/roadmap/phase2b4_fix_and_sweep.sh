#!/usr/bin/env bash
# FAZ 2b.4: (1) fix shards 4/5/8 corrupt parquet; (2) rule sweep on dev corpus.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b4_fixsweep_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 2b.4 fix + sweep =="
echo "log: $LOG"

S=$(cat /tmp/phase2b4_scratch 2>/dev/null)
echo "blind scratch: $S"

echo
echo "########## 1) Delete corrupt parquet for shards 4/5/8 ##########"
for i in 4 5 8; do
  pq="$S/out/$i/parquet/astrotransit_candidates.parquet"
  if [ -f "$pq" ]; then
    mv "$pq" "/tmp/corrupt_parquet_shard-$i.$(date +%s)" && echo "  moved $pq"
  fi
  csv="$S/out/$i/csv/astrotransit_candidates.csv"
  [ -f "$csv" ] && mv "$csv" "/tmp/corrupt_csv_shard-$i.$(date +%s)" && echo "  moved $csv"
done
echo "  cleanup done"

echo
echo "########## 2) Rule sweep on dev corpus (with new metrics) ##########"
python - <<'PY'
import json
from pathlib import Path
from collections import defaultdict

# Load ALL dev shards we have (from fixv4 partial + fixv3 complete)
scratches = [
    "outputs/dev-holdout-fixv4-20261010_163019",
    "outputs/dev-holdout-fixv3-20261010_100934",
]
rows = []
seen = set()
for s in scratches:
    shards = Path(s) / "shards"
    if not shards.exists(): continue
    for sp in sorted(shards.glob("shard-*.json")):
        try:
            d = json.loads(sp.read_text())
        except Exception:
            continue
        for r in d.get("rows", []):
            tid = r.get("target_id")
            if tid and tid not in seen:
                seen.add(tid)
                rows.append(r)
print(f"loaded {len(rows)} unique targets from dev scratches")

def label_of(r):
    return "planet" if str(r.get("stratum", "")).startswith("planet:") else "fp"

# Define alternative rules
def evaluate(name, accept_fn):
    tp=fn=fp=tn=0
    for r in rows:
        if r.get("error"): continue
        lab = label_of(r)
        ok = accept_fn(r)
        if lab == "planet":
            if ok: tp+=1
            else: fn+=1
        else:
            if ok: fp+=1
            else: tn+=1
    rec = tp/(tp+fn) if (tp+fn) else 0
    fpr = fp/(fp+tn) if (fp+tn) else 0
    ba = (rec + (1-fpr))/2
    print(f"  {name:55s} TP={tp:3d} FN={fn:3d} FP={fp:3d} TN={tn:3d}  "
          f"recall={rec:.3f} fpr={fpr:.3f} ba={ba:.3f}")

def any_sector(r, reject_fn):
    sectors = r.get("per_sector") or []
    if not sectors:
        return bool(r.get("accepted_candidate"))
    return any(not reject_fn(s) for s in sectors)

print()
print("="*78)
print("RULE SWEEP — alternative class gates")
print("="*78)

# Baseline
evaluate("[0] detection-level (cascade confirmed)",
         lambda r: bool(r.get("accepted_candidate")))

# Current rule: class in {C,D}
evaluate("[A] reject if class in {C,D}",
         lambda r: any_sector(r, lambda s: str(s.get("quality_class") or "").endswith(("C","D"))))

# Alternative B: only class D
evaluate("[B] reject if class == D",
         lambda r: any_sector(r, lambda s: str(s.get("quality_class") or "").endswith("D")))

# Alternative C: class in {C,D} AND sec_snr >= 5
evaluate("[C] reject if class in {C,D} AND sec_snr >= 5",
         lambda r: any_sector(r, lambda s:
             str(s.get("quality_class") or "").endswith(("C","D"))
             and (s.get("metric_secondary_eclipse_snr") or 0) >= 5))

# Alternative D: class in {C,D} AND n_fail >= 1
evaluate("[D] reject if class in {C,D} AND n_fail >= 1",
         lambda r: any_sector(r, lambda s:
             str(s.get("quality_class") or "").endswith(("C","D"))
             and (s.get("vetting_n_fail") or 0) >= 1))

# Alternative E: class == D OR (class == C AND n_fail >= 1)
evaluate("[E] reject if class==D OR (class==C AND n_fail>=1)",
         lambda r: any_sector(r, lambda s:
             str(s.get("quality_class") or "").endswith("D")
             or (str(s.get("quality_class") or "").endswith("C")
                 and (s.get("vetting_n_fail") or 0) >= 1)))

# Alternative F: class in {C,D} AND sec_snr >= 3
evaluate("[F] reject if class in {C,D} AND sec_snr >= 3",
         lambda r: any_sector(r, lambda s:
             str(s.get("quality_class") or "").endswith(("C","D"))
             and (s.get("metric_secondary_eclipse_snr") or 0) >= 3))

# Alternative G: class in {C,D} AND (n_fail>=1 OR sec_snr>=3)
evaluate("[G] reject if class in {C,D} AND (n_fail>=1 OR sec_snr>=3)",
         lambda r: any_sector(r, lambda s:
             str(s.get("quality_class") or "").endswith(("C","D"))
             and ((s.get("vetting_n_fail") or 0) >= 1
                  or (s.get("metric_secondary_eclipse_snr") or 0) >= 3)))

# Alternative H: is_false_positive OR rejected_by_class_D_only
evaluate("[H] reject if is_fp OR class == D",
         lambda r: any_sector(r, lambda s:
             bool(s.get("vetting_is_false_positive"))
             or str(s.get("quality_class") or "").endswith("D")))

# Alternative I: reject if score < 55 (Class D) OR (score < 75 AND n_fail>=1)
evaluate("[I] reject if class==D OR (class==C AND n_fail>=2)",
         lambda r: any_sector(r, lambda s:
             str(s.get("quality_class") or "").endswith("D")
             or (str(s.get("quality_class") or "").endswith("C")
                 and (s.get("vetting_n_fail") or 0) >= 2)))

# Print current class distribution for context
print()
print("="*78)
print("CLASS DISTRIBUTION by stratum")
print("="*78)
by_stratum = defaultdict(lambda: defaultdict(int))
for r in rows:
    if r.get("error"): continue
    s = r.get("stratum", "?")
    for sec in (r.get("per_sector") or []):
        c = sec.get("quality_class") or "?"
        by_stratum[s][c] += 1
print(f"  {'stratum':24s}  {'A':>3s}  {'B':>3s}  {'C':>3s}  {'D':>3s}")
for s in sorted(by_stratum):
    c = by_stratum[s]
    print(f"  {s:24s}  {c.get('A',0):>3d}  {c.get('B',0):>3d}  {c.get('C',0):>3d}  {c.get('D',0):>3d}")
PY

echo
echo "== DONE =="
