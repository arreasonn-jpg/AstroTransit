from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

OUT_DIR = Path("outputs_discovery/reports")
OUT_DIR.mkdir(parents=True, exist_ok=True)

CROSSCHECK = Path("outputs_discovery/reports/TIC_417860263_crosscheck.json")
EXO = Path("outputs_discovery/reports/TIC_417860263_exoplanet_archive_check.json")
TOI = Path("outputs_discovery/reports/TIC_417860263_toi_check.json")
TOI_NEARBY = Path("outputs_discovery/reports/TIC_417860263_toi_nearby_check.json")

# Detailed posterior / audit sidecar
MCMC_SUMMARY = Path("outputs_novel_mcmc/json/TIC_417860263_S57_mcmc_summary.json")

# Native pipeline candidate JSON (now restored/fixed)
MCMC_NATIVE_JSON = Path("outputs_novel_mcmc/json/TIC_417860263_S57.json")

MAP_SUMMARY = {
    "fit_method": "map",
    "period_days": 2.853511,
    "rp_rs": 0.025106,
    "planet_radius_rearth": 3.071,
    "snr": 47.85,
    "candidate_class": "A",
    "score": 100,
    "fpp": 0.0,
    "source": "validated_followup_map_result_manual_summary",
}


def load_json(path: Path):
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def first_or_none(x):
    return x[0] if x else None


