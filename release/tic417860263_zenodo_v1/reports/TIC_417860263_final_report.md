# TIC 417860263 Final Candidate Report

## Executive Summary
TIC 417860263 (HD 224792), AstroTransit keşif iş akışında tespit edilen en güçlü TOI-dışı transit adayıdır. NASA Exoplanet Archive onaylı gezegenler tablosunda (pscomppars) ve TOI tablosunda 30 yay-saniyesi içinde ya da TIC kimliği/yıldız adı üzerinden herhangi bir eşleşme bulunmamaktadır. SIMBAD, ev sahibi yıldızı bir proper-motion yıldızı olarak sınıflandırmakta; Gaia yakın çevre kontrolünde ise 10 yay-saniyesi içinde benzer parlaklıkta kirletici kaynak görülmemektedir. Yaklaşık 2.85 günlük transit sinyali ve ~3.07 R⊕ yarıçap tahmini, hem MAP hem de WSL tabanlı MCMC analiziyle desteklenmektedir.

## Metadata
- **generated_at_utc**: 2026-07-10T20:05:41.189154+00:00
- **report_type**: final_candidate_report
- **target_key**: TIC_417860263_S57

## Target Identification
- **tic_id**: 417860263
- **host_name**: HD 224792
- **gaia_dr3_id**: 429915991435184000
- **sector**: 57
- **ra_deg**: 0.173517429377549
- **dec_deg**: 62.1758987685257

## Stellar Parameters
- **Tmag**: 6.5443
- **Teff_K**: 6362.34
- **Rstar_Rsun**: 1.12036
- **Mstar_Msun**: 1.27
- **simbad_otype**: PM*

## MAP Follow-up Summary
- **fit_method**: map
- **period_days**: 2.853511
- **rp_rs**: 0.025106
- **planet_radius_rearth**: 3.071
- **snr**: 47.85
- **candidate_class**: A
- **score**: 100
- **fpp**: 0.0
- **source**: validated_followup_map_result_manual_summary

## WSL MCMC Summary
### Fit Quality
- **fit_method**: mcmc
- **platform**: wsl
- **success**: True
- **convergence_ok**: True
- **r_hat_max**: 1.0421
- **n_divergences**: 0
- **n_samples**: 1000
- **mcmc_policy**: controlled_full_a

### Sampling Contract
- **sampled_parameters**: ['t0', 'rp_rs', 'impact_parameter', 'baseline', 'log_jitter']
- **fixed_parameters**: ['period', 'u1', 'u2']
- **period_sampled**: False
- **period_err**: None
- **period_err_source**: fixed_in_mcmc
- **limb_darkening_sampled**: False

### Posterior Summary
- **t0**: 2854.378905 ± 0.001789
- **rp_rs**: 0.025096 ± 0.000271
- **impact_parameter**: 0.028297 ± 0.023378
- **log_jitter**: -8.066158 ± 0.007117
- **baseline**: 1.000036 ± 3e-06

### Derived Parameters
- **period_days_map_reference**: 2.853511
- **planet_radius_rearth**: 3.0703
- **equilibrium_temperature_k**: 1438.4

## Catalog Cross-check Summary
- **simbad_known_exoplanet_host_flag**: False
- **gaia_sources_within_10arcsec_including_host**: 5
- **gaia_other_sources_within_10arcsec**: 4
- **brightest_other_gaia_gmag**: 15.780437
- **host_gaia_gmag**: 6.922204
- **brightest_neighbor_delta_g**: 8.858232999999998
- **bright_contaminant_flag_delta_g_lt_3**: False
- **confirmed_exoplanet_archive_match_found**: False
- **toi_exact_tic_match_found**: False
- **toi_nearby_30arcsec_match_found**: False

## Interpretation
- **novelty_status**: strong_non_toi_candidate
- **summary_en**: TIC 417860263 (HD 224792) is currently the strongest non-TOI transit candidate identified in this AstroTransit discovery workflow. It shows no match in the NASA Exoplanet Archive confirmed planets table (pscomppars) or the TOI table within 30 arcsec or by TIC/hostname identifier. SIMBAD classifies the host as a proper-motion star and Gaia nearby-source checks reveal no comparably bright contaminant within 10 arcsec. The transit signal at period ~2.85 d and planet radius ~3.07 R_earth is supported by both MAP and WSL-based MCMC analysis.
- **summary_tr**: TIC 417860263 (HD 224792), AstroTransit keşif iş akışında tespit edilen en güçlü TOI-dışı transit adayıdır. NASA Exoplanet Archive onaylı gezegenler tablosunda (pscomppars) ve TOI tablosunda 30 yay-saniyesi içinde ya da TIC kimliği/yıldız adı üzerinden herhangi bir eşleşme bulunmamaktadır. SIMBAD, ev sahibi yıldızı bir proper-motion yıldızı olarak sınıflandırmakta; Gaia yakın çevre kontrolünde ise 10 yay-saniyesi içinde benzer parlaklıkta kirletici kaynak görülmemektedir. Yaklaşık 2.85 günlük transit sinyali ve ~3.07 R⊕ yarıçap tahmini, hem MAP hem de WSL tabanlı MCMC analiziyle desteklenmektedir.

## Cautions
- CTOI / ExoFOP-TESS cross-check is not yet included in this report.
- A manual MCMC sidecar was initially exported during debugging; native outputs_novel_mcmc persistence was subsequently restored after MCMCFitResult harmonization patch (patch_mcmc_harmonize.py).
- Period was fixed during controlled Full-A MCMC, so period_err is intentionally null in the MCMC output. This should be interpreted as period_sampled=False and period_err_source='fixed_in_mcmc'.
- r_hat_max=1.0421 is slightly above the conservative 1.01 threshold. Convergence is acceptable for exploratory follow-up, but this should be noted in any formal scientific communication.

## Artifacts Status
- **native_mcmc_candidate_json_exists**: True
- **mcmc_summary_sidecar_exists**: True

## Source Files
- **crosscheck_json**: outputs_discovery/reports/TIC_417860263_crosscheck.json
- **exoplanet_archive_json**: outputs_discovery/reports/TIC_417860263_exoplanet_archive_check.json
- **toi_json**: outputs_discovery/reports/TIC_417860263_toi_check.json
- **toi_nearby_json**: outputs_discovery/reports/TIC_417860263_toi_nearby_check.json
- **mcmc_summary_sidecar_json**: outputs_novel_mcmc/json/TIC_417860263_S57_mcmc_summary.json
- **native_mcmc_candidate_json**: outputs_novel_mcmc/json/TIC_417860263_S57.json
- **followup_map_json**: outputs_novel_followup/json/TIC_417860263_S57.json
