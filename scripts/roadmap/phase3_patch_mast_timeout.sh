#!/usr/bin/env bash
# FAZ 3: bound astroquery MAST timeout. The default 60s * internal retry
# makes single queries hang for 30+ min.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase3_mast_timeout_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== patch MAST timeout =="

M="astrotransit/data/mast_client.py"
cp "$M" /tmp/mast_client.py.faz3.bak

python - <<'PY'
from pathlib import Path
import re

p = Path("astrotransit/data/mast_client.py")
src = p.read_text()

if "astroquery_conf.timeout" in src:
    print("  already patched"); raise SystemExit(0)

# Insert right after `from astropy.table import Table`
anchor = "from astropy.table import Table\n"
if anchor not in src:
    print("FATAL: anchor not found"); raise SystemExit(1)

patch = (
    "from astropy.table import Table\n"
    "\n"
    "# FAZ 3: bound astroquery MAST query timeout. The library default is\n"
    "# 60 s * its own internal retry policy, which together let a single\n"
    "# catalog query hang for tens of minutes on some TIC IDs. 30 s is\n"
    "# generous for MAST and short enough that a stuck query is recoverable.\n"
    "try:\n"
    "    from astroquery import conf as _astroquery_conf\n"
    "    _astroquery_conf.timeout = 30\n"
    "except Exception:  # pragma: no cover - astroquery optional at import\n"
    "    pass\n"
)
src = src.replace(anchor, patch, 1)
p.write_text(src)
print("  patched mast_client.py")
PY

echo
echo "########## Patch entry points with socket.setdefaulttimeout ##########"
for F in \
    scripts/validation/run_false_positive_controls.py \
    scripts/validation/run_blind_holdout.py ; do
    if [ ! -f "$F" ]; then continue; fi
    python - "$F" <<'PY'
import sys
from pathlib import Path

p = Path(sys.argv[1])
src = p.read_text()
if "socket.setdefaulttimeout" in src:
    print(f"  {p}: already patched"); raise SystemExit(0)

# Insert after the first `import sys` line
import re
m = re.search(r"^(import sys\n)", src, re.MULTILINE)
if not m:
    print(f"  {p}: no `import sys`; skipping")
    raise SystemExit(0)

insert = (
    "import sys\n"
    "import socket\n"
    "\n"
    "# FAZ 3: hard cap on any socket operation. Complements astroquery's\n"
    "# own timeout by guaranteeing that even a library ignoring conf.timeout\n"
    "# cannot stall the runner for more than this many seconds.\n"
    "socket.setdefaulttimeout(40)\n"
)
src = src.replace(m.group(1), insert, 1)
p.write_text(src)
print(f"  {p}: socket timeout added")
PY
done

echo
echo "########## Verify ##########"
python -c "import ast; ast.parse(open('$M').read()); print('mast_client syntax OK')"
python -c "import ast; ast.parse(open('scripts/validation/run_false_positive_controls.py').read()); print('fp runner syntax OK')"
python -c "import ast; ast.parse(open('scripts/validation/run_blind_holdout.py').read()); print('blind runner syntax OK')"

ruff check astrotransit/data/mast_client.py scripts/validation/run_false_positive_controls.py scripts/validation/run_blind_holdout.py 2>&1 | tail -5

echo
echo "########## Show patches ##########"
grep -n "astroquery_conf\|_astroquery_conf" "$M"
echo "---"
grep -n "socket.setdefaulttimeout" scripts/validation/run_false_positive_controls.py scripts/validation/run_blind_holdout.py

echo
echo "== DONE =="
