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

## Interpretation boundary

The 46/46 value is conditional detection on this selected, evaluable known-target subset. It is not population recall, survey completeness or calibrated precision. This campaign does not evaluate false-positive rejection, quiet-control false-positive rate, injection-recovery completeness, FPP calibration, blind-test performance or population-level radius accuracy.

## Remaining gates

| Validation area | Status |
|---|---|
| Parameter recovery | N=50 known-target point estimates measured; bias/scatter/RMSE/coverage campaign pending |
| Injection recovery | Implemented; measured campaign pending |
| False positives and quiet controls | Labelled FP/planet input available; quiet controls and run pending |
| FPP calibration | Implemented; labelled holdout run pending |
| Blind test | Implemented; held-out data/run pending |
| TLS/BLS baselines | Implemented; same-corpus run pending |
| Performance | Implemented; measured campaign pending |

The next high-value step is empirical parameter-recovery analysis, not another validation framework component.
