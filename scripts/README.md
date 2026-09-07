# Scripts

This directory contains operational, follow-up, release, maintenance, and historical patch scripts for AstroTransit.

## Layout

### `discovery/`
Scripts used to build target pools and run discovery scans.

Primary entrypoints:
- `build_non_toi_target_pool_v3.py`
- `run_discovery_pilot_v2.py`
- `classify_novelty.py`
- `filter_discovery_candidates.py`

### `followup/`
Scripts used for selected-candidate validation, multisector checks, ephemeris refinement, FPP estimation, and WSL MCMC runs.

### `crosscheck/`
Catalog and archive cross-check scripts used to verify novelty / known-status.

### `release/`
Scripts used to generate candidate reports and release metadata. Large ZIPs,
extracted evidence bundles and campaign outputs are published through Zenodo
or GitHub Releases; they are intentionally not committed under `release/`.

Reference DOI (historical external artifact):
- `10.5281/zenodo.21307889`
- https://doi.org/10.5281/zenodo.21307889

### `maintenance/`
Utility scripts for project checks, candidate deduplication, ranking analysis, and visuals.

### `patches/`
Historical or provenance-preserving patch scripts. These are generally **not** normal daily entrypoints.
They are kept to document important repository changes.

Critical preserved patch:
- `patch_mcmc_harmonize.py`
  - fixed native WSL MCMC output persistence / downstream contract issues

### `archive/`
Legacy, one-off, diagnostics, and superseded patch scripts. Backup snapshots
are not versioned; Git history and external release manifests are the recovery
mechanisms.

## Current workflow

1. Build discovery target pool
2. Run discovery scan with MAP-oriented pipeline
3. Classify novelty and filter candidates
4. Follow up only strongest candidates
5. Run WSL/Linux MCMC only for selected cases
6. Build reports / release artifacts as needed

## Reference candidate

TIC 417860263 / HD 224792 is kept as the main reference non-TOI discovery candidate for reproducibility and pipeline demonstration.

## Notes

- Prefer MAP for bulk discovery scanning
- Prefer WSL/Linux for MCMC
- Do not run patch scripts casually on a clean checkout
- Archive first, delete later