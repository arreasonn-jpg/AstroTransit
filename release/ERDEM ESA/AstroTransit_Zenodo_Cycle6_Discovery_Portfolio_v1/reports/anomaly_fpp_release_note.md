# Anomaly + FPP Final Assessment Note

- Created: 2026-07-17T11:02:15.611381+00:00
- Evaluated candidates: 6

## Executive summary

A standalone anomaly-detection and simple false-positive proxy framework was applied to six MCMC-converged non-TOI transit candidates. The analysis combined residual diagnostics, folded-transit consistency, timing stability, crowding metadata (CROWDSAP), and Gaia DR3 local-neighborhood checks.

The main outcome is that the six candidates are not equally strong: two remain comparatively strong follow-up targets, two require manual methodological review, and two show substantial host-association / contamination concerns.

## Human-ranked candidate ordering

| Rank | TIC | Sector | Decision | Anomaly | FPP | P(planet) proxy | Note |
|---:|---|---:|---|---|---:|---:|---|
| 1 | TIC 354532520 | 17 | TOP_CLEAN_FOLLOWUP | CLEAN | 0.426 | 0.574 | Clean anomaly profile and clean environment; strongest current follow-up target. |
| 2 | TIC 347299560 | 24 | KEEP_WITH_CROWDING_CAUTION | REVIEW | 0.410 | 0.590 | Moderate crowding/timing concerns, but candidate remains viable. |
| 3 | TIC 352146741 | 17 | MANUAL_TIMING_REVIEW_REQUIRED | REJECT | 0.433 | 0.567 | Environment appears clean; timing instability may reflect ephemeris/midtime methodology. |
| 4 | TIC 427332476 | 42 | SHAPE_REVIEW_REQUIRED | REJECT | 0.321 | 0.679 | Environment is clean, but folded transit shape requires manual review. |
| 5 | TIC 439946042 | 17 | FOLLOWUP_WITH_HOST_AMBIGUITY_WARNING | CLEAN | 0.854 | 0.146 | Nearby brighter or near-equal-brightness source suggests host ambiguity. |
| 6 | TIC 439949948 | 17 | DEPRIORITIZED_CONTAMINATION_RISK | REVIEW | 0.881 | 0.119 | Very low CROWDSAP indicates strong contamination; likely ambiguous/blended host. |

## Strongest retained targets

### TIC 354532520 (S17)

- Decision: **TOP_CLEAN_FOLLOWUP**
- Anomaly: `CLEAN`
- Simple FPP: `0.426`
- CROWDSAP: `0.99943942`
- Gaia nearest neighbor: `8.635108674798076` arcsec
- Δmag: `8.692956924438477`
- Assessment: Clean anomaly profile and clean environment; strongest current follow-up target.

### TIC 347299560 (S24)

- Decision: **KEEP_WITH_CROWDING_CAUTION**
- Anomaly: `REVIEW`
- Simple FPP: `0.410`
- CROWDSAP: `0.97546136`
- Gaia nearest neighbor: `2.9604544334253573` arcsec
- Δmag: `4.957546234130859`
- Assessment: Moderate crowding/timing concerns, but candidate remains viable.

## Manual-review targets

### TIC 352146741 (S17)

- Decision: **MANUAL_TIMING_REVIEW_REQUIRED**
- Timing flag: `TIMING_UNSTABLE`
- Transit-consistency flag: `CONSISTENT`
- Simple FPP: `0.433`
- Environment note: CROWDSAP=`0.99777681`, nearest Gaia neighbor=`23.426070964166755` arcsec
- Assessment: Environment appears clean; timing instability may reflect ephemeris/midtime methodology.

### TIC 427332476 (S42)

- Decision: **SHAPE_REVIEW_REQUIRED**
- Timing flag: `STABLE`
- Transit-consistency flag: `EB_SUSPECT`
- Simple FPP: `0.321`
- Environment note: CROWDSAP=`0.9996444`, nearest Gaia neighbor=`9.06053836052126` arcsec
- Assessment: Environment is clean, but folded transit shape requires manual review.

## Host-ambiguity / contamination-limited targets

### TIC 439946042 (S17)

- Decision: **FOLLOWUP_WITH_HOST_AMBIGUITY_WARNING**
- CROWDSAP: `0.86085206`
- Dominant FP scenario: `neb`
- Nearest Gaia neighbor: `3.9197766728529806` arcsec
- Brightest-neighbor Δmag: `-2.0707201957702637`
- Simple FPP: `0.854`
- Assessment: Nearby brighter or near-equal-brightness source suggests host ambiguity.

### TIC 439949948 (S17)

- Decision: **DEPRIORITIZED_CONTAMINATION_RISK**
- CROWDSAP: `0.48620275`
- Dominant FP scenario: `neb`
- Nearest Gaia neighbor: `6.033660453320511` arcsec
- Brightest-neighbor Δmag: `-0.05041217803955078`
- Simple FPP: `0.881`
- Assessment: Very low CROWDSAP indicates strong contamination; likely ambiguous/blended host.

## Recommended operational outcome

- Promote **TIC 354532520** as the cleanest current follow-up target.
- Retain **TIC 347299560** with explicit crowding caution.
- Perform manual timing review for **TIC 352146741**.
- Perform folded-transit/shape review for **TIC 427332476**.
- Mark **TIC 439946042** as host-ambiguous.
- Deprioritize **TIC 439949948** due to strong contamination/blending risk.

## Caveat

This FPP framework is a proxy diagnostic layer and not a formal validation engine. Residual diagnostics are based on simplified standalone modeling and may over-penalize some otherwise viable signals. Nevertheless, the Gaia + CROWDSAP contamination findings are considered operationally meaningful.
