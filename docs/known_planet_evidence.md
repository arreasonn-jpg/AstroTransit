# Frozen known-planet evidence

## N=1 deterministic rerun

The same WASP-18b benchmark was executed independently twice at commit
`2502ebe92a628b2180ad8433cbdedcf91cf4f1d9`.

- Verdict: `PASS`
- Canonical JSON hashes: equal
- Raw CSV SHA-256 hashes: equal
- Metrics hashes: equal
- Target ordering: equal
- Differences: none

Evidence: `validation_runs/v1_known_planets/determinism_n1_v1/`.

This proves deterministic reproduction only for this target, commit and locked
environment. It does not establish population-level recovery performance.

## N=5 known-planet sanity baseline

Five known targets were evaluated at commit
`5987f798fdd36ef97eb61c4494482a6c2062a8cd`.

| Metric | Measured value |
|---|---:|
| Detection | 5/5 (1.0) |
| Correct recovery | 2/5 (0.4) |
| Period recovery | 3/5 (0.6) |
| Radius recovery | 3/5 (0.6) |
| Sector consistency | 1/4 (0.25) |
| False-positive rejection | Not evaluated |

Evidence: `validation_runs/v1_known_planets/known_planets_5_v1/`.

The run establishes that multi-target execution and evidence capture work. It
also exposes recovery weaknesses: TOI-125b and TOI-561b failed period recovery,
TOI-561b and WASP-19b failed radius recovery, and only one of four targets with
a sector-consistency verdict was consistent.

## Interpretation boundary

Neither campaign measures injection-recovery completeness, calibrated
precision, false-positive rejection, or release-scale known-planet recall. The
next broad known-planet run must preserve these frozen baselines and report
failures rather than replacing them with unsupported claims.
