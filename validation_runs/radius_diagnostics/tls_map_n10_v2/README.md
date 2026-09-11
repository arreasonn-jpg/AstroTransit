# Frozen N=10 TLS–MAP radius diagnostic v2

This is the clean-provenance rerun of the same frozen N=10 real-TESS corpus after MAP adopted physical Kipping `q1/q2` quadratic limb darkening.

## Provenance

- Source commit: `1eea9e933b6ad93f631373f6b82d95eec1f7e234`
- Evidence commit: `3ca95404137dd15c82fbf15ee7d72b82c6417a98`
- Ten shard manifests record `git.dirty == false` and one common source commit.
- Input hash: `2e05fd8f726cf1d1079d1c04c73ce548b57676bae5ddcae7514e03e8da692b57`
- Aggregate canonical hash: `50d989568527c0295e628990c8a79aa2766235c2d21ae64f9d79f0e980537519`
- Aggregate JSON SHA-256: `b30523079171e80a4ecd8c12e6f7ac1f023c1e6ad4edb92ba2f511effbce07f8`
- Aggregate CSV SHA-256: `18c95fbfb9ef182207fbaf5fc629dd4782ac8c2f6f884133a2f37f405bfbb5b1`

## Controlled result

| Metric | v1 | v2 |
|---|---:|---:|
| Sector rows | 153 | 153 |
| Evaluated comparisons | 133 | 133 |
| Median signed `(MAP-TLS)/TLS` | 6.10% | 6.82% |
| Median absolute difference | 7.04% | 7.21% |
| Absolute difference >25% | 20 | 21 |
| Absolute difference >50% | 12 | 11 |
| Outside the closed physical LD region | 29 | 0 |
| Strict-interior LD solutions | 97 | 102 |
| Radius lower-bound signatures | 4 | 5 |
| Radius upper-bound signatures | 6 | 6 |

The physical parameterization eliminated coefficients outside the closed physical quadratic limb-darkening region. It did **not** improve the global median radius discrepancy on this corpus: median absolute difference changed from 7.04% to 7.21%.

For the exploratory high-impact subset, median absolute difference changed from 75.88% (14 rows) to 51.26% (18 rows). Because solutions can move between impact strata, this is not a paired causal estimate.

## Boundary inventory

Forty-nine of 133 evaluated v2 rows touched at least one optimizer bound. The most frequent contacts were:

- `log_jitter:lower`: 27
- `ld_q2:lower`: 16
- `ld_q2:upper`: 12
- `ld_q1:lower`: 7
- `log_rp_rs:upper`: 6
- `log_rp_rs:lower`: 5

Boundary contact is diagnostic evidence and not automatic fit failure. The unchanged radius-bound signatures and large grazing discrepancies show that physical limb darkening alone does not resolve the radius-identifiability problem.

## Decision

Do not claim improved radius recovery. Before scaling to N>=50, the next model iteration should address grazing/radius identifiability and replace silent hard-bound dependence with an explicit prior or reliability policy. Any change requires another controlled real-data comparison.
