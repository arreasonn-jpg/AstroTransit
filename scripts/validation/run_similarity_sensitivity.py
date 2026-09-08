"""Run the Gate-7 Earth-similarity weight-sensitivity experiment.

``astrotransit.validation.sensitivity.earth_similarity_sensitivity`` already
implements the designed experiment (deterministic ±weight perturbations,
Kendall tau, top-k overlap). This script closes the loop that the validation
roadmap flagged as "skeleton exists, run missing": it feeds a *real* candidate
catalog (``benchmarks/toi_catalog.csv`` — TOI records with photometric planet
parameters) through the scorer, applies the ±10/20% weight perturbations, and
freezes the measured result into an immutable JSON report with provenance.

Derived quantities (standard stellar/planet relations, albedo 0):

    a [AU]        = (P[yr]^2 * M_star[M_sun])^(1/3)          (Kepler III)
    L/L_sun       = (R_star[R_sun])^2 * (T_eff/5772.4 K)^4
    S_earth       = (L/L_sun) / a[AU]^2
    T_eq [K]      = T_eff * sqrt(R_star[R_sun] * 0.00465047 / (2 a[AU]))

Limitations recorded in the report (do not read past them):

* This measures *ranking stability* of the heuristic weight choice on a TOI
  candidate pool. It is not a calibration of absolute similarity scores and
  it is not a habitability claim.
* The TOI catalog carries no planetary masses or densities, so the
  ``strict_earth_twin`` profile is evaluated on its available dimensions only
  (its classification stays ``INCOMPLETE_EARTH_TWIN``); the
  ``photometric_earth_analog`` profile is the primary ranking profile for
  photometric-only data.
* ``tfopwg_disp`` designations in the catalog are independent-program labels
  and are NOT used to score or weight any result here.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from astrotransit import __version__
from astrotransit.science.earth_similarity import score_earth_similarity
from astrotransit.validation.provenance import build_manifest, canonical_hash
from astrotransit.validation.sensitivity import earth_similarity_sensitivity

REPORT_ID = "similarity_sensitivity_v1"
PROFILES = ("photometric_earth_analog", "strict_earth_twin")
FRACTIONS = (0.10, 0.20)
TOP_K = 10
TAU_STABILITY_THRESHOLD = 0.9
SUN_TEFF_K = 5772.4
RSUN_TO_AU = 0.00465047


def load_candidates(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Load finite, positive photometric candidates from the TOI catalog."""
    rows: list[dict[str, float]] = []
    total = 0
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for record in csv.DictReader(handle):
            total += 1
            try:
                radius = float(record["pl_rade"])
                period_days = float(record["pl_orbper"])
                teff = float(record["st_teff"])
                r_star = float(record["st_rad"])
                m_star = float(record["st_mass_est"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (radius > 0 and period_days > 0 and teff > 0 and r_star > 0 and m_star > 0):
                continue
            a_au = ((period_days / 365.25) ** 2 * m_star) ** (1.0 / 3.0)
            luminosity = r_star**2 * (teff / SUN_TEFF_K) ** 4
            insolation = luminosity / a_au**2
            equilibrium_temperature = teff * math.sqrt(RSUN_TO_AU * r_star / (2.0 * a_au))
            rows.append({
                "toi": str(record.get("toi", "")).strip(),
                "radius": radius,
                "insolation": insolation,
                "equilibrium_temperature": equilibrium_temperature,
                "semi_major_axis": a_au,
                "host_teff": teff,
            })
    if not rows:
        raise SystemExit(f"No usable candidates in {path}")
    return rows, total


def baseline_top_k(candidates: list[dict[str, Any]], profile: str, top_k: int) -> list[dict[str, Any]]:
    scored = []
    for candidate in candidates:
        parameters = {
            "planet_radius_rearth": candidate["radius"],
            "insolation_s_earth": candidate["insolation"],
            "equilibrium_temperature_k": candidate["equilibrium_temperature"],
            "semi_major_axis_au": candidate["semi_major_axis"],
            "stellar_teff_k": candidate["host_teff"],
        }
        scored.append(
            (candidate["toi"], float(score_earth_similarity(profile, **parameters).score_p50))
        )
    ranked = sorted(scored, key=lambda item: item[1], reverse=True)
    return [
        {"index": position, "toi": toi, "score": round(score, 4)}
        for position, (toi, score) in enumerate(ranked[:top_k], start=1)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=Path("benchmarks/toi_catalog.csv"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/results/similarity_sensitivity_v1.json"),
    )
    parser.add_argument("--top-k", type=int, default=TOP_K)
    args = parser.parse_args()

    start = time.time()
    candidates, total_rows = load_candidates(args.input)
    profile_blocks: dict[str, Any] = {}
    for profile in PROFILES:
        cells = {}
        for fraction in FRACTIONS:
            report = earth_similarity_sensitivity(
                candidates, profile=profile, perturbation_fraction=fraction, top_k=args.top_k
            )
            tau_min = report.kendall_tau_min
            verdict = (
                "ranking_stable"
                if tau_min is not None and tau_min >= TAU_STABILITY_THRESHOLD
                else "weight_sensitive"
            )
            cells[f"{fraction:.2f}"] = {
                "n_candidates": report.n_candidates,
                "n_perturbations": report.n_perturbations,
                "kendall_tau_min": tau_min,
                "kendall_tau_median": report.kendall_tau_median,
                "top_k_overlap_min": report.top_k_overlap_min,
                "verdict": verdict,
            }
        profile_blocks[profile] = {
            "perturbation_fraction": cells,
            "overall_verdict": (
                "ranking_stable"
                if all(cell["verdict"] == "ranking_stable" for cell in cells.values())
                else "weight_sensitive"
            ),
            "baseline_top_k": baseline_top_k(candidates, profile, args.top_k),
        }
    profile_blocks["photometric_earth_analog"]["input_limitations"] = [
        "planet_mass_mearth not in TOI catalog; mass/density dimensions unavailable",
    ]
    profile_blocks["strict_earth_twin"]["input_limitations"] = [
        "planet_mass_mearth and density_gcm3 not in TOI catalog; required dimensions "
        "missing, classification remains INCOMPLETE_EARTH_TWIN",
        "ranking measured over available dimensions only (radius, insolation, "
        "equilibrium_temperature, semi_major_axis, host_teff)",
    ]

    config = {
        "report_id": REPORT_ID,
        "profiles": list(PROFILES),
        "fractions": list(FRACTIONS),
        "top_k": args.top_k,
        "tau_stability_threshold": TAU_STABILITY_THRESHOLD,
    }
    payload = {
        "report_id": REPORT_ID,
        "experiment": "earth_similarity_weight_sensitivity",
        "gate": "docs/validation.md — Gate 7 (Earth-similarity sensitivity)",
        "command": "python scripts/validation/run_similarity_sensitivity.py "
        f"--input {args.input} --output {args.output}",
        "input": {
            "path": str(args.input),
            "sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
            "n_rows_total": total_rows,
            "n_candidates_used": len(candidates),
            "filters": "finite positive pl_rade, pl_orbper, st_teff, st_rad, st_mass_est",
            "derived_quantities": {
                "semi_major_axis_au": "(P[yr]^2 * M_star)^(1/3)",
                "insolation_s_earth": "(L/L_sun) / a^2; L/L_sun = R_star^2 * (Teff/5772.4)^4",
                "equilibrium_temperature_k": "Teff * sqrt(R_star * 0.00465047 / (2 a)), albedo 0",
            },
        },
        "tau_stability_threshold": TAU_STABILITY_THRESHOLD,
        "decision_rule": (
            f"kendall_tau_min < {TAU_STABILITY_THRESHOLD} => 'weight_sensitive' "
            "(weight choice determines the ranking; results must be labelled as such); "
            f"kendall_tau_min >= {TAU_STABILITY_THRESHOLD} => 'ranking_stable'"
        ),
        "profiles": profile_blocks,
        "scope_note": (
            "Ranking-stability test of heuristic profile weights on a TOI candidate "
            "pool. Not a calibration of absolute similarity scores, not a "
            "habitability claim. tfopwg_designation labels are not used to score "
            "or weight any result."
        ),
        "runtime_seconds": round(time.time() - start, 1),
        "provenance": build_manifest(
            input_path=args.input,
            config=config,
            seed=None,
            pipeline_version=__version__,
            model_version="score_earth_similarity (heuristic profile weights v1.0)",
        ),
    }
    payload["provenance"]["report_hash"] = canonical_hash(
        {key: value for key, value in payload.items() if key not in ("provenance",)}
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.output} ({len(candidates)} candidates, {payload['runtime_seconds']}s)")
    for profile in PROFILES:
        cells = profile_blocks[profile]["perturbation_fraction"]
        summary = ", ".join(
            f"±{key}: τ_min={cell['kendall_tau_min']} ({cell['verdict']})"
            for key, cell in cells.items()
        )
        print(f"  {profile}: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
