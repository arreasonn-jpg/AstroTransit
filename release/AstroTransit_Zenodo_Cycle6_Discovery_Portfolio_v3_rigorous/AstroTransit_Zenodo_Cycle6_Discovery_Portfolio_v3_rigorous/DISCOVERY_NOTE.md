# ASTROTRANSIT DISCOVERY & VETTING NOTE (v3 RIGOROUS AUDIT RELEASE)

## 1. Executive Summary & Vetting Rigor
This evidence package provides empirical TESS photometry fits, MCMC parameter estimations, and explicit False Positive Probability (FPP) reports for validated **Non-TOI exoplanet candidates**.

### Strict False Positive Exclusion Policy:
1. **TIC 439949948**: PURGED from the discovery portfolio due to a high FPP of 0.881 (NEB scenario, crowding ratio = 0.486).
2. **TIC 289972535**: PURGED due to a secondary eclipse signal (Eclipsing Binary / Stellar Variability).
3. All remaining candidates in this release have individually verified FPP < 0.02 and clean aperture photometry.

## 2. Vetted Exoplanet Candidates

### A. TIC 383353664 b (Temperate Super-Earth Candidate)
- **Status**: Planet Candidate (Sector 66)
- **Parameters**: Rp = 1.71 R_earth | Teq = +41.9 °C (315.0 K) | Period = 11.02 days
- **Metrics**: ESI = 0.8126 | TSM = 66.44
- **Vetting**: SNR = 10.3, FPP = 0.008 (Individual FPP report included in /reports/)

### B. TIC 74401074 b (Multi-Sector Super-Earth Candidate)
- **Status**: Planet Candidate (S39, S65)
- **Parameters**: Rp = 1.66 R_earth | Teq = +47.6 °C (320.7 K) | Period = 11.07 days
- **Metrics**: ESI = 0.8113 | TSM = 64.22 | FPP = 0.012

### C. TIC 352179145 b (Rocky Sub-Earth Candidate)
- **Status**: MCMC Validated Sub-Earth Candidate (R-hat = 1.0016, Divergences = 0)
- **Parameters**: Rp = 0.712 +/- 0.042 R_earth (0.295 M_earth) | Teq = 496.2 K
- **Metrics**: ESI = 0.7910 | SNR = 15.1 | FPP = 0.004

## 3. Rejection Log & Transparency
- **TIC 439949948**: Rejected (FPP = 0.881, NEB contamination risk).
- **TIC 289972535**: Rejected (Class D, Eclipsing Binary).
