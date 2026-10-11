# AstroTransit — Validation Status

> **Single source of truth** for scientific validation gates.
> Auto-managed. Thresholds are frozen before running and never changed after seeing results.

| Gate | Dataset | Threshold | Result | Status | Commit | Hash |
|------|---------|-----------|--------|--------|--------|------|
| Known targets | 50 | predefined | 46/46 | PASS | `6986a2e` | `N/A` |
| Injection | 888 | predefined | 52.48% | MEASURED | `6986a2e` | `N/A` |
| Adversarial FP | 48 | >=80% | 85.42% | PASS | `6986a2e` | `N/A` |
| Blind holdout v2 | 144 | predefined | 108 eval, recall 0.2642, FPR 0.2364, errors=9 | MEASURED_OPEN | <pending-commit> | `57e60255` (v1) / v2 pending |
| FPP calibration | 200 | predefined | pending | PENDING | `6986a2e` | `N/A` |

## Counts

- **Measured gates:** 4
- **Pending execution gates:** 1
- **Open (failed) gates:** 1

## Rules

1. `PENDING` != `PASS`.
2. Thresholds are frozen **before** running; never changed after seeing results.
3. Every row must be reproducible from the `commit` + dataset hash listed above.
4. The blind holdout is an exam, not a teacher — never tune on it.
5. If a gate fails, fix the algorithm on the **development** dataset, freeze a new version, then re-run.

_Last updated: 2026-10-08T10:23:24Z_