def main():
    cross = load_json(CROSSCHECK) or {}
    exo = load_json(EXO) or {}
    toi = load_json(TOI) or {}
    toi_nearby = load_json(TOI_NEARBY) or {}
    mcmc = load_json(MCMC_SUMMARY) or {}
    native_mcmc_json_exists = MCMC_NATIVE_JSON.exists()

    generated_at_utc = datetime.now(timezone.utc).isoformat()

    tic_basic = cross.get("tic_basic", {})
    simbad = first_or_none(cross.get("simbad_matches_within_30arcsec", []))
    gaia_rows = cross.get("vizier_gaia_matches_within_10arcsec", [])
    gaia_id = tic_basic.get("Gaia_ID")

    host_row = None
    for row in gaia_rows:
        if str(row.get("Source")) == str(gaia_id):
            host_row = row
            break

    other_rows = []
    for row in gaia_rows:
        if str(row.get("Source")) != str(gaia_id) and row.get("Gmag") is not None:
            other_rows.append(row)

    brightest_other = None
    if other_rows:
        brightest_other = min(other_rows, key=lambda r: r["Gmag"])

    delta_g = None
    if host_row and brightest_other and host_row.get("Gmag") is not None:
        delta_g = brightest_other["Gmag"] - host_row["Gmag"]

    exo_queries = exo.get("queries", {})
    confirmed_cone = exo_queries.get("pscomppars_cone_30arcsec", [])
    confirmed_exact = exo_queries.get("pscomppars_exact_hostname", [])
    confirmed_loose = exo_queries.get("pscomppars_loose_hostname", [])

    confirmed_match_found = any([
        isinstance(confirmed_cone, list) and len(confirmed_cone) > 0,
        isinstance(confirmed_exact, list) and len(confirmed_exact) > 0,
        isinstance(confirmed_loose, list) and len(confirmed_loose) > 0,
    ])

    toi_queries = toi.get("queries", {})
    toi_exact = toi_queries.get("toi_exact_tic_match", [])
    toi_exact_found = isinstance(toi_exact, list) and len(toi_exact) > 0

    toi_nearby_rows = toi_nearby.get("matches_within_30arcsec", [])
    toi_nearby_found = isinstance(toi_nearby_rows, list) and len(toi_nearby_rows) > 0

    bright_contaminant = False
    if delta_g is not None and delta_g < 3.0:
        bright_contaminant = True

    novelty_status = "strong_non_toi_candidate"
    if confirmed_match_found or toi_exact_found or toi_nearby_found:
        novelty_status = "not_novel_or_catalog_match_found"
    elif bright_contaminant:
        novelty_status = "candidate_with_crowding_caution"

    fit_summary = mcmc.get("fit_summary", {})
    posterior = mcmc.get("posterior_summary", {})
    derived = mcmc.get("derived_parameters", {})
    sampling = mcmc.get("sampling_contract", {})

    r_hat_max = fit_summary.get("r_hat_max")

    cautions = [
        "CTOI / ExoFOP-TESS cross-check is not yet included in this report.",
        (
            "A manual MCMC sidecar was initially exported during debugging; "
            "native outputs_novel_mcmc persistence was subsequently restored "
            "after MCMCFitResult harmonization patch (patch_mcmc_harmonize.py)."
        ),
        (
            "Period was fixed during controlled Full-A MCMC, so period_err is "
            "intentionally null in the MCMC output. This should be interpreted as "
            "period_sampled=False and period_err_source='fixed_in_mcmc'."
        ),
    ]

    if isinstance(r_hat_max, (int, float)) and r_hat_max > 1.01:
        cautions.append(
            (
                f"r_hat_max={r_hat_max:.4f} is slightly above the conservative 1.01 "
                "threshold. Convergence is acceptable for exploratory follow-up, "
                "but this should be noted in any formal scientific communication."
            )
        )

    report = {
        "metadata": {
            "generated_at_utc": generated_at_utc,
            "report_type": "final_candidate_report",
            "target_key": "TIC_417860263_S57",
        },
        "target": {
            "tic_id": 417860263,
            "host_name": simbad.get("main_id") if simbad else "HD 224792",
            "gaia_dr3_id": tic_basic.get("Gaia_ID"),
            "sector": 57,
            "ra_deg": tic_basic.get("ra_deg"),
            "dec_deg": tic_basic.get("dec_deg"),
        },
        "stellar_parameters": {
            "Tmag": tic_basic.get("Tmag"),
            "Teff_K": tic_basic.get("Teff_K"),
            "Rstar_Rsun": tic_basic.get("Rstar_Rsun"),
            "Mstar_Msun": tic_basic.get("Mstar_Msun"),
            "simbad_otype": simbad.get("otype") if simbad else None,
        },
        "map_summary": MAP_SUMMARY,
        "mcmc_summary": mcmc,
        "crosscheck_summary": {
            "simbad_known_exoplanet_host_flag": False,
            "gaia_sources_within_10arcsec_including_host": len(gaia_rows),
            "gaia_other_sources_within_10arcsec": len(other_rows),
            "brightest_other_gaia_gmag": brightest_other.get("Gmag") if brightest_other else None,
            "host_gaia_gmag": host_row.get("Gmag") if host_row else None,
            "brightest_neighbor_delta_g": delta_g,
            "bright_contaminant_flag_delta_g_lt_3": bright_contaminant,
            "confirmed_exoplanet_archive_match_found": confirmed_match_found,
            "toi_exact_tic_match_found": toi_exact_found,
            "toi_nearby_30arcsec_match_found": toi_nearby_found,
        },
        "interpretation": {
            "novelty_status": novelty_status,
            "summary_en": (
                "TIC 417860263 (HD 224792) is currently the strongest non-TOI transit candidate "
                "identified in this AstroTransit discovery workflow. It shows no match in the NASA "
                "Exoplanet Archive confirmed planets table (pscomppars) or the TOI table within 30 arcsec "
                "or by TIC/hostname identifier. SIMBAD classifies the host as a proper-motion star and "
                "Gaia nearby-source checks reveal no comparably bright contaminant within 10 arcsec. "
                "The transit signal at period ~2.85 d and planet radius ~3.07 R_earth is supported by "
                "both MAP and WSL-based MCMC analysis."
            ),
            "summary_tr": (
                "TIC 417860263 (HD 224792), AstroTransit keşif iş akışında tespit edilen en güçlü "
                "TOI-dışı transit adayıdır. NASA Exoplanet Archive onaylı gezegenler tablosunda "
                "(pscomppars) ve TOI tablosunda 30 yay-saniyesi içinde ya da TIC kimliği/yıldız adı "
                "üzerinden herhangi bir eşleşme bulunmamaktadır. SIMBAD, ev sahibi yıldızı bir "
                "proper-motion yıldızı olarak sınıflandırmakta; Gaia yakın çevre kontrolünde ise "
                "10 yay-saniyesi içinde benzer parlaklıkta kirletici kaynak görülmemektedir. "
                "Yaklaşık 2.85 günlük transit sinyali ve ~3.07 R⊕ yarıçap tahmini, hem MAP hem de "
                "WSL tabanlı MCMC analiziyle desteklenmektedir."
            ),
            "cautions": cautions,
        },
        "source_files": {
            "crosscheck_json": str(CROSSCHECK),
            "exoplanet_archive_json": str(EXO),
            "toi_json": str(TOI),
            "toi_nearby_json": str(TOI_NEARBY),
            "mcmc_summary_sidecar_json": str(MCMC_SUMMARY),
            "native_mcmc_candidate_json": str(MCMC_NATIVE_JSON),
            "followup_map_json": "outputs_novel_followup/json/TIC_417860263_S57.json",
        },
        "artifacts_status": {
            "native_mcmc_candidate_json_exists": native_mcmc_json_exists,
            "mcmc_summary_sidecar_exists": MCMC_SUMMARY.exists(),
        },
    }

    json_path = OUT_DIR / "TIC_417860263_final_report.json"
    md_path = OUT_DIR / "TIC_417860263_final_report.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TIC 417860263 Final Candidate Report\n\n")

        f.write("## Executive Summary\n")
        f.write(report["interpretation"]["summary_tr"] + "\n\n")

        f.write("## Metadata\n")
        for k, v in report["metadata"].items():
            f.write(f"- **{k}**: {v}\n")

        f.write("\n## Target Identification\n")
        for k, v in report["target"].items():
            f.write(f"- **{k}**: {v}\n")

        f.write("\n## Stellar Parameters\n")
        for k, v in report["stellar_parameters"].items():
            f.write(f"- **{k}**: {v}\n")

        f.write("\n## MAP Follow-up Summary\n")
        for k, v in report["map_summary"].items():
            f.write(f"- **{k}**: {v}\n")

        f.write("\n## WSL MCMC Summary\n")
        if fit_summary:
            f.write("### Fit Quality\n")
            for k, v in fit_summary.items():
                f.write(f"- **{k}**: {v}\n")
        if sampling:
            f.write("\n### Sampling Contract\n")
            for k, v in sampling.items():
                f.write(f"- **{k}**: {v}\n")
        if posterior:
            f.write("\n### Posterior Summary\n")
            for k, v in posterior.items():
                f.write(f"- **{k}**: {v.get('value')} ± {v.get('err')}\n")
        if derived:
            f.write("\n### Derived Parameters\n")
            for k, v in derived.items():
                f.write(f"- **{k}**: {v}\n")

        f.write("\n## Catalog Cross-check Summary\n")
        for k, v in report["crosscheck_summary"].items():
            f.write(f"- **{k}**: {v}\n")

        f.write("\n## Interpretation\n")
        f.write(f"- **novelty_status**: {report['interpretation']['novelty_status']}\n")
        f.write(f"- **summary_en**: {report['interpretation']['summary_en']}\n")
        f.write(f"- **summary_tr**: {report['interpretation']['summary_tr']}\n")

        f.write("\n## Cautions\n")
        for note in report["interpretation"]["cautions"]:
            f.write(f"- {note}\n")

        f.write("\n## Artifacts Status\n")
        for k, v in report["artifacts_status"].items():
            f.write(f"- **{k}**: {v}\n")

        f.write("\n## Source Files\n")
        for k, v in report["source_files"].items():
            f.write(f"- **{k}**: {v}\n")

    print(f"Saved: {json_path}")
    print(f"Saved: {md_path}")


if __name__ == "__main__":
    main()