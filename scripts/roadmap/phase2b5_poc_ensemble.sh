#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase2b5_ens_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== ensemble ML POC =="

python - <<'PY'
import json
import numpy as np
from pathlib import Path
from collections import Counter
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import balanced_accuracy_score, make_scorer

rows = []
seen = set()
for S in ["outputs/dev-holdout-fixv4-20261010_163019",
          "outputs/dev-holdout-fixv3-20261010_100934"]:
    d = Path(S)
    if not d.exists(): continue
    for sp in sorted((d/"shards").glob("shard-*.json")):
        try:
            payload = json.loads(sp.read_text())
        except Exception:
            continue
        for r in payload.get("rows", []):
            tid = r.get("target_id")
            if not tid or tid in seen: continue
            seen.add(tid)
            for sec in (r.get("per_sector") or []):
                rows.append({
                    "stratum": r.get("stratum"),
                    "error": r.get("error"),
                    "candidate_snr_adopted": sec.get("candidate_snr_adopted"),
                    "candidate_depth_ppm": sec.get("candidate_depth_ppm"),
                    "candidate_duration_days": sec.get("candidate_duration_days"),
                    "metric_odd_even_mismatch": sec.get("metric_odd_even_mismatch"),
                    "metric_odd_even_harmonic": sec.get("metric_odd_even_harmonic"),
                    "metric_secondary_eclipse_depth_ppm": sec.get("metric_secondary_eclipse_depth_ppm"),
                    "metric_secondary_eclipse_snr": sec.get("metric_secondary_eclipse_snr"),
                    "metric_transit_symmetry": sec.get("metric_transit_symmetry"),
                    "metric_shape_correlation": sec.get("metric_shape_correlation"),
                    "metric_depth_variance": sec.get("metric_depth_variance"),
                    "metric_variability_amplitude_ppm": sec.get("metric_variability_amplitude_ppm"),
                    "metric_lomb_scargle_peak": sec.get("metric_lomb_scargle_peak"),
                    "vetting_fpp": sec.get("vetting_fpp"),
                })

print(f"rows: {len(rows)}")
rows = [r for r in rows if not r["error"] and r["stratum"]]

cols = ["candidate_snr_adopted", "candidate_depth_ppm",
        "candidate_duration_days", "metric_odd_even_mismatch",
        "metric_odd_even_harmonic", "metric_secondary_eclipse_depth_ppm",
        "metric_secondary_eclipse_snr", "metric_transit_symmetry",
        "metric_shape_correlation", "metric_depth_variance",
        "metric_variability_amplitude_ppm", "metric_lomb_scargle_peak",
        "vetting_fpp"]
X, y = [], []
for r in rows:
    feats = []
    for c in cols:
        v = r[c]
        try:
            feats.append(0.0 if v is None else float(v))
        except Exception:
            feats.append(0.0)
    X.append(feats)
    y.append(1 if r["stratum"].startswith("false_positive") else 0)
X = np.nan_to_num(np.array(X), nan=0.0, posinf=0.0, neginf=0.0)
X = np.clip(X, -1e9, 1e9)
y = np.array(y)
print(f"X: {X.shape}, classes: {dict(Counter(y))}")

cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

lr = make_pipeline(StandardScaler(),
                   LogisticRegression(max_iter=2000, class_weight="balanced"))
lr_auc = cross_val_score(lr, X, y, cv=cv, scoring="roc_auc")
lr_ba = cross_val_score(lr, X, y, cv=cv,
                        scoring=make_scorer(balanced_accuracy_score))
print(f"\nLogistic  AUC={lr_auc.mean():.4f}±{lr_auc.std():.4f}  BA={lr_ba.mean():.4f}")

rf = RandomForestClassifier(n_estimators=200, max_depth=6,
                            class_weight="balanced", random_state=42)
rf_auc = cross_val_score(rf, X, y, cv=cv, scoring="roc_auc")
rf_ba = cross_val_score(rf, X, y, cv=cv,
                        scoring=make_scorer(balanced_accuracy_score))
print(f"RForest   AUC={rf_auc.mean():.4f}±{rf_auc.std():.4f}  BA={rf_ba.mean():.4f}")

rf.fit(X, y)
print("\nFeature importance (RF):")
for name, imp in sorted(zip(cols, rf.feature_importances_), key=lambda x: -x[1]):
    print(f"  {name:42s}  {imp:.4f}")
PY
