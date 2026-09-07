from pathlib import Path
import sys
import time
import pandas as pd

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))


GOLDEN_TARGETS = [
    {
        "target_id": "TIC 100100827",
        "name": "WASP-18b",
        "sector": 2,
    },
    {
        "target_id": "TIC 256364928",
        "name": "HD 189733b",
        "sector": 41,
    },
    {
        "target_id": "TIC 25155310",
        "name": "WASP-126b",
        "sector": 1,
    },
]


def summarize_sector_result(name: str, target_id: str, sector_result):
    row = {
        "name": name,
        "target_id": target_id,
        "sector": sector_result.sector,
        "pipeline_success": sector_result.success,
        "has_candidate": sector_result.has_candidate,
        "candidate_confirmed": sector_result.candidate_confirmed,
        "candidate_period": None,
        "candidate_snr": None,
        "candidate_sde": None,
        "fit_method": None,
        "fit_success": None,
        "fitted_period": None,
        "fitted_rp_rs": None,
        "planet_radius_rearth": None,
        "equilibrium_temperature_k": None,
        "convergence_ok": None,
        "r_hat_max": None,
        "n_divergences": None,
        "n_samples": None,
        "quality_class": None,
        "quality_score": None,
        "fpp": None,
        "error": sector_result.error,
    }

    cand = sector_result.candidate
    if cand is not None:
        row["candidate_period"] = cand.period
        row["candidate_snr"] = cand.snr
        row["candidate_sde"] = cand.sde

    fit = sector_result.fit_result
    if fit is not None:
        row["fit_method"] = getattr(fit, "fit_method", None)
        row["fit_success"] = getattr(fit, "success", None)
        row["fitted_period"] = getattr(fit, "period", None)
        row["fitted_rp_rs"] = getattr(fit, "rp_rs", None)

        derived = getattr(fit, "derived", None)
        if derived is not None:
            row["planet_radius_rearth"] = getattr(derived, "planet_radius_rearth", None)
            row["equilibrium_temperature_k"] = getattr(derived, "equilibrium_temperature_k", None)

        row["convergence_ok"] = getattr(fit, "convergence_ok", None)
        row["r_hat_max"] = getattr(fit, "r_hat_max", None)
        row["n_divergences"] = getattr(fit, "n_divergences", None)
        row["n_samples"] = getattr(fit, "n_samples", None)

    quality = sector_result.quality
    if quality is not None:
        row["quality_class"] = quality.score.candidate_class.value
        row["quality_score"] = quality.score.total_score
        row["fpp"] = quality.vetting.false_positive_probability

    return row


def main():
    from astrotransit.logging_config import setup_logging
    from astrotransit.pipelines.orchestrator import AstroTransitOrchestrator

    config_path = project_root / "configs" / "wsl_mcmc.toml"
    output_dir = project_root / "outputs_wsl_mcmc"
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "wsl_mcmc_validation_summary.csv"

    setup_logging(log_level="INFO")

    print("=" * 72)
    print("  AstroTransit - WSL MCMC Validation")
    print("=" * 72)
    print(f"Config : {config_path}")
    print(f"Output : {output_dir}")
    print("=" * 72)
    print()

    all_rows = []
    t0 = time.time()

    with AstroTransitOrchestrator(
        config_path=str(config_path),
        force_mcmc=True,
        force_map=False,
        skip_visualization=True,
        skip_catalog=False,
        log_level="INFO",
    ) as orch:

        for idx, item in enumerate(GOLDEN_TARGETS, start=1):
            target_id = item["target_id"]
            name = item["name"]
            sector = item["sector"]

            print(f"[{idx}/{len(GOLDEN_TARGETS)}] {name} ({target_id}) S{sector}")

            t_target = time.time()
            result = orch.run_single(target_id, sectors=[sector])
            dt = time.time() - t_target

            print(f"  sure: {dt:.1f}s | success={result.success} | confirmed={result.candidates_confirmed}")

            if result.sector_results:
                sr = result.sector_results[0]
                row = summarize_sector_result(name, target_id, sr)
                all_rows.append(row)

                print(f"  fit_method      : {row['fit_method']}")
                print(f"  fit_success     : {row['fit_success']}")
                print(f"  fitted_period   : {row['fitted_period']}")
                print(f"  fitted_rp_rs    : {row['fitted_rp_rs']}")
                print(f"  convergence_ok  : {row['convergence_ok']}")
                print(f"  r_hat_max       : {row['r_hat_max']}")
                print(f"  n_divergences   : {row['n_divergences']}")
                print(f"  n_samples       : {row['n_samples']}")
                print(f"  class           : {row['quality_class']}")
                print(f"  score           : {row['quality_score']}")
                print(f"  fpp             : {row['fpp']}")
            else:
                all_rows.append({
                    "name": name,
                    "target_id": target_id,
                    "sector": sector,
                    "pipeline_success": result.success,
                    "has_candidate": None,
                    "candidate_confirmed": None,
                    "candidate_period": None,
                    "candidate_snr": None,
                    "candidate_sde": None,
                    "fit_method": None,
                    "fit_success": None,
                    "fitted_period": None,
                    "fitted_rp_rs": None,
                    "planet_radius_rearth": None,
                    "equilibrium_temperature_k": None,
                    "convergence_ok": None,
                    "r_hat_max": None,
                    "n_divergences": None,
                    "n_samples": None,
                    "quality_class": None,
                    "quality_score": None,
                    "fpp": None,
                    "error": result.error,
                })
                print(f"  sector result yok | error={result.error}")

            print()

    total_dt = time.time() - t0

    df = pd.DataFrame(all_rows)
    df.to_csv(csv_path, index=False)

    print("=" * 72)
    print("  Ozet")
    print("=" * 72)
    print(df.to_string(index=False))
    print()
    print("MCMC fit_method dagilimi:")
    if "fit_method" in df.columns:
        print(df["fit_method"].value_counts(dropna=False))
    print()
    print(f"Toplam sure: {total_dt:.1f}s")
    print(f"CSV rapor: {csv_path}")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())