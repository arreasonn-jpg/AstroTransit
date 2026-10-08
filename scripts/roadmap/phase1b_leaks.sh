#!/usr/bin/env bash
# PHASE 1B: leak diagnostics (read-only). No writes.
set -uo pipefail
REPO="$HOME/AstroTransit"
cd "$REPO" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase1b_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1

echo "=== PHASE 1B: leak diagnostics ==="
echo "Log: $LOG"

python - <<'PY'
import json
from pathlib import Path
from collections import Counter, defaultdict

scratch_dirs = sorted(Path("outputs").glob("adv-fp-regen-*/shards"))
if not scratch_dirs:
    print("No scratch dir"); raise SystemExit(1)
shards_dir = scratch_dirs[-1]
print(f"Reading: {shards_dir}")

all_rows = []
for sp in sorted(shards_dir.glob("shard-*.json")):
    d = json.loads(sp.read_text())
    if isinstance(d, list):
        all_rows.extend(d)
    elif isinstance(d, dict):
        for key in ("rows", "scenarios", "results"):
            if isinstance(d.get(key), list):
                all_rows.extend(d[key]); break
        else:
            all_rows.append(d)
print(f"Loaded {len(all_rows)} rows")

adv = [r for r in all_rows if r.get("family") != "planetary_control"]
leaks = [r for r in adv if r.get("outcome") == "leaked_as_candidate"]
rejects = [r for r in adv if r.get("outcome") != "leaked_as_candidate"]
print(f"Adversarial: {len(adv)} (leaks={len(leaks)}, rejects={len(rejects)})")

def show_row(r, indent="  "):
    for k in [
        "scenario_id", "family",
        "injected_period_days", "detected_period_days",
        "period_within_tolerance",
        "candidate_confirmed", "cascade_status",
        "n_fail", "n_warn", "fpp",
        "odd_even_mismatch", "secondary_eclipse_depth_ppm",
        "transit_symmetry", "depth_variance",
        "quality_class", "quality_score",
        "injected_depth_ppm", "fp_flags",
    ]:
        print(f"{indent}{k:35s} {r.get(k)}")

print()
print("=" * 78)
print("ALL LEAKS:")
for r in leaks:
    print("-" * 78)
    show_row(r)

print()
print("=" * 78)
for label, group in (("LEAKS", leaks), ("REJECTS", rejects)):
    fc = Counter()
    for r in group:
        for f in (r.get("fp_flags") or []):
            fc[f] += 1
    print(f"FP_FLAG PATTERN ({label}):")
    for k, v in fc.most_common():
        print(f"  {k:35s} {v}")
    print()

print("n_fail distribution (leaks):", dict(sorted(Counter(r.get('n_fail') for r in leaks).items())))
print("n_fail distribution (rejects):", dict(sorted(Counter(r.get('n_fail') for r in rejects).items())))
print()
print("FPP (leaks):", sorted([r.get('fpp') for r in leaks if r.get('fpp') is not None]))
print("FPP (rejects):", sorted([r.get('fpp') for r in rejects if r.get('fpp') is not None]))

print()
print("=" * 78)
print("PER-FAMILY COMPARISON:")
by_fam = defaultdict(lambda: {"leaks": [], "rejects": []})
for r in adv:
    k = "leaks" if r.get("outcome") == "leaked_as_candidate" else "rejects"
    by_fam[r.get("family")][k].append(r)
for fam in sorted(by_fam):
    L = by_fam[fam]["leaks"]; R = by_fam[fam]["rejects"]
    print(f"\n--- {fam} --- (leaks={len(L)}, rejects={len(R)})")
    if L:
        print(f"  leak  n_fail: {[r.get('n_fail') for r in L]}")
        print(f"  leak  fpp:    {[r.get('fpp') for r in L]}")
        print(f"  leak  flags:  {[r.get('fp_flags') for r in L]}")
        print(f"  leak  period: {[r.get('injected_period_days') for r in L]}")
    if R:
        print(f"  rej   n_fail: {[r.get('n_fail') for r in R]}")
        print(f"  rej   fpp:    {[r.get('fpp') for r in R]}")

print()
print("=" * 78)
print("Metric ranges (leaks vs rejects):")
for metric in ("odd_even_mismatch", "secondary_eclipse_depth_ppm",
               "transit_symmetry", "depth_variance", "quality_score"):
    l = sorted(r.get(metric) for r in leaks   if r.get(metric) is not None)
    z = sorted(r.get(metric) for r in rejects if r.get(metric) is not None)
    print(f"  {metric}:")
    print(f"    leaks:   {l}")
    print(f"    rejects: {z[:10]}{' ... ' + str(z[-5:]) if len(z) > 15 else ''}")
PY

echo
echo "=== PHASE 1B DONE ==="
