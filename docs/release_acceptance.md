# Scientific release acceptance matrix

This file is an acceptance template, not a claim that every gate has measured
results. `PASS` requires an immutable report and a reproducible command.

| Gate | Required evidence | Status |
|---|---|---|
| Known planets | >=50 labelled targets, expected/recovered table | 50 SELECTED / 46 EVALUATED / 4 NO MEASURED SECTOR; conditional detection 46/46, joint recovery 21/46 |
| Injection recovery | period/depth/duration grid on real noise | IMPLEMENTED / PENDING RUN |
| False positives | >=100 labelled FP and quiet controls | LABELLED FP/PLANET INPUT CORPUS READY (1817 FP + 1191 planet) / QUIET CONTROLS PENDING DATA / RUN PENDING |
| Parameter recovery | bias, scatter, RMSE and coverage | N=50 PERIOD/RADIUS POINT RECOVERY MEASURED; bias/scatter/RMSE/coverage campaign pending |
| FPP | holdout calibration and reliability metrics | IMPLEMENTED / PENDING DATA |
| Earth similarity | ±10/20% sensitivity and ablation | SENSITIVITY MEASURED (τ=1.0, ±10/20%) / ABLATION PENDING RUN |
| Cross-sector | period/depth/duration/epoch metrics | N=50 LIMITED MEASUREMENT: 20/38 consistent; broader analysis pending |
| MCMC | R-hat, ESS, divergences quality gate | IMPLEMENTED |
| Baselines | same corpus, TLS-only and BLS-only comparison | IMPLEMENTED / PENDING RUN |
| Blind test | deterministic held-out target IDs | IMPLEMENTED / PENDING DATA |
| Provenance | input/config/output hashes and git revision | MEASURED FOR N=1, N=5, N=10 AND N=50; 50 N=50 environment manifests frozen |
| Schema | CI machine validation | IMPLEMENTED |
| Determinism | repeated output hash equality | N=1 MEASURED PASS; N=10/N=50 clean rerun comparison pending |
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
- `validation_runs/v1_known_planets/known_planets_50_v1/`

The availability-aware N=50 campaign selected 50 known targets. Forty-six were
evaluable and four produced no measured sector. The evaluated subset detected
46/46 targets, jointly recovered period and radius for 21/46, recovered period
for 32/46, recovered radius for 23/46, and returned a true sector-consistency
verdict for 20/38 evaluable targets. False-positive rejection was not evaluated.
The four unavailable targets are excluded from recovery denominators and are
not failed detections.

These are selected-set measurements, not population recall, completeness,
precision or calibrated false-positive performance. See
[`docs/measured_validation_results.md`](measured_validation_results.md) for the
numeric summary and claim boundary. A release must not convert `PENDING DATA`
or `PENDING RUN` into a numeric score.
