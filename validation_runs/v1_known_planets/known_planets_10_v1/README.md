# Clean sharded N=10 known-planet benchmark

This directory freezes the authoritative clean-provenance N=10 benchmark run.

## Execution

- Source commit: `f68b24faa7b55a1938067875ff84aee200edb41d`
- Evidence commit: `c5cab4ac06fbb45963c4101176c641dab30d11fd`
- GitHub Actions run: `34512713842`
- Pipeline: AstroTransit 0.3.0
- Python: 3.11.16
- Seed: 42
- Shards: 10 independent one-target jobs
- Aggregation: `deterministic_target_row_merge_v1`
- Git cleanliness: `dirty: false` in all ten shard environment manifests

## Measured results

| Metric | Value |
|---|---:|
| Targets | 10 |
| Detected | 10/10 |
| Joint period + radius recovery | 5/10 |
| Period recovery | 7/10 |
| Radius recovery | 6/10 |
| Sector consistency | 5/9 |
| False-positive rejection | Not evaluated |

The aggregate canonical output hash is
`cd96087d2ec78d5c32f5dbc40b83a4315dac0b67f1d39edc2fd4e90e842fe08e`.
Every input, environment, shard report, shard CSV, aggregate report and
aggregate CSV is covered by SHA-256 evidence in `manifest.json`.

## Interpretation

This is a measured engineering baseline on ten labelled known targets. It is
not injection-recovery completeness, calibrated precision, false-positive
rejection, or the >=50-target release gate. Detection of 10/10 must not be
reported as general population recall.

The initial run was discarded because its environment manifests were dirty and
its aggregation environment omitted runtime dependencies. The clean run is the
only accepted N=10 evidence. Slight numeric differences between the discarded
and clean executions mean this campaign is not a broader deterministic-rerun
PASS; a separate clean-versus-clean comparison is required.
