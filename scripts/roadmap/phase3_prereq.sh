#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1
LOG="$HOME/phase3_prereq_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== FAZ 3 prerequisite check =="

echo
echo "########## 1) Are all input files present? ##########"
for f in \
  benchmarks/corpora/tfop_disposition_corpus_v1.json \
  benchmarks/corpora/fp_run_subset_v1.json \
  benchmarks/discovery_targets_v4_small_cool_1000_dedup.csv \
  validation_runs/v1_injection_recovery/real_noise_v1/input/quiet_hosts.json \
  outputs/quiet_controls_v1/quiet_controls.json \
  outputs/quiet_controls_v1/selection_audit.json \
  validation_runs/final_acceptance_v1/false_positive_controls/corpus_manifest.json \
  scripts/validation/run_false_positive_controls.py \
  scripts/validation/build_quiet_controls.py \
  tests/test_quiet_control_corpus.py ; do
  if [ -f "$f" ]; then
    echo "  ✅ $f  ($(stat -c%s "$f") bytes)"
  else
    echo "  ❌ MISSING: $f"
  fi
done

echo
echo "########## 2) FP subset — proper inspection ##########"
python - <<'PY'
import json
from pathlib import Path
d = json.loads(Path("benchmarks/corpora/fp_run_subset_v1.json").read_text())
print(f"  type: {type(d).__name__}")
if isinstance(d, list):
    print(f"  count: {len(d)}")
    if d:
        print(f"  first item type: {type(d[0]).__name__}")
        if isinstance(d[0], dict):
            print(f"  first item keys: {list(d[0].keys())}")
            print(f"  first item: {json.dumps(d[0], indent=2)[:400]}")
elif isinstance(d, dict):
    for k, v in d.items():
        if isinstance(v, list):
            print(f"  {k}: list[{len(v)}]")
        else:
            print(f"  {k}: {str(v)[:80]}")
PY

echo
echo "########## 3) corpus_manifest content ##########"
python - <<'PY'
import json
from pathlib import Path
p = Path("validation_runs/final_acceptance_v1/false_positive_controls/corpus_manifest.json")
d = json.loads(p.read_text())
print(f"  keys: {list(d.keys())}")
print(json.dumps(d, indent=2)[:1500])
PY

echo
echo "########## 4) Quiet controls pool — first 5 rows ##########"
python - <<'PY'
import csv
from pathlib import Path
p = Path("benchmarks/discovery_targets_v4_small_cool_1000_dedup.csv")
with p.open() as f:
    reader = csv.DictReader(f)
    print(f"  columns: {reader.fieldnames}")
    for i, row in enumerate(reader):
        if i >= 3: break
        print(f"  row{i}: {dict(list(row.items())[:5])}")
PY

echo
echo "########## 5) prior_hosts (quiet_hosts.json) ##########"
python - <<'PY'
import json
from pathlib import Path
p = Path("validation_runs/v1_injection_recovery/real_noise_v1/input/quiet_hosts.json")
if not p.exists():
    print("  MISSING"); raise SystemExit
d = json.loads(p.read_text())
print(f"  type: {type(d).__name__}")
if isinstance(d, list):
    print(f"  count: {len(d)}")
    if d: print(f"  first: {d[0]}")
elif isinstance(d, dict):
    print(f"  keys: {list(d.keys())[:10]}")
    for k, v in list(d.items())[:3]:
        print(f"  {k}: {str(v)[:120]}")
PY

echo
echo "########## 6) build_quiet_controls --help ##########"
python scripts/validation/build_quiet_controls.py --help 2>&1 | head -30

echo
echo "########## 7) run_false_positive_controls run-shard --help ##########"
python scripts/validation/run_false_positive_controls.py run-shard --help 2>&1 | head -40

echo
echo "########## 8) run_false_positive_controls aggregate --help ##########"
python scripts/validation/run_false_positive_controls.py aggregate --help 2>&1 | head -30

echo
echo "########## 9) TFOP corpus — how many FP/planet? ##########"
python - <<'PY'
import json
from pathlib import Path
from collections import Counter
d = json.loads(Path("benchmarks/corpora/tfop_disposition_corpus_v1.json").read_text())
print(f"  type: {type(d).__name__}")
cases = d if isinstance(d, list) else d.get("cases", d)
if isinstance(cases, list):
    print(f"  total: {len(cases)}")
    labels = Counter(c.get("label") for c in cases if isinstance(c, dict))
    print(f"  labels: {dict(labels)}")
    if cases and isinstance(cases[0], dict):
        print(f"  first keys: {list(cases[0].keys())}")
elif isinstance(cases, dict):
    print(f"  keys: {list(cases.keys())}")
PY

echo
echo "== DONE =="
