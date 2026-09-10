# Scientific release acceptance matrix

This file is an acceptance template, not a claim that every gate has measured
results. `PASS` requires an immutable report and a reproducible command.

| Gate | Required evidence | Status |
|---|---|---|
| Known planets | >=50 labelled targets, expected/recovered table | N=1 + N=5 + N=10 MEASURED; release-scale >=50 run pending |
| Injection recovery | period/depth/duration grid on real noise | IMPLEMENTED / PENDING RUN |
| False positives | >=100 labelled FP and quiet controls | LABELLED FP/PLANET INPUT CORPUS READY (1817 FP + 1191 planet) / QUIET CONTROLS PENDING DATA / RUN PENDING |
| Parameter recovery | bias, scatter, RMSE and coverage | N=10 PERIOD/RADIUS MEASURED; grid-level validation pending |
| FPP | holdout calibration and reliability metrics | IMPLEMENTED / PENDING DATA |
| Earth similarity | ±10/20% sensitivity and ablation | SENSITIVITY MEASURED (τ=1.0, ±10/20%) / ABLATION PENDING RUN |
| Cross-sector | period/depth/duration/epoch metrics | N=10 LIMITED MEASUREMENT: 5/9 consistent; broader run pending |
| MCMC | R-hat, ESS, divergences quality gate | IMPLEMENTED |
| Baselines | same corpus, TLS-only and BLS-only comparison | IMPLEMENTED / PENDING RUN |
| Blind test | deterministic held-out target IDs | IMPLEMENTED / PENDING DATA |
| Provenance | input/config/output hashes and git revision | MEASURED FOR N=1, N=5 AND N=10; all N=10 shards clean |
| Schema | CI machine validation | IMPLEMENTED |
| Determinism | repeated output hash equality | N=1 MEASURED PASS; N=10 clean rerun comparison pending |
| Performance | seconds/target and peak memory | IMPLEMENTED / PENDING RUN |
| Figures | measured-only recovery/reliability plots | IMPLEMENTED / PENDING RUN |
| Reproduction | `astrotransit reproduce benchmark-v1` | IMPLEMENTED |
| Documentation | methods, assumptions, references, limitations | IMPLEMENTED |
| Environment | `uv.lock`, requirements lock and Dockerfile | IMPLEMENTED |
| Repository lint | `ruff check .` | IMPLEMENTED |

Frozen known-planet evidence:

- `validation_runs/v1_known_planets/determinism_n1_v1/`
- `validation_runs/v1_known_planets/known_planets_5_v1/`
- `validation_runs/v1_known_planets/known_planets_10_v1/`

The clean N=10 campaign detected 10/10 targets but fully recovered 5/10,
recovered the period for 7/10, recovered the radius for 6/10, and returned a
sector-consistency verdict of true for 5/9 evaluable targets. It is a measured
baseline, not a release-level success claim. A release must not convert
`PENDING DATA` or `PENDING RUN` into a numeric score.
