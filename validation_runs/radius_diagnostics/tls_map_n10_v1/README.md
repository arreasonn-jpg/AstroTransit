# Frozen N=10 TLS–MAP radius diagnostic

This directory contains the first clean-provenance TLS-versus-MAP radius diagnostic on the frozen N=10 real-TESS known-planet corpus.

## Measured campaign result

- 10 targets and 153 sector rows were recorded.
- 133 rows contained both TLS and successful MAP measurements.
- 20 rows were explicitly not evaluated: 19 missing a successful fit and 1 missing TLS.
- Median signed MAP-minus-TLS `Rp/Rs` difference was +6.10% relative to TLS.
- Median absolute difference was 7.04%.

These are sector-level diagnostics, not independent target-level performance measurements.

## Exploratory failure-mode inventory

The following strata were defined after inspecting the diagnostic and are therefore **post-hoc exploratory**, not preregistered tests:

| Stratum | Evaluated rows | Median absolute fractional difference |
|---|---:|---:|
| Impact parameter `< 0.5` | 44 | 4.36% |
| Impact parameter `0.5–0.85` | 75 | 7.95% |
| Impact parameter `>= 0.85` | 14 | 75.88% |
| Physical quadratic limb-darkening region | 97 | 6.10% |
| Outside physical limb-darkening region | 36 | 10.30% |

Ten rows landed numerically at the TLS-derived MAP `Rp/Rs` search bounds: 4 near `0.5 × TLS` and 6 near `2 × TLS`. Twenty rows had an absolute fractional difference above 25%; twelve were above 50%.

The association is strongest in high-impact/grazing solutions, often accompanied by limb-darkening or radius-bound behavior. This does **not** prove a single causal mechanism. The next engineering step is to enforce a physical quadratic limb-darkening parameterization and expose optimizer-boundary hits, followed by a clean rerun on the same frozen corpus.

## Provenance

- Source commit: `eb413be452fb727402292873e3bc8248aa90508d`
- Evidence commit: `a98c4c8768a9d55e23e66a9c0a7f819ca896c7b2`
- Aggregate canonical output hash: `469fc60c290ca33185ef62839314dd44cb408035210531c6ccd6b90666434c46`
- Aggregate JSON SHA-256: `0bcb51530d3d3989f4f41963d34529838491de7d247f88a935ad048e49ee1eb9`
- Aggregate CSV SHA-256: `d82181384c43736773eddb7cbb21b177d98eeed05fa4c89c626fc7f53f385944`
- Frozen input SHA-256: `2e05fd8f726cf1d1079d1c04c73ce548b57676bae5ddcae7514e03e8da692b57`

All ten shard environment manifests record `git.dirty = false`, Python 3.11.16, AstroTransit 0.3.0, and the same source commit.

## Claim boundary

This campaign does not establish calibrated radius accuracy, parameter-recovery coverage, completeness, precision, or causality. It is an evidence-backed diagnostic used to choose the next model-hardening experiment.
