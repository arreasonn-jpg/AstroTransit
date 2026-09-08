# Benchmark corpus and results

`verified_targets.json` is the versioned **ground-truth corpus** for known
planet targets. It is not a performance report and must not be quoted as
recall/completeness evidence.

## Labelled negative corpus

False-positive and quiet-star data must be supplied as a separate JSON corpus.
The format is described by `benchmarks/corpus.schema.json` and is loaded with
`astrotransit.validation.load_corpus`. Every case requires an explicit label
and a traceable `reference`; unknown labels are rejected. The repository does
not fabricate labels or convert missing labels to `false`.

Freeze a reviewed CSV corpus with an input hash:

```bash
python scripts/validation/build_labelled_corpus.py curated_cases.csv \
  --output benchmarks/labelled_corpus_v1.json
```

The CSV must contain `target_id,label,reference`; valid labels are
`planet`, `false_positive` and `quiet_star`. Duplicate IDs and empty corpora
are rejected.

Recommended minimum release gate:

- 100 labelled eclipsing-binary/false-positive cases
- 100 quiet-star negative controls
- a held-out blind split produced by `partition_target_ids`

## Known-target benchmark

To expand the confirmed-planet corpus from a traceable external source, run:

```bash
python scripts/validation/build_known_planet_corpus.py --limit 100 \
  --output benchmarks/verified_targets_nasa_v1.json
```

The script queries only the NASA Exoplanet Archive confirmed-planet table,
records retrieval provenance and refuses to write an empty result. Review the
result and pin its retrieval date/hash before using it in a release.

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

## One-command reproduction

After installing the locked environment, reproduce the versioned benchmark
contract with:

```bash
astrotransit reproduce benchmark-v1 \
  --output outputs/benchmark/benchmark_performance.json \
  --csv-output outputs/benchmark/benchmark_targets.csv \
  --manifest outputs/benchmark/manifest.json
```

The command refuses unknown dataset identifiers, records input/config/output
hashes and can enforce a previously published output hash with
`--expected-sha256`. Network-backed data downloads remain explicit inputs and
are never silently treated as reproducible local fixtures.

Generate figures only from measured report fields:

```bash
python scripts/validation/generate_figures.py outputs/benchmark/benchmark_performance.json \
  --output-dir outputs/benchmark/plots
```

No figure is generated for a missing metric, preventing empty or fabricated
plots from being presented as validation evidence.

## Acceptance gate

Before claiming a research release, run:

```bash
astrotransit release-gate --corpus benchmarks/labelled_corpus.json \
  --injection-report outputs/validation/injection.json \
  --blind-report outputs/validation/blind.json \
  --baseline-report outputs/validation/baselines.json \
  --output outputs/validation/release_gate.json
```

A non-zero exit code is expected until the real corpora and immutable reports
meet the minimum thresholds. `PENDING_DATA` and `PENDING_RUN` are intentionally
not converted into zero-valued scientific metrics.

Evaluate saved predictions without changing the corpus split:

```bash
astrotransit evaluate-corpus corpus.json predictions.json \
  --split blind_test --output outputs/validation/blind.json
astrotransit evaluate-fpp fpp_predictions.json \
  --output outputs/validation/fpp_holdout.json
```
