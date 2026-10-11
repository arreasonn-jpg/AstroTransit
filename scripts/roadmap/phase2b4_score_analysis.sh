#!/usr/bin/env bash
# FAZ 2b.4: compare score components dev vs blind for real planets.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase2b4_score_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== score component analysis =="

python - <<'PY'
import json
from pathlib import Path
from collections import defaultdict
import statistics as st

def load(scratches):
    rows, seen = [], set()
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
                    seen.add(tid); rows.append(r)
    return rows

dev_rows   = load(["outputs/dev-holdout-fixv4-20261010_163019",
                   "outputs/dev-holdout-fixv3-20261010_100934"])
blind_rows = load(["outputs/blind-holdout-v2-20261011_085204"])

print(f"dev: {len(dev_rows)} targets, blind: {len(blind_rows)} targets")

def stats_for(rows, stratum_prefix, label):
    """Average score components for one label group."""
    components = defaultdict(list)
    scores = []
    classes = defaultdict(int)
    for r in rows:
        if r.get("error"): continue
        if not str(r.get("stratum","")).startswith(stratum_prefix): continue
        for sec in (r.get("per_sector") or []):
            scores.append(sec.get("quality_score") or 0)
            classes[sec.get("quality_class") or "?"] += 1
            # Score components are not in per_sector. We need the score object.
            # But we do have access to raw values, not components. Let's use
            # what's there:
            # - candidate_snr_adopted, candidate_depth_ppm, candidate_duration_days
            # - metric_* values
            for k in ("candidate_snr_adopted", "candidate_depth_ppm",
                      "metric_odd_even_mismatch", "metric_transit_symmetry",
                      "metric_shape_correlation", "metric_depth_variance",
                      "metric_variability_amplitude_ppm"):
                v = sec.get(k)
                if v is not None:
                    components[k].append(float(v))
            components["data_completeness_proxy"].append(
                1.0 if sec.get("success") else 0.0
            )
    print(f"\n=== {label} — n_scores={len(scores)} ===")
    if scores:
        s = sorted(scores)
        print(f"  score: min={s[0]:.1f} med={s[len(s)//2]:.1f} max={s[-1]:.1f}")
    print(f"  classes: {dict(classes)}")
    for k, vals in sorted(components.items()):
        if not vals: continue
        s = sorted(vals)
        print(f"  {k:35s} n={len(vals):3d} med={s[len(s)//2]:10.2f} max={s[-1]:10.2f}")

print("\n" + "=" * 78)
print("PLANETS — dev vs blind")
print("=" * 78)
stats_for(dev_rows,   "planet:", "DEV planet")
stats_for(blind_rows, "planet:", "BLIND planet")

print("\n" + "=" * 78)
print("FALSE POSITIVES — dev vs blind")
print("=" * 78)
stats_for(dev_rows,   "false_positive:", "DEV fp")
stats_for(blind_rows, "false_positive:", "BLIND fp")

# Now: score distribution by class and label for blind
print("\n" + "=" * 78)
print("BLIND: scores by class for planets vs fp")
print("=" * 78)
by_class = defaultdict(lambda: {"planet": [], "fp": []})
for r in blind_rows:
    if r.get("error"): continue
    lab = "planet" if str(r.get("stratum","")).startswith("planet:") else "fp"
    for sec in (r.get("per_sector") or []):
        c = sec.get("quality_class") or "?"
        by_class[c][lab].append(sec.get("quality_score") or 0)
for c in sorted(by_class):
    p = sorted(by_class[c]["planet"])
    f = sorted(by_class[c]["fp"])
    def fmt(v):
        if not v: return "[]"
        return f"n={len(v)} med={v[len(v)//2]:.1f} max={v[-1]:.1f}"
    print(f"  class {c}: planets={fmt(p)}  fp={fmt(f)}")
PY

echo
echo "== DONE =="
