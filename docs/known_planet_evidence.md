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

## N=10 clean sharded baseline

Ten known targets were executed as independent one-target shards at commit
`f68b24faa7b55a1938067875ff84aee200edb41d`. All ten shard environment
manifests record a clean Git tree, Python 3.11.16, AstroTransit 0.3.0 and the
same dependency-lock hash. Aggregate metrics were recomputed from the target
rows rather than averaging shard metrics.

| Metric | Measured value |
|---|---:|
| Detection | 10/10 (1.0) |
| Correct recovery | 5/10 (0.5) |
| Period recovery | 7/10 (0.7) |
| Radius recovery | 6/10 (0.6) |
| Sector consistency | 5/9 (0.555556) |
| False-positive rejection | Not evaluated |

Evidence: `validation_runs/v1_known_planets/known_planets_10_v1/`.

WASP-18b, WASP-126b, WASP-100b, TOI-402.01 and TOI 564.01 passed the joint
period-and-radius recovery contract. TOI-125b, TOI-561b and WASP-77Ab failed
period recovery. TOI-561b, WASP-19b, WASP-77Ab and TOI 5556.01 failed radius
recovery. WASP-19b had one evaluated sector, so no sector-consistency verdict
was assigned.

The first N=10 execution produced complete shard outputs but had invalid dirty
provenance and an aggregation dependency error; it was discarded. A recovery
aggregation of those discarded shards is retained only in Git history, not as
accepted evidence. The clean campaign is the authoritative N=10 baseline.
Because the discarded and clean executions differed slightly in three numeric
target outputs while preserving all categorical counts, N=10 must not be
represented as a deterministic-rerun PASS. A dedicated clean rerun comparison
is still required for a broader determinism claim.

## Interpretation boundary

None of these campaigns measures injection-recovery completeness, calibrated
precision, false-positive rejection, or release-scale known-planet recall. The
N=10 run is an engineering and measured recovery baseline, not the >=50-target
release gate. Future campaigns must preserve these frozen artifacts and report
failures rather than replacing them with unsupported claims.
