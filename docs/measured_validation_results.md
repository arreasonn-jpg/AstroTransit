# Measured validation results

Only immutable, provenance-backed campaign outputs are numeric evidence here. `PENDING DATA` and `PENDING RUN` are never converted into scores.

## Known targets — availability-aware N=50 campaign

| Quantity | Measured result |
|---|---:|
| Selected known targets | 50 |
| Evaluable targets | 46 |
| Not evaluated: no measured sector | 4 |
| Detection on evaluable selected subset | 46/46 (100.0%) |
| Joint period + radius recovery | 21/46 (45.6522%) |
| Period recovery | 32/46 (69.5652%) |
| Radius recovery | 23/46 (50.0000%) |
| Sector consistency | 20/38 (52.6316%) |
| False-positive rejection | Not evaluated |

The four unavailable targets are TIC 4610830, TIC 8348911, TIC 14570099 and TIC 17307715. They are excluded from recovery denominators and are not counted as non-detections.

Evidence: [`validation_runs/v1_known_planets/known_planets_50_v1/`](../validation_runs/v1_known_planets/known_planets_50_v1/)

Frozen input SHA-256: `c90de0ff053026f16781a8b8ffcc3e35088cae1385a2138a62e6f93afd54673a`

Aggregate canonical output hash: `6efcb7834f8e310744a76c7ffec0c8b46fc20622b49e7d9203a0c1d123e889d0`

## Real-noise injection recovery — 960 planned trials

The frozen v1 campaign injected box transits after detrending into ten selected real-TESS quiet-host light curves. It recorded all 960 planned trial identities. Availability and detector outcomes remain separate.

| Quantity | Measured result |
|---|---:|
| Planned and recorded trials | 960/960 |
| Evaluable trials | 888 |
| Not evaluated: no observed injected cadence | 72 |
| Data-access failures | 0 |
| Detector errors | 0 |
| Strict period recovery | 450/888 (50.6757%) |
| Strict recovery 95% Wilson interval | 47.3915%–53.9540% |
| Harmonic-aware period recovery | 466/888 (52.4775%) |
| Harmonic-only recoveries | 16 |

### Recovery by execution lane

| Lane | Evaluable/planned | Strict recovery | Harmonic-aware recovery |
|---|---:|---:|---:|
| Cascade single-sector, P ≤ 20 d | 800/800 | 449/800 (56.1250%) | 465/800 (58.1250%) |
| Stitched long-period, P = 50 d | 88/160 | 1/88 (1.1364%) | 1/88 (1.1364%) |

### Recovery by period bin

| Period bin | Strict recovery | Harmonic-aware recovery |
|---|---:|---:|
| Short, P < 5 d | 265/320 (82.8125%) | 271/320 (84.6875%) |
| Mid, 5 ≤ P ≤ 20 d | 184/480 (38.3333%) | 194/480 (40.4167%) |
| Long, P = 50 d | 1/88 (1.1364%) | 1/88 (1.1364%) |

### Recovery by injected depth

| Depth | Strict recovery | Harmonic-aware recovery |
|---|---:|---:|
| 200 ppm | 41/222 (18.4685%) | 44/222 (19.8198%) |
| 500 ppm | 110/222 (49.5495%) | 114/222 (51.3514%) |
| 1000 ppm | 147/222 (66.2162%) | 152/222 (68.4685%) |
| 2000 ppm | 152/222 (68.4685%) | 156/222 (70.2703%) |

Evidence: [`validation_runs/v1_injection_recovery/real_noise_v1/`](../validation_runs/v1_injection_recovery/real_noise_v1/)

Frozen host-corpus SHA-256: `8175058b8b519bffbff8a37a8c7978bb67ad8f1e03b777a9568ed35f21ffbe42`

Frozen grid SHA-256: `a741396df50d6340bb73b4b09c874b32d08b149c8eb67ebe0799853a656ebb21`

Trials SHA-256: `6dff856f848b89b17b14dca33a938ab2bc13ae5830fd25795998ed4dea199a47`

Report SHA-256: `86eb94c77b15c60d7e91de0ca2797e3f87cc64adf3b8ac897ed8b6a7220493d9`

Canonical combined output SHA-256: `c142612b64fb888f76725b45df5e494b3ac8186804c3238b1a8df56a868ba810`

## Interpretation boundaries

The known-target 46/46 value is conditional detection on the selected, evaluable known-target subset. It is not population recall, survey completeness or calibrated precision.

The injection-recovery values measure the detection stage after detrending on the frozen selected real-noise hosts. They are not population completeness or end-to-end preprocessing completeness. The selected ten hosts are not population representative. The 72 long-period scenarios with no injected cadence in an observed window are availability outcomes and are excluded from scientific denominators, not counted as detector failures.

The very low measured 50-day stitched recovery is a recorded pipeline limitation, not an availability-adjusted success. No acceptance threshold was frozen before this run, so the campaign is `MEASURED`, not retroactively declared `PASS`.

## Remaining gates

| Validation area | Status |
|---|---|
| Parameter recovery | N=50 period/radius bias, scatter and RMSE measured; injection-trial parameter-error aggregation and interval coverage pending |
| Injection recovery | 960/960 trial records frozen; 888 evaluable; strict and harmonic-aware recovery measured |
| False positives and quiet controls | Labelled FP/planet input available; ten quiet hosts frozen; controlled run pending |
| FPP calibration | Implemented; labelled holdout run pending |
| Blind test | Implemented; held-out data/run pending |
| TLS/BLS baselines | Implemented; same-corpus run pending |
| Performance | Implemented; measured campaign pending |

The next step is deterministic recovered-parameter analysis from the frozen injection trial table. It must preserve the measured detection results and report unavailable parameter values as `not_evaluated`, never as zero.
