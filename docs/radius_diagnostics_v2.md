# N=10 radius diagnostic v2 protocol

The v2 campaign reruns the unchanged frozen N=10 target corpus after the physical Kipping `q1/q2` MAP limb-darkening change.

## Controlled comparison

Held fixed:

- the ten target IDs and their order;
- real TESS data access and 120-second configured cadence;
- detrending configuration;
- TLS detection configuration;
- stellar catalog path;
- locked dependency environment and random seed.

Changed:

- MAP quadratic limb darkening is optimized in physical `q1/q2` coordinates;
- optimizer-boundary contacts and the limb-darkening parameterization are captured in each diagnostic row.

## Outputs

The campaign freezes sector-level JSON/CSV rows, ten clean environment manifests, artifact hashes, and an aggregate report. A later comparison must report v1 and v2 side by side and must not reinterpret this controlled engineering rerun as population-level radius accuracy.
