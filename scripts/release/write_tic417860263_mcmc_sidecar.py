from __future__ import annotations

import json
from pathlib import Path

OUT_DIR_JSON = Path("outputs_novel_mcmc/json")
OUT_DIR_MD = Path("outputs_novel_mcmc/reports")
OUT_DIR_JSON.mkdir(parents=True, exist_ok=True)
OUT_DIR_MD.mkdir(parents=True, exist_ok=True)


def main():
    payload = {
        "target": {
            "tic_id": 417860263,
            "target_name": "TIC 417860263",
            "host_name": "HD 224792",
            "gaia_dr3_id": "429915991435184000",
            "sector": 57,
        },
        "fit_summary": {
            "fit_method": "mcmc",
            "platform": "wsl",
            "success": True,
            "convergence_ok": True,
            "r_hat_max": 1.0421,
            "n_divergences": 0,
            "n_samples": 1000,
            "mcmc_policy": "controlled_full_a",
        },
        "sampling_contract": {
            "sampled_parameters": [
                "t0",
                "rp_rs",
                "impact_parameter",
                "baseline",
                "log_jitter",
            ],
            "fixed_parameters": [
                "period",
                "u1",
                "u2",
            ],
            "period_sampled": False,
            "period_err": None,
            "period_err_source": "fixed_in_mcmc",
            "limb_darkening_sampled": False,
        },
        "posterior_summary": {
            "t0": {"value": 2854.378905, "err": 0.001789},
            "rp_rs": {"value": 0.025096, "err": 0.000271},
            "impact_parameter": {"value": 0.028297, "err": 0.023378},
            "log_jitter": {"value": -8.066158, "err": 0.007117},
            "baseline": {"value": 1.000036, "err": 0.000003},
        },
        "derived_parameters": {
            "period_days_map_reference": 2.853511,
            "planet_radius_rearth": 3.0703,
            "equilibrium_temperature_k": 1438.4,
        },
        "provenance": {
            "source": "validated_wsl_mcmc_run_manual_sidecar_export",
            "date_utc": "2026-07-10",
            "notes": [
                "This sidecar was written because native outputs_novel_mcmc JSON persistence was not yet confirmed.",
                "Values were copied from the validated WSL MCMC run summary for TIC 417860263.",
            ],
        },
    }

    json_path = OUT_DIR_JSON / "TIC_417860263_S57_mcmc_summary.json"
    md_path = OUT_DIR_MD / "TIC_417860263_S57_mcmc_summary.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TIC 417860263 WSL MCMC Summary\n\n")
        f.write("## Target\n")
        for k, v in payload["target"].items():
            f.write(f"- **{k}**: {v}\n")

        f.write("\n## Fit Summary\n")
        for k, v in payload["fit_summary"].items():
            f.write(f"- **{k}**: {v}\n")

        f.write("\n## Sampling Contract\n")
        for k, v in payload["sampling_contract"].items():
            f.write(f"- **{k}**: {v}\n")

        f.write("\n## Posterior Summary\n")
        for k, v in payload["posterior_summary"].items():
            f.write(f"- **{k}**: {v['value']} ± {v['err']}\n")

        f.write("\n## Derived Parameters\n")
        for k, v in payload["derived_parameters"].items():
            f.write(f"- **{k}**: {v}\n")

        f.write("\n## Provenance\n")
        for k, v in payload["provenance"].items():
            f.write(f"- **{k}**: {v}\n")

    print(f"Saved: {json_path}")
    print(f"Saved: {md_path}")


if __name__ == "__main__":
    main()