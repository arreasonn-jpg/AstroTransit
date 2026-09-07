# AstroTransit Discovery Scale-Up Campaign Report

Campaign: `2026-07-11_discovery_scaleup`

## Reference DOI
- https://doi.org/10.5281/zenodo.21307889

## Scope
- scripts cleanup and operational reorganization
- v4 small-cool builder development
- proximity dedup and multisector prioritization
- discovery scan expansion (5 → 50 → 200 → 293 targets)
- crosscheck and selected follow-up

## Target pool
- v3 general pool: initial validation
- v4 small-cool mode: Teff ≤ 6200 K, R★ ≤ 1.2 R☉
- proximity dedup (10 arcsec)
- multisector >= 2 filter applied
- final pool: 293 targets

## Crosscheck
- All shortlisted candidates checked against:
  - NASA TOI catalog
  - local verified target set
  - NASA Exoplanet Archive (TIC-based query)
- All returned: NO_KNOWN_MATCH_FOUND

## Core MCMC-converged candidates
- TIC 347299560 / S24: Rp=0.787 R_earth, Teq=859.9 K, SNR=10.80, r_hat=1.008
- TIC 439949948 / S17: Rp=0.795 R_earth, Teq=559.1 K, SNR=7.97,  r_hat=1.031
- TIC 352146741 / S17: Rp=0.839 R_earth, Teq=512.6 K, SNR=12.24, r_hat=1.009

## Tier-2 MCMC-converged candidates
- TIC 439946042 / S17: Rp=0.932 R_earth, Teq=797.7 K, SNR=7.45, r_hat=1.008
- TIC 354532520 / S17: Rp=0.785 R_earth, Teq=704.7 K, SNR=6.40, r_hat=1.007
- TIC 427332476 / S42: Rp=1.109 R_earth, Teq=651.5 K, SNR=7.21, r_hat=1.008

## Additional validated MAP follow-up candidates
- TIC 407423779 / S18: Rp=1.128 R_earth, Teq=683.4 K, SNR=8.23
- TIC 201778444 / S57: Rp=1.497 R_earth, Teq=763.8 K, SNR=8.98

## Remaining shortlist (no follow-up yet)
- TIC 238432056 / S17: Rp=2.101 R_earth, Teq=1048.8 K
- TIC 352179145 / S17: Rp=2.053 R_earth, Teq=512.6 K
- TIC 373513128 / S18: Rp=1.378 R_earth, Teq=856.1 K
- TIC 283858887 / S57: Rp=0.723 R_earth, Teq=769.2 K
- TIC 411524787 / S17: Rp=0.974 R_earth, Teq=743.1 K

## Technical notes
- PyMC `Bad initial energy` instability was diagnosed and patched.
- Stabilized: `log_rp_rs`, `impact_parameter`, `log_jitter` initializations.
- All 6 MCMC candidates: n_divergences = 0, r_hat_max < 1.04.

## Outcome
- AstroTransit supports scalable non-TOI discovery.
- Science-priority filtering for small/cool candidates is operational.
- 6 crosscheck-clean, MCMC-converged candidates produced.
