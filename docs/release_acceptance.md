# Scientific release acceptance matrix

This file is an acceptance template, not a claim that every gate has measured results. `PASS` requires an immutable report, a reproducible command and a threshold frozen before evaluation. A completed measurement without a predeclared threshold is reported as `MEASURED`, not retroactively promoted to `PASS`.

| Gate | Required evidence | Status |
|---|---|---|
| Known planets | >=50 labelled targets, expected/recovered table | 50 SELECTED / 46 EVALUATED / 4 NO MEASURED SECTOR; conditional detection 46/46, joint recovery 21/46 |
| Injection recovery | period/depth/duration grid on real noise | MEASURED: 960/960 RECORDED / 888 EVALUABLE / 450 STRICT / 466 HARMONIC-AWARE; no predeclared pass threshold |
| False positives | >=100 labelled FP and quiet controls | LABELLED FP/PLANET INPUT CORPUS READY (1817 FP + 1191 planet) / 10 QUIET HOSTS FROZEN / CONTROLLED RUN PENDING |
| Parameter recovery | bias, scatter, RMSE and coverage | N=50 PERIOD/RADIUS BIAS, SCATTER AND RMSE MEASURED; injection parameter aggregation and interval coverage pending |
| FPP | holdout calibration and reliability metrics | IMPLEMENTED / PENDING DATA |
| Earth similarity | ±10/20% sensitivity and ablation | SENSITIVITY MEASURED (τ=1.0, ±10/20%) / ABLATION PENDING RUN |
| Cross-sector | period/depth/duration/epoch metrics | N=50 LIMITED MEASUREMENT: 20/38 consistent; broader analysis pending |
| MCMC | R-hat, ESS, divergences quality gate | IMPLEMENTED |
| Baselines | same corpus, TLS-only and BLS-only comparison | IMPLEMENTED / PENDING RUN |
| Blind test | deterministic held-out target IDs | IMPLEMENTED / PENDING DATA |
| Provenance | input/config/output hashes and git revision | MEASURED FOR N=1, N=5, N=10, N=50 AND 960-TRIAL INJECTION CAMPAIGN |
| Schema | CI machine validation | IMPLEMENTED |
| Determinism | repeated output hash equality | N=1 MEASURED PASS; N=10/N=50/injection clean rerun comparison pending |
| Performance | seconds/target and peak memory | IMPLEMENTED / PENDING RUN |
| Figures | measured-only recovery/reliability plots | IMPLEMENTED / PENDING RUN |
| Reproduction | `astrotransit reproduce benchmark-v1` | IMPLEMENTED |
| Documentation | methods, assumptions, references, limitations | IMPLEMENTED |
| Environment | `uv.lock`, requirements lock and Dockerfile | IMPLEMENTED |
| Repository lint | `ruff check .` | IMPLEMENTED |

## Frozen evidence

Known-planet evidence:

- `validation_runs/v1_known_planets/determinism_n1_v1/`
- `validation_runs/v1_known_planets/known_planets_5_v1/`
- `validation_runs/v1_known_planets/known_planets_10_v1/`
- `validation_runs/v1_known_planets/known_planets_50_v1/`

Real-noise injection evidence:

- `validation_runs/v1_injection_recovery/real_noise_v1/`
- planned/recorded: 960/960
- evaluable: 888
- not evaluated because no injected cadence was observed: 72
- strict period recovery: 450/888 (50.6757%; 95% Wilson 47.3915%–53.9540%)
- harmonic-aware period recovery: 466/888 (52.4775%)
- cascade lane strict recovery: 449/800 (56.1250%)
- stitched 50-day lane strict recovery: 1/88 (1.1364%)
- output SHA-256: `c142612b64fb888f76725b45df5e494b3ac8186804c3238b1a8df56a868ba810`

The availability-aware N=50 campaign selected 50 known targets. Forty-six were evaluable and four produced no measured sector. The evaluated subset detected 46/46 targets, jointly recovered period and radius for 21/46, recovered period for 32/46, recovered radius for 23/46, and returned a true sector-consistency verdict for 20/38 evaluable targets. False-positive rejection was not evaluated. The four unavailable targets are excluded from recovery denominators and are not failed detections.

The injection campaign measures post-detrending detection-stage completeness on ten selected real-noise hosts. It does not measure population completeness, end-to-end preprocessing completeness or uncertainty coverage. The low 50-day recovery is an explicit measured limitation and must not be hidden by combining availability outcomes with detector outcomes.

See [`docs/measured_validation_results.md`](measured_validation_results.md) for numeric summaries and claim boundaries. A release must not convert `PENDING DATA`, `PENDING RUN`, or a measurement without a predeclared threshold into a passing score.
