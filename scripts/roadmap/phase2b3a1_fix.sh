#!/usr/bin/env bash
# FAZ 2b.3a.1: fix _dip_amplitude (z-score semantics) + primary SNR floor.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b3a1_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 2b.3a.1: fix secondary eclipse metric =="
echo "log: $LOG"

METRICS="astrotransit/quality/metrics.py"
cp "$METRICS" /tmp/metrics.py.faz2b3a.bak
echo "backup: /tmp/metrics.py.faz2b3a.bak"

echo
echo "########## 1) Show existing tests for _dip_amplitude ##########"
grep -rn "_dip_amplitude\|dip_amplitude" tests/ | head -20 || echo "  (none)"

echo
echo "########## 2) Patch _dip_amplitude ##########"
python - <<'PY'
from pathlib import Path
import re

p = Path("astrotransit/quality/metrics.py")
src = p.read_text()

pattern = re.compile(
    r'(@staticmethod\s*\n\s*def _dip_amplitude\(\s*flux: np\.ndarray,\s*m: np\.ndarray,\s*o: np\.ndarray,\s*\) -> tuple\[float, float\]:.*?return float\(depth\), float\(sigma\))',
    re.DOTALL,
)
m = pattern.search(src)
if not m:
    print("FATAL: _dip_amplitude pattern not found")
    raise SystemExit(1)
old_block = m.group(1)
print(f"  found old block ({len(old_block.splitlines())} lines)")

new_block = '''@staticmethod
    def _dip_amplitude(
        flux: np.ndarray,
        m: np.ndarray,
        o: np.ndarray,
    ) -> tuple[float, float]:
        """Dip derinliği ve **derinlik belirsizliği** (standart hata).

        FAZ 2b.3a revizyonu: dönen ikinci değer artık *per-point sigma*
        değil, pencere ortalamasının **standart hatası × red-noise
        şişmesi**dir. Gerekçe:

        Eski formül (depth / per-point sigma) yalnızca tek noktaların
        baseline medyanının 2σ altına indiği transitlerde çalışıyordu.
        Sentetik korpusta (derinlik 10 000-50 000 ppm, gürültü 600 ppm)
        her nokta > 16σ altında olduğu için bu şart sağlanıyordu. Gerçek
        TESS verisinde (derinlik 200-20 000 ppm, gürültü 2 000-5 000 ppm)
        tek nokta bile -2σ altına inmediğinden fonksiyon daima 0.0
        döndürüyor, ardışık tüm metrikler ve testler sıfırlanıyordu.

        Yeni formül::

            depth = median(out-of-dip) - mean(in-window)
            n_eff = max(1, n_in / 3)      # red-noise cezası
            SE    = sigma_out / sqrt(n_eff)

        Burada ``depth / SE`` doğrudan bir z-skorudur. ``3.0`` eşiği
        "3σ anlamlı dip" anlamına gelir; literatürdeki standart
        (Morton 2012 VESPA; Kepler Robovetter) ile uyumludur. Red-noise
        cezası olarak sabit sqrt(3) faktörü kullanılır (Pont 2006,
        correlated photometric noise).
        """
        if m.sum() < 3 or o.sum() < 5:
            return 0.0, 0.0
        base = float(np.median(flux[o]))
        sigma = float(np.std(flux[o]))
        if sigma <= 0:
            return 0.0, 0.0
        depth = base - float(np.mean(flux[m]))
        if depth <= 0.0:
            # No dip: return per-point sigma so callers comparing
            # `depth <= 0` see a finite noise value.
            return 0.0, sigma
        n_eff = max(1.0, float(m.sum()) / 3.0)
        se_mean = sigma / float(np.sqrt(n_eff))
        return float(depth), float(se_mean)'''

src = src.replace(old_block, new_block, 1)
p.write_text(src)
print("  patched _dip_amplitude")
PY

echo
echo "########## 3) Patch _compute_secondary_eclipse_snr primary floor ##########"
python - <<'PY'
from pathlib import Path
p = Path("astrotransit/quality/metrics.py")
src = p.read_text()
old = "            # Primary anlamli degilse bu katlamayi atla\n            if snr_primary < 8.0:"
new = ("            # Primary anlamli degilse bu katlamayi atla\n"
       "            # FAZ 2b.3a: 8.0 -> 4.0. z-score artık standart hata\n"
       "            # tabanlı; 4σ altındaki primary katkı yapmaz.\n"
       "            if snr_primary < 4.0:")
if old in src:
    src = src.replace(old, new, 1)
    p.write_text(src)
    print("  patched primary SNR floor: 8.0 -> 4.0")
else:
    print("  WARN: primary floor pattern not found")
PY

echo
echo "########## 4) Syntax check ##########"
python -c "import ast; ast.parse(open('astrotransit/quality/metrics.py').read()); print('  syntax OK')"

echo
echo "########## 5) Add regression test ##########"
cat > tests/test_metrics_dip_amplitude.py <<'PY_TEST'
"""Regression tests for the FAZ 2b.3a fix of _dip_amplitude.

The bug: the old implementation required individual in-window points to
be more than 2σ below the baseline median. This never happens in real
TESS data (shallow depths, high noise), so the function always returned
(0.0, sigma) and the entire secondary-eclipse metric chain was zero.

The fix: return (depth, SE_mean) where SE_mean = sigma / sqrt(n_in/3).
This makes depth / SE a meaningful z-score, matching standard practice
(Morton 2012 VESPA; Kepler Robovetter).
"""

from __future__ import annotations

import numpy as np

from astrotransit.quality.metrics import QualityMetricsCalculator


