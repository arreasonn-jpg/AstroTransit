# Known-planets N=50 v1 corpus

This campaign expands the frozen N=10 pilot to 50 unique TIC targets without changing the first ten target identities or their order.

## Selection policy

1. Read the repository-pinned `benchmarks/verified_targets.json` registry.
2. Preserve registry order; do not select targets based on AstroTransit output.
3. Take the first 50 unique TIC IDs with finite positive period and radius references.
4. Preserve source references and mark inherited N=10 rows explicitly when the registry lacks a row-level citation.
5. Freeze the source-file SHA-256, selected corpus SHA-256, selection code version, and counts by difficulty/reference status.

The selection is deterministic and independent of pipeline performance. It is not a random or population-representative sample.

## Execution plan

The real-data benchmark will use one target per shard, clean environment capture before evidence writes, locked dependencies, and immutable aggregate hashes. Radius results will be stratified by the reliability policy introduced in PR #19.

## Claim boundary

N=50 supports a broader empirical benchmark than N=10, but does not by itself establish survey completeness, precision, false-positive rejection, or population-level radius accuracy.
