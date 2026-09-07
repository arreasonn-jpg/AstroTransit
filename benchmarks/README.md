# Benchmark corpus and results

`verified_targets.json` is the versioned **ground-truth corpus** for known
planet targets. It is not a performance report and must not be quoted as
recall/completeness evidence.

Run the network-backed known-target benchmark from the repository root:

```bash
astrotransit benchmark --max 5 \
  --output outputs/benchmark/benchmark_performance.json \
  --csv-output outputs/benchmark/benchmark_targets.csv
```

The command compares expected and recovered period/radius values and records
per-target detection, parameter recovery and sector consistency. The output
contains `null` for unmeasured quantities. False-positive rejection remains
`not_evaluated` until a labeled FP/quiet-star corpus is configured in
`configs/default.toml`.

Generated reports belong under `outputs/` and are ignored by Git. External
campaign data belong in Zenodo/GitHub Release artifacts, not in this directory.