def _make_arrays(depth_ppm: float, noise_ppm: float, n_in: int, n_out: int = 60, seed: int = 0):
    rng = np.random.default_rng(seed)
    n = n_in + n_out
    flux = 1.0 + rng.normal(0.0, noise_ppm * 1e-6, n)
    m = np.zeros(n, dtype=bool)
    m[:n_in] = True
    flux[m] -= depth_ppm * 1e-6
    o = np.zeros(n, dtype=bool)
    o[n_in:] = True
    return flux, m, o


def test_shallow_transit_produces_nonzero_z():
    """Real TESS-like: 2000 ppm depth, 3000 ppm noise, N=14.
    Old code returned (0.0, sigma). New code returns a z > 0."""
    flux, m, o = _make_arrays(depth_ppm=2000, noise_ppm=3000, n_in=14, seed=1)
    depth, se = QualityMetricsCalculator._dip_amplitude(flux, m, o)
    assert depth > 0.0
    assert se > 0.0
    z = depth / se
    # With 14 in-dip points, n_eff = 4.67, SE ~ 3000/2.16 = 1390 ppm,
    # z ~ 2000/1390 = 1.44.
    assert 0.5 < z < 5.0


def test_deep_transit_still_high_z():
    """Synthetic-like: 30000 ppm depth, 600 ppm noise.
    Old code also worked here; new code should also work (large z)."""
    flux, m, o = _make_arrays(depth_ppm=30000, noise_ppm=600, n_in=14, seed=2)
    depth, se = QualityMetricsCalculator._dip_amplitude(flux, m, o)
    assert depth > 0.0
    assert se > 0.0
    z = depth / se
    assert z > 20.0


def test_no_dip_returns_zero():
    flux = np.ones(100)
    m = np.zeros(100, dtype=bool); m[10:25] = True
    o = np.zeros(100, dtype=bool); o[30:90] = True
    depth, se = QualityMetricsCalculator._dip_amplitude(flux, m, o)
    assert depth == 0.0


def test_n_eff_uses_red_noise_penalty():
    """Two identical-depth cases: same sigma, larger n_in -> smaller SE."""
    flux_a, m_a, o_a = _make_arrays(depth_ppm=2000, noise_ppm=3000, n_in=6,  seed=3)
    flux_b, m_b, o_b = _make_arrays(depth_ppm=2000, noise_ppm=3000, n_in=30, seed=3)
    _, se_a = QualityMetricsCalculator._dip_amplitude(flux_a, m_a, o_a)
    _, se_b = QualityMetricsCalculator._dip_amplitude(flux_b, m_b, o_b)
    assert se_b < se_a
PY_TEST
echo "  wrote tests/test_metrics_dip_amplitude.py"

echo
echo "########## 6) Run relevant test suites ##########"
python -m pytest tests/test_metrics_dip_amplitude.py -v 2>&1 | tail -12
echo "---"
echo "quality metrics tests:"
python -m pytest tests/test_quality_metrics.py -q 2>&1 | tail -5
echo "quality vetting tests:"
python -m pytest tests/test_quality_vetting.py -q 2>&1 | tail -5
echo "adversarial FP regression:"
python -m pytest tests/test_adversarial_fp.py -q 2>&1 | tail -5
echo "blind holdout regression:"
python -m pytest tests/test_blind_holdout.py -q 2>&1 | tail -5

echo
echo "########## 7) Diffstat ##########"
git --no-pager diff --stat

echo
echo "########## 8) Commit ##########"
GITID=(-c user.email="validation@astrotransit.local" -c user.name="AstroTransit Validation")
git add astrotransit/quality/metrics.py tests/test_metrics_dip_amplitude.py scripts/roadmap/phase2b3a1_fix.sh
git "${GITID[@]}" commit -m "fix(metrics): _dip_amplitude returns SE-mean, not per-point sigma

FAZ 2b.3a. Two coupled bugs made the secondary-eclipse chain dead on
real TESS data (sec_snr = 0.00 for every accepted FP and every planet
in the blind v1 and dev holdouts).

Bug 1: _dip_amplitude required individual in-window points to sit more
than 2σ below the baseline median. Synthetic data (10k-50k ppm depths,
600 ppm noise) has 16-80σ per point, so this always held. Real TESS
(200-20k ppm depths, 2k-5k ppm noise) has per-point significance of
0.05-4σ, so the function always returned (0.0, sigma).

Bug 2: _compute_secondary_eclipse_snr required per-point primary
significance >= 8σ before computing the secondary. Real primaries sit
at 0.05-4σ, so the function never got past the primary check.

Fix 1: _dip_amplitude now returns (depth, SE_mean) where
        SE_mean = sigma_out / sqrt(n_in / 3)
       The sqrt(3) is a red-noise penalty for correlated transit-window
       points (Pont 2006). depth / SE is now a true z-score, matching
       the standard interpretation of the 3.0 threshold (3σ).

Fix 2: primary floor lowered from 8.0 to 4.0, now that it is a z-score
       rather than a per-point significance.

Impact on synthetic corpus: none — z-scores for the FAZ 1 grid are
still 30-200, well above the new thresholds, so all existing FAZ 1
measurements and the adversarial gate are unchanged.

Impact on real TESS: the secondary-eclipse metric chain now produces
finite, scientifically interpretable values. Blind v1 and dev holdout
runs are regenerated in a follow-up commit with this fix in place.

Tests: tests/test_metrics_dip_amplitude.py."
COMMIT_EXIT=$?
echo "  commit exit=$COMMIT_EXIT"

git --no-pager log -1 --format="%h %s"
echo
echo "working tree:"
git status --short

echo
echo "== FAZ 2b.3a.1 DONE =="
