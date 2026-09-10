# Sharded known-planet benchmarks

Large known-planet campaigns must not run as one serial GitHub Actions job.
The N=5 baseline required more than two hours, so N=10 and larger campaigns
run independent target shards and aggregate only completed reports.

## Scientific contract

- Every shard uses the same commit, locked environment and tolerances.
- A target ID may occur in exactly one shard.
- Empty or partial shards are rejected.
- Aggregate metrics are recomputed from target rows; shard percentages are
  never averaged.
- The final target order is either an explicit frozen corpus order or a
  deterministic lexical order.
- Source shard canonical hashes and git commits are retained in provenance.
- False-positive rejection remains `null` for a known-planet-only campaign.

## Aggregation command

```bash
python scripts/validation/aggregate_benchmark_shards.py \
  shard-results/*/benchmark.json \
  --target-order-file frozen_targets.json \
  --output aggregate/benchmark.json \
  --csv-output aggregate/targets.csv
```

The JSON writer also creates `aggregate/benchmark.manifest.json`. A campaign
manifest must additionally hash the frozen input corpus, environment manifest,
all shard reports and aggregate artifacts.

## Failure behavior

A failed shard blocks aggregation and must never be represented as a zero or
missing recovery row. Rerun the failed shard under the same frozen contract, or
start a new versioned campaign if the code, config or corpus changes.
