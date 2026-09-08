# Scientific release acceptance matrix

This file is an acceptance template, not a claim that every gate has measured
results. `PASS` requires an immutable report and a reproducible command.

| Gate | Required evidence | Status |
|---|---|---|
| Known planets | >=50 labelled targets, expected/recovered table | PENDING DATA |
| Injection recovery | period/depth/duration grid on real noise | IMPLEMENTED / PENDING RUN |
| False positives | >=100 labelled FP and quiet controls | LABELLED FP/PLANET INPUT CORPUS READY (1817 FP + 1191 planet, TESS FOP WG dispositions, `benchmarks/corpora/tfop_disposition_corpus_v1.json`) / QUIET CONTROLS PENDING DATA / RUN PENDING |
| Parameter recovery | bias, scatter, RMSE and coverage | IMPLEMENTED / PENDING RUN |
| FPP | holdout calibration and reliability metrics | IMPLEMENTED / PENDING DATA |
| Earth similarity | ±10/20% sensitivity and ablation | SENSITIVITY MEASURED (τ=1.0, ±10/20%, `benchmarks/results/similarity_sensitivity_v1.json`) / ABLATION PENDING RUN |
| Cross-sector | period/depth/duration/epoch metrics | IMPLEMENTED |
| MCMC | R-hat, ESS, divergences quality gate | IMPLEMENTED |
| Baselines | same corpus, TLS-only and BLS-only comparison | IMPLEMENTED / PENDING RUN |
| Blind test | deterministic held-out target IDs | IMPLEMENTED / PENDING DATA |
| Provenance | input/config/output hashes and git revision | IMPLEMENTED |
| Schema | CI machine validation | IMPLEMENTED |
| Determinism | repeated output hash equality | IMPLEMENTED |
| Performance | seconds/target and peak memory | IMPLEMENTED / PENDING RUN |
| Figures | measured-only recovery/reliability plots | IMPLEMENTED / PENDING RUN |
| Reproduction | `astrotransit reproduce benchmark-v1` | IMPLEMENTED |
| Documentation | methods, assumptions, references, limitations | IMPLEMENTED |
| Environment | `uv.lock`, requirements lock and Dockerfile | IMPLEMENTED |
| Repository lint | `ruff check .` | IMPLEMENTED |

A release must not convert `PENDING DATA` or `PENDING RUN` into a numeric score.
