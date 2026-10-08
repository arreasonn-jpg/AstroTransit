# Adversarial FP Leakage Analysis

Total leaks: **7**

## By category

| Category | Count | % |
|---|---:|---:|
| WEAK_ODD_EVEN | 6 | 85.7% |
| OTHER | 1 | 14.3% |

## By family

| Family | Count |
|---|---:|
| grazing_eclipsing_binary | 2 |
| eclipsing_binary_v | 2 |
| blended_diluted_eb | 1 |
| eb_with_secondary_eclipse | 1 |
| odd_even_alternating_eb | 1 |

## Per-scenario detail

| Scenario | Family | Category | FPP | Reasons |
|---|---|---|---|---|
| `blended_diluted_eb:000` | blended_diluted_eb | WEAK_ODD_EVEN | 0.039474 | odd_even_mismatch=0.80 (weak) |
| `grazing_eclipsing_binary:001` | grazing_eclipsing_binary | WEAK_ODD_EVEN | 0.094737 | odd_even_mismatch=0.18 (weak) |
| `eclipsing_binary_v:003` | eclipsing_binary_v | WEAK_ODD_EVEN | 0.047368 | odd_even_mismatch=0.00 (weak) |
| `eclipsing_binary_v:004` | eclipsing_binary_v | OTHER | 0.094737 | transit_symmetry=0.993 (asymmetric) |
| `grazing_eclipsing_binary:004` | grazing_eclipsing_binary | WEAK_ODD_EVEN | 0.039474 | odd_even_mismatch=0.18 (weak) |
| `eb_with_secondary_eclipse:006` | eb_with_secondary_eclipse | WEAK_ODD_EVEN | 0.086842 | odd_even_mismatch=0.74 (weak) |
| `odd_even_alternating_eb:007` | odd_even_alternating_eb | WEAK_ODD_EVEN | 0.039474 | odd_even_mismatch=0.18 (weak) |
