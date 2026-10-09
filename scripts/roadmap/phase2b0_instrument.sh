#!/usr/bin/env bash
# FAZ 2b.0: Instrument the blind holdout runner.
# Adds per-sector vetting diagnostics to shard rows so we can see WHY
# false positives leak, without changing any decision logic.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b0_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== PHASE 2b.0: Instrument runner =="
echo "log: $LOG"

RUNNER="scripts/validation/run_blind_holdout.py"
cp "$RUNNER" /tmp/run_blind_holdout.py.faz2b0.bak
echo "backup: /tmp/run_blind_holdout.py.faz2b0.bak"

echo
echo "########## 0) Locate function ##########"
grep -n "def _evaluate_case\|^def run_shard" "$RUNNER" | head -5

echo
echo "########## 1) Patch _evaluate_case ##########"
python - <<'PY'
from pathlib import Path
import re

p = Path("scripts/validation/run_blind_holdout.py")
src = p.read_text()

pattern = re.compile(
    r'(def _evaluate_case\(case: dict\[str, Any\], orchestrator: Any, sector_client: Any\) -> dict\[str, Any\]:.*?)(?=\ndef )',
    re.DOTALL,
)
m = pattern.search(src)
if not m:
    print("FATAL: _evaluate_case not found")
    raise SystemExit(1)

old_lines = len(m.group(1).splitlines())
print(f"  found _evaluate_case ({old_lines} lines)")

new_body = '''def _evaluate_case(case: dict[str, Any], orchestrator: Any, sector_client: Any) -> dict[str, Any]:
    """Tek hedef: sektör seçimi → pipeline → kabul edilmiş aday var mı?

    FAZ 2b.0 instrumentation: persist the full vetting picture per sector,
    so a post-hoc diagnosis can see *which* test fired (or failed to fire)
    for the false positives that leak. This does not change any decision.
    """

    def _safe_float(v: Any) -> Optional[float]:
        if v is None:
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        if f != f or f in (float("inf"), float("-inf")):
            return None
        return f

    def _verdict_value(v: Any) -> str:
        return str(getattr(v, "value", v) or "")

    requested = [int(item) for item in case.get("sectors", []) or []]
    sector_source = "frozen_corpus"
    error = ""
    if not requested:
        sector_source = "lowest_available_spoc_120s_at_run"
        try:
            requested = list(sector_client.get_available_sectors(case["target_id"]))[:1]
        except Exception as exc:
            error = f"sector_lookup_failed:{type(exc).__name__}: {exc}"
    row = {
        "target_id": normalize_target_id(case["target_id"]),
        "label": case["label"],
        "stratum": case["stratum"],
        "requested_sectors": requested,
        "sector_source": sector_source,
        "successful_sector_count": 0,
        "accepted_candidate": None,
        "candidate_count": None,
        "error": error,
    }
    if not requested:
        row["error"] = error or "no_available_spoc_120s_sector"
        return row
    try:
        result = orchestrator.run_single(row["target_id"], sectors=requested)
        sectors = list(getattr(result, "sector_results", []) or [])
        confirmed = [item for item in sectors if getattr(item, "candidate_confirmed", False)]
        row["successful_sector_count"] = sum(1 for item in sectors if getattr(item, "success", False))
        row["candidate_count"] = len(sectors)
        row["accepted_candidate"] = bool(confirmed)

        per_sector: list[dict[str, Any]] = []
        for item in sectors:
            quality = getattr(item, "quality", None)
            candidate = getattr(item, "candidate", None)
            vetting = getattr(quality, "vetting", None) if quality else None
            metrics = getattr(quality, "metrics", None) if quality else None
            transit_m = getattr(metrics, "transit", None) if metrics else None
            stellar_m = getattr(metrics, "stellar", None) if metrics else None
            snr_o = getattr(quality, "snr", None) if quality else None
            score_o = getattr(quality, "score", None) if quality else None

            tests = []
            for t in (getattr(vetting, "tests", []) or []):
                tests.append({
                    "name": str(getattr(t, "name", "") or ""),
                    "verdict": _verdict_value(getattr(t, "verdict", "")),
                    "value": _safe_float(getattr(t, "value", None)),
                    "threshold": _safe_float(getattr(t, "threshold", None)),
                })

            sec_depth = getattr(stellar_m, "secondary_eclipse_depth", None) if stellar_m else None
            var_amp = getattr(stellar_m, "variability_amplitude", None) if stellar_m else None
            cand_depth = getattr(candidate, "depth", None) if candidate else None

            per_sector.append({
                "sector": getattr(item, "sector", None),
                "success": bool(getattr(item, "success", False)),
                "has_candidate": bool(getattr(item, "has_candidate", False)),
                "candidate_confirmed": bool(getattr(item, "candidate_confirmed", False)),
                "status": _verdict_value(getattr(item, "status", "")),
                "candidate_period_days": _safe_float(getattr(candidate, "period", None)) if candidate else None,
                "candidate_depth_ppm": (_safe_float(cand_depth) or 0.0) * 1e6 if cand_depth is not None else None,
                "candidate_duration_days": _safe_float(getattr(candidate, "duration", None)) if candidate else None,
                "candidate_snr_adopted": _safe_float(getattr(snr_o, "snr_adopted", None)) if snr_o else None,
                "quality_class": _verdict_value(getattr(score_o, "candidate_class", "")) if score_o else "",
                "quality_score": _safe_float(getattr(score_o, "total_score", None)) if score_o else None,
                "vetting_fpp": _safe_float(getattr(vetting, "false_positive_probability", None)) if vetting else None,
                "vetting_fpp_method": str(getattr(vetting, "fpp_method", "") or "") if vetting else "",
                "vetting_is_false_positive": bool(getattr(vetting, "is_false_positive", False)) if vetting else False,
                "vetting_n_pass": getattr(vetting, "n_pass", None) if vetting else None,
                "vetting_n_fail": getattr(vetting, "n_fail", None) if vetting else None,
                "vetting_n_warn": getattr(vetting, "n_warn", None) if vetting else None,
                "vetting_fp_flags": list(getattr(vetting, "fp_flags", []) or []) if vetting else [],
                "vetting_tests": tests,
                "metric_secondary_eclipse_depth_ppm": (_safe_float(sec_depth) or 0.0) * 1e6 if sec_depth is not None else None,
                "metric_secondary_eclipse_snr": _safe_float(getattr(stellar_m, "secondary_eclipse_snr", None)) if stellar_m else None,
                "metric_variability_amplitude_ppm": (_safe_float(var_amp) or 0.0) * 1e6 if var_amp is not None else None,
                "metric_lomb_scargle_peak": _safe_float(getattr(stellar_m, "lomb_scargle_peak", None)) if stellar_m else None,
                "metric_odd_even_mismatch": _safe_float(getattr(transit_m, "odd_even_mismatch", None)) if transit_m else None,
                "metric_odd_even_harmonic": _safe_float(getattr(transit_m, "odd_even_harmonic", None)) if transit_m else None,
                "metric_transit_symmetry": _safe_float(getattr(transit_m, "transit_symmetry", None)) if transit_m else None,
                "metric_shape_correlation": _safe_float(getattr(transit_m, "shape_correlation", None)) if transit_m else None,
                "metric_depth_variance": _safe_float(getattr(transit_m, "depth_variance", None)) if transit_m else None,
            })

        row["per_sector"] = per_sector
        row["quality_classes"] = [s["quality_class"] for s in per_sector]
        row["quality_scores"] = [s["quality_score"] for s in per_sector]
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row
'''

