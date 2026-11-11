# AstroTransit — Validation Status

> **Single source of truth** for scientific validation gates.
> Auto-managed. Thresholds are frozen before running and never changed after seeing results.

| Gate | Dataset | Threshold | Result | Status | Commit | Hash |
|------|---------|-----------|--------|--------|--------|------|
| Known targets | 50 | predefined | 46/46 | PASS | `6986a2e` | `N/A` |
| Injection | 888 | predefined | 52.48% | MEASURED | `6986a2e` | `N/A` |
| Adversarial FP | 48+8 | >=80% / >=50% ctrl | 85.42% / 8/8 ctrl | PASS | `c4dac84` | `2e2b434d` |
| Labelled FP + quiet | 100+100 | 100 eval + 0 err | FP rej 55%, quiet FAR 48%, 0 err | MEASURED_PASS | `360625c` | `a59e2454` |
| Blind holdout v2 | 144 | recall>=0.5 / FPR<=0.6 | 108 eval, recall 0.2642, FPR 0.2364, errors=9 | MEASURED_OPEN | `<pending>` | `57e60255` |
| FPP calibration | 200 | predefined | pending | PENDING | `<pending>` | `N/A` |

## Counts

- **Closed gates:** 3 (parameter_recovery, adversarial_false_positives, labelled_fp_quiet_controls)
- **Measured but open:** 1 (blind_domain_holdout — recall below floor)
- **Pending execution:** 1 (fpp_quality_calibration)
- **Contract missing:** 5 (robustness, baselines, mcmc, performance, reproduction)

## Rules

1. `PENDING` != `PASS`.
2. Thresholds are frozen **before** running; never changed after seeing results.
3. Every row must be reproducible from the `commit` + dataset hash listed above.
4. The blind holdout is an exam, not a teacher — never tune on it.
5. If a gate fails, fix the algorithm on the **development** dataset, freeze a new version, then re-run.

_Last updated: 2026-10-17_
