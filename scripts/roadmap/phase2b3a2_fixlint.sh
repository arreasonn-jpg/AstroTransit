#!/usr/bin/env bash
# Quick fix: restore SimpleNamespace style for _metrics helper, add the
# two new fields, re-commit.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b3a2_fixlint_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== fixlint =="
echo "log: $LOG"

python - <<'PY'
from pathlib import Path
import re

p = Path("tests/test_quality_vetting.py")
src = p.read_text()

pattern = re.compile(
    r'def _metrics\(.*?\n\)\s*(?:->\s*[\w\.]+)?\s*:\s*\n(?:.*\n)*?    \)',
    re.MULTILINE,
)
m = pattern.search(src)
if not m:
    print("FATAL: _metrics block not found")
    raise SystemExit(1)

new_helper = '''def _metrics(
    odd_even=0.0,
    secondary=0.0,
    secondary_snr=0.0,
    variable=False,
    amplitude=0.0,
    depth_var=0.0,
    n_transits=5,
    symmetry=0.5,
    completeness=0.95,
    ls_peak=0.0,
    harmonic=0.0,
    shape=0.0,
):
    return SimpleNamespace(
        transit=SimpleNamespace(
            odd_even_mismatch=odd_even,
            depth_variance=depth_var,
            n_transits=n_transits,
            transit_symmetry=symmetry,
            odd_even_harmonic=harmonic,
            shape_correlation=shape,
        ),
        stellar=SimpleNamespace(
            secondary_eclipse_depth=secondary,
            secondary_eclipse_snr=secondary_snr,
            is_variable_star=variable,
            variability_amplitude=amplitude,
            lomb_scargle_peak=ls_peak,
        ),
        photometric=SimpleNamespace(data_completeness=completeness),
    )'''

src = src[:m.start()] + new_helper + src[m.end():]
p.write_text(src)
print("  restored SimpleNamespace style for _metrics")
PY

echo
echo "########## Verify ##########"
python -m pytest tests/test_quality_vetting.py -q 2>&1 | tail -3
ruff check tests/test_quality_vetting.py tests/test_metrics_dip_amplitude.py 2>&1 | tail -3

echo
echo "########## Re-stage + retry commit ##########"
git add tests/test_quality_vetting.py

GITID=(-c user.email="validation@astrotransit.local" -c user.name="AstroTransit Validation")
git "${GITID[@]}" commit -F /tmp/faz2b3a_commit_msg.txt
COMMIT_EXIT=$?
echo "  commit exit=$COMMIT_EXIT"

git --no-pager log -2 --format="%h %s"
echo
echo "working tree:"
git status --short
echo
echo "== fixlint DONE =="
