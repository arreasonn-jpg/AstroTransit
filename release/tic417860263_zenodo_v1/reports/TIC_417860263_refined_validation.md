# TIC 417860263 — Refined Multi-Sector Validation

## Ephemeris Refinement (S57+S58)
- **Initial T0**: 2854.378905 BTJD
- **Initial P**: 2.8535114704 d
- **Refined T0**: 2854.36844461 ± 0.01253756 BTJD
- **Refined P**: 2.8540582116 ± 0.0011403164 d
- **ΔP**: +47.2384 seconds
- **Reduced χ²**: 441.51
- **RMS residual**: 59.49 min
- **Transits used**: 19 (clipped: 0)

## Forced Validation with Refined Ephemeris

- **Sectors tested**: 6
- **Sectors with detection**: 4
- **Detected in**: [57, 58, 77, 78]
- **Combined depth**: 228.7 ± 4.9 ppm
- **Combined SNR**: 46.87
- **All odd-even consistent**: False

### Per-Sector

| Sector | Detrend | Depth (ppm) | Err | SNR | Detected | Odd | Even | Diff | OE |
|---:|:---:|---:|---:|---:|:---:|---:|---:|---:|:---:|
| 57 | AT | 585.4 | 10.2 | 57.36 | ✓ | 565.6 | 612.4 | 46.8 | ✗ |
| 58 | AT | 247.4 | 7.7 | 32.07 | ✓ | 210.8 | 284.6 | 73.8 | ✗ |
| 77 | AT | 219.8 | 24.0 | 9.16 | ✓ | 181.9 | 273.5 | 91.6 | ✗ |
| 78 | AT | 85.8 | 15.6 | 5.51 | ✓ | -113.1 | 239.5 | 352.6 | ✗ |
| 84 | AT | -171.5 | 13.4 | -12.81 | ✗ | -253.7 | -90.9 | 162.9 | ✗ |
| 85 | AT | 11.6 | 15.5 | 0.75 | ✗ | 59.0 | -28.3 | 87.3 | ✗ |

## Interpretation
- **Strong multi-sector support**: 4/6 sectors.
- **Odd-even warning**: sectors [57, 58, 77, 78, 84, 85].
- **Combined SNR = 46.9**: strong.
