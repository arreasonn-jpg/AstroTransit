# Discovery Note: TIC 417860263 / HD 224792

**Date:** 2026-07-11  
**Pipeline:** AstroTransit v0.1.0

## Summary

TIC 417860263 (HD 224792; Gaia DR3 429915991435184000) is currently the strongest
non-TOI transit candidate identified in the AstroTransit discovery workflow.

The candidate is based primarily on a strong Sector 57 detection and is supported by:
- MAP follow-up
- WSL/Linux MCMC posterior analysis
- clean catalog cross-checks
- simplified scenario-based FPP analysis
- partial multi-sector forced-ephemeris recovery

## Host Star

- **Distance:** ~38.34 pc (~125 light years)
- **Tmag:** 6.5443
- **Teff:** 6362 K
- **R★:** 1.120 R☉
- **M★:** 1.27 M☉
- **TIC contamination ratio:** 0.011693 (~1.2%)

## Transit Candidate Parameters

Sector 57 provides the strongest signal.

- **Period (reference):** ~2.8535 d
- **Transit depth:** ~630 ppm
- **Rp/Rs:** ~0.0251
- **Planet radius:** ~3.07 R⊕
- **Equilibrium temperature:** ~1438 K
- **TLS SNR:** ~47.85

## MCMC Summary

- **Platform:** WSL/Linux
- **Fit method:** PyMC / exoplanet
- **success:** True
- **convergence_ok:** True
- **r_hat_max:** 1.0421
- **n_divergences:** 0
- **Period sampled:** No (fixed during controlled Full-A MCMC)

## Catalog Cross-Check Status

The target does **not** appear as:
- a TOI,
- a CTOI,
- a confirmed planet host in the NASA Exoplanet Archive checks used here,
- or a follow-up target in ExoFOP-TESS records examined during this workflow.

SIMBAD identifies the host as **PM*** rather than a known exoplanet host.
Gaia nearby-source checks do not show a comparably bright contaminant within 10 arcsec.

## Simplified False Positive Probability

A simplified scenario-based FPP estimate yields:

- **P(TP):** 95.34%
- **FPP:** 4.66%

This places TIC 417860263 in the **strong candidate** category, not in the
formally validated or confirmed-planet category.

## Multi-Sector Status

Additional SPOC 120s TESS data exist in sectors:
**57, 58, 77, 78, 84, 85**

A refined forced-ephemeris analysis using AstroTransit detrending recovered
positive transit-like signals in **4 of 6 sectors**:

- **Detected:** 57, 58, 77, 78
- **Not clearly recovered:** 84, 85

Combined forced-ephemeris depth / SNR metrics are strong, but sector-to-sector
depth consistency is imperfect and odd-even checks remain noisy.

## Limitations

This candidate is **not formally validated** and **not confirmed**.

Missing ingredients for formal validation include:
- high-resolution imaging,
- radial velocity follow-up,
- and/or a more complete external FPP workflow.

Multi-sector transit timing refinement was explored, but the current timing
approach remains too noisy for a definitive long-baseline ephemeris solution.

## Current Best Statement

TIC 417860263 (HD 224792) is a **strong non-TOI sub-Neptune transit candidate**
identified by AstroTransit, supported by Sector 57 MAP and WSL-based MCMC analysis,
clean catalog cross-checks, simplified FPP = 4.66%, and partial multi-sector recovery.

## Package Contents

This deposit includes:
- core reports,
- candidate JSON data products,
- MCMC summary artifacts,
- catalog cross-check outputs,
- forced multi-sector validation outputs,
- figures,
- configs,
- and environment snapshots.