src2 = src[:m.start()] + new_body + src[m.end():]
p.write_text(src2)
print(f"  patched ({len(new_body.splitlines())} lines)")
PY

echo
echo "########## 2) Ensure Optional is imported ##########"
python - <<'PY'
from pathlib import Path
import re
p = Path("scripts/validation/run_blind_holdout.py")
src = p.read_text()
m = re.search(r"^from typing import ([^\n]+)$", src, flags=re.M)
if m:
    names = [n.strip() for n in m.group(1).split(",")]
    if "Optional" not in names:
        names = ["Optional"] + names
        src = src[:m.start()] + f"from typing import {', '.join(names)}" + src[m.end():]
        p.write_text(src)
        print("  added Optional")
    else:
        print("  Optional already present")
else:
    print("  WARN: no 'from typing import' line found")
PY
grep -n "^from typing import" "$RUNNER" | head -2

echo
echo "########## 3) Syntax + import check ##########"
python -c "import ast; ast.parse(open('scripts/validation/run_blind_holdout.py').read()); print('  syntax OK')"
python scripts/validation/run_blind_holdout.py --help 2>&1 | head -3

echo
echo "########## 4) Full test suite (target files) ##########"
python -m pytest tests/test_blind_holdout.py tests/test_validation_blind_holdout_full.py -q 2>&1 | tail -6

echo
echo "########## 5) Diffstat ##########"
git --no-pager diff --stat "$RUNNER"

echo
echo "########## 6) Commit ##########"
GITID=(-c user.email="validation@astrotransit.local" -c user.name="AstroTransit Validation")
git add "$RUNNER"
git "${GITID[@]}" commit -m "instrument(blind-holdout): persist per-sector vetting detail

FAZ 2b.0. The runner saved only 11 top-level fields per target
(accepted_candidate, quality_classes, quality_scores, ...), so the
blind-holdout v1 result (APC accepted 18/19) could not be explained
from the artifact itself: no fp_flags, no fpp, no per-test values.

This commit adds a per_sector list to each row with:
  * candidate_period_days, candidate_depth_ppm, candidate_duration_days
  * candidate_snr_adopted
  * quality_class, quality_score
  * vetting_fpp, vetting_is_false_positive, vetting_n_pass/fail/warn
  * vetting_fp_flags, vetting_tests [{name, verdict, value, threshold}]
  * metric_secondary_eclipse_depth_ppm / _snr
  * metric_odd_even_mismatch / _harmonic
  * metric_transit_symmetry, metric_shape_correlation, metric_depth_variance
  * metric_variability_amplitude_ppm, metric_lomb_scargle_peak

No decision rule changes. The accept/reject outcome is byte-identical to
before; the new fields are additive and consumed only by diagnosis."
COMMIT_EXIT=$?
echo "  commit exit=$COMMIT_EXIT"

git --no-pager log -1 --format="%h %s"

echo
echo "########## 7) Working tree ##########"
git status --short | head -10

echo
echo "== PHASE 2b.0 DONE =="
