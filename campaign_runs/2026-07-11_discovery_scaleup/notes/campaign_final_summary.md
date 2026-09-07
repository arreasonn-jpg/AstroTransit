# AstroTransit Discovery Scale-Up Campaign Summary

## Campaign
- Name: 2026-07-11_discovery_scaleup

## Reference DOI
- https://doi.org/10.5281/zenodo.21307889

## Discovery strategy
- Initial general discovery validation completed
- Science-priority refinement added
- New v4 small-cool target-pool builder created
- Proximity-dedup + multisector prioritization applied

## Target-pool evolution
- v3 general pool validated
- v4 small-cool pool generated
- v4 small-cool dedup multisector>=2 pool used for science run

## Core results
Three non-TOI, crosscheck-clean, small-cool candidates reached successful WSL MCMC convergence:

1. TIC 347299560 / Sector 24
   - Rp ≈ 0.787 R_earth
   - MCMC converged
   - r_hat_max ≈ 1.008
   - divergences = 0

2. TIC 439949948 / Sector 17
   - Rp ≈ 0.795 R_earth
   - MCMC converged
   - r_hat_max ≈ 1.031
   - divergences = 0

3. TIC 352146741 / Sector 17
   - Rp ≈ 0.839 R_earth
   - MCMC converged
   - r_hat_max ≈ 1.009
   - divergences = 0

## Additional validated MAP follow-up candidates
- TIC 407423779 / Sector 18
- TIC 201778444 / Sector 57

## Technical note
A PyMC initialization stability issue causing `Bad initial energy` was resolved by stabilizing:
- `log_rp_rs` initialization
- `impact_parameter` initialization
- `log_jitter` initialization

## Outcome
AstroTransit now supports:
- large-scale TOI-excluded discovery
- science-priority filtering for small/cool systems
- crosscheck of novel candidates
- selected-candidate WSL MCMC follow-up with converged posterior results
