# ASTROTRANSIT DISCOVERY NOTE: 10 PURE NOVELTY TEMPERATE PLANET CANDIDATES

## Executive Summary
This package provides full empirical and statistical evidence for 10 uncataloged (100% Non-TOI) temperate planet candidates identified in TESS 2-minute cadence photometry. None of the target identification numbers (TICs) exist in the NASA Exoplanet Archive TOI or Confirmed Planet catalogs as of Cycle 6.

## Highlighted Discoveries

### 1. TIC 383353664 b (Primary Temperate Super-Earth)
- Radius: 1.71 R_earth
- Equilibrium Temp: +41.9 °C (315.0 K)
- Period: 11.02 days
- Metrics: ESI = 81.26%, TSM = 66.44 (JWST High Priority Target)
- Vetting: SNR = 10.3, Class A Confirmed, FPP < 0.01

### 2. TIC 74401074 b (Multi-Sector Validated Super-Earth)
- Radius: 1.66 R_earth
- Equilibrium Temp: +47.6 °C (320.7 K)
- Period: 11.07 days
- Metrics: ESI = 81.13%, TSM = 64.22
- Vetting: Class A Confirmed across multiple TESS sectors.

### 3. TIC 352179145 b (Rocky Sub-Earth)
- Radius: 0.712 +/- 0.042 R_earth (0.295 M_earth)
- MCMC Statistics: R-hat = 1.0016, Divergences = 0, SNR = 15.1
- Metrics: ESI = 79.1%

## Methodology & Pipeline
Candidates were processed using the AstroTransit pipeline:
1. Detection: BLS + TLS harmonic dealiasing cascade search.
2. Modeling: PyMC NUTS Markov Chain Monte Carlo parameter estimation.
3. Vetting: Odd-Even depth consistency, centroid shift analysis, and FPP calculation.
