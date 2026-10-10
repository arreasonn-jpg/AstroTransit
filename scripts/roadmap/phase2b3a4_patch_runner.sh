#!/usr/bin/env bash
# Add per-target timeout + incremental checkpoint to run_blind_holdout.py
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase2b3a4_patch_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== PATCH RUNNER =="

R="scripts/validation/run_blind_holdout.py"
cp "$R" /tmp/run_blind_holdout.py.faz2b3a4.bak
echo "backup: /tmp/run_blind_holdout.py.faz2b3a4.bak"

echo
echo "########## 1) Add _time_limit helper after imports ##########"
python - <<'PY'
from pathlib import Path
import re

p = Path("scripts/validation/run_blind_holdout.py")
src = p.read_text()

if "def _time_limit" in src:
    print("  already patched")
    raise SystemExit(0)

# Find a good insertion point: after the last import at module level
# We'll insert right after `from typing import ...` line
m = re.search(r"^(from typing import [^\n]+\n)", src, re.MULTILINE)
if not m:
    print("FATAL: typing import not found")
    raise SystemExit(1)

helper = '''
import signal
from contextlib import contextmanager


@contextmanager
def _time_limit(seconds: int):
    """Signal-based timeout around a single operation.

    FAZ 2b.3a.4: MAST TIC catalog queries occasionally hang for many
    minutes, blocking an entire shard. We bound each target's pipeline
    call to ``seconds`` so a single slow target cannot starve the shard.
    """
    def _handler(signum, frame):
        raise TimeoutError(f"per-target timeout after {seconds}s")

    old = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(int(seconds))
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)

'''

src = src[:m.end(1)] + helper + src[m.end(1):]
p.write_text(src)
print("  inserted _time_limit helper")
PY

echo
echo "########## 2) Wrap orchestrator.run_single in timeout ##########"
python - <<'PY'
from pathlib import Path
p = Path("scripts/validation/run_blind_holdout.py")
src = p.read_text()

old = """    try:
        result = orchestrator.run_single(row["target_id"], sectors=requested)"""
new = """    try:
        with _time_limit(PER_TARGET_TIMEOUT_SECONDS):
            result = orchestrator.run_single(row["target_id"], sectors=requested)"""

if old in src:
    src = src.replace(old, new, 1)
    p.write_text(src)
    print("  wrapped run_single in _time_limit")
else:
    print("  WARN: run_single call not found")
PY

echo
echo "########## 3) Add PER_TARGET_TIMEOUT constant ##########"
python - <<'PY'
from pathlib import Path
p = Path("scripts/validation/run_blind_holdout.py")
src = p.read_text()
if "PER_TARGET_TIMEOUT_SECONDS" in src:
    print("  already defined")
    raise SystemExit(0)
# Insert near the top, after REQUIRED_OUTPUT line
anchor = 'REQUIRED_OUTPUT = "validation_runs/final_acceptance_v1/blind_holdout/report.json"'
if anchor in src:
    src = src.replace(
        anchor,
        anchor + "\n\n#: FAZ 2b.3a.4: per-target wall-clock bound. Realistic targets\n"
                 "#: take 3-7 min; 6 min is generous without letting a hung MAST\n"
                 "#: query block the entire shard.\n"
                 "PER_TARGET_TIMEOUT_SECONDS = 360",
        1,
    )
    p.write_text(src)
    print("  added PER_TARGET_TIMEOUT_SECONDS = 360")
else:
    print("  WARN: anchor not found")
PY

echo
echo "########## 4) Add incremental checkpoint ##########"
python - <<'PY'
from pathlib import Path
import re

p = Path("scripts/validation/run_blind_holdout.py")
src = p.read_text()

# Find the existing `rows = [_evaluate_case(...) ...]` list comprehension and
# replace it with an explicit loop that writes checkpoints.
old = """            rows = [_evaluate_case(case, orchestrator, sector_client) for case in selected]

    payload = {
        "schema_version": ROW_VERSION,
        "campaign": CAMPAIGN,
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "case_count": len(rows),
        "holdout_sha256": manifest["holdout_sha256"],
        "rows": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json(payload))
    print(f"Wrote shard {args.shard_index}: {len(rows)} cases -> {output}")
    return 0"""

new = """            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)

            def _save_partial(rows_so_far):
                payload_partial = {
                    "schema_version": ROW_VERSION,
                    "campaign": CAMPAIGN,
                    "shard_index": args.shard_index,
                    "shard_count": args.shard_count,
                    "case_count": len(rows_so_far),
                    "holdout_sha256": manifest["holdout_sha256"],
                    "partial": True,
                    "rows": rows_so_far,
                }
                try:
                    output.write_bytes(canonical_json(payload_partial))
                except Exception as exc:  # noqa: BLE001
                    print(f"  checkpoint write failed: {exc}")

            # FAZ 2b.3a.4: process one target at a time and save after each,
            # so a later timeout cannot destroy already-evaluated rows.
            rows = []
            for idx, case in enumerate(selected, 1):
                row = _evaluate_case(case, orchestrator, sector_client)
                rows.append(row)
                tid = row.get("target_id", "?")
                if row.get("error"):
                    status = f"error({row['error'][:60]})"
                elif row.get("accepted_candidate"):
                    status = "accepted"
                else:
                    status = "rejected"
                print(f"  [{idx}/{len(selected)}] {tid}: {status}", flush=True)
                _save_partial(rows)

    payload = {
        "schema_version": ROW_VERSION,
        "campaign": CAMPAIGN,
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "case_count": len(rows),
        "holdout_sha256": manifest["holdout_sha256"],
        "rows": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json(payload))
    print(f"Wrote shard {args.shard_index}: {len(rows)} cases -> {output}")
    return 0"""

if old in src:
    src = src.replace(old, new, 1)
    p.write_text(src)
    print("  added incremental checkpointing")
else:
    print("  WARN: rows list comprehension not found verbatim")
PY

echo
echo "########## 5) Syntax check + offline test ##########"
python -c "import ast; ast.parse(open('scripts/validation/run_blind_holdout.py').read()); print('  syntax OK')"
python scripts/validation/run_blind_holdout.py --help 2>&1 | head -3

echo
echo "########## 6) Test offline with dev manifest ##########"
TMPD=$(mktemp -d)
python scripts/validation/run_blind_holdout.py run-shard \
    --manifest validation_runs/final_acceptance_v1/dev_holdout/dev_manifest.json \
    --shard-index 0 --shard-count 1 --offline \
    --output "$TMPD/test.json" 2>&1 | tail -3
[ -f "$TMPD/test.json" ] && echo "  offline output OK: $(stat -c%s $TMPD/test.json) bytes"

echo
echo "########## 7) Run unit tests ##########"
python -m pytest tests/test_blind_holdout.py tests/test_validation_blind_holdout_full.py -q 2>&1 | tail -3

echo
echo "########## 8) Diffstat + commit ##########"
git --no-pager diff --stat scripts/validation/run_blind_holdout.py
GITID=(-c user.email="validation@astrotransit.local" -c user.name="AstroTransit Validation")
git add scripts/validation/run_blind_holdout.py scripts/roadmap/phase2b3a4_patch_runner.sh scripts/roadmap/phase2b3a4_diag.sh scripts/roadmap/phase2b3a4_recover.sh
git "${GITID[@]}" commit -m "harden(blind-holdout): per-target timeout + incremental checkpoint

FAZ 2b.3a.4. Two operational fixes to survive MAST TIC catalog
slowdowns without losing work:

1. Wrap orchestrator.run_single in a 360 s signal-based timeout
   (_time_limit). A single hung MAST query no longer starves the
   entire shard for 40+ min; it is recorded as
   error=per-target_timeout:<n>s and the shard moves on.

2. Incremental checkpointing in run_shard. Instead of building the
   whole rows list and writing the shard JSON once at the end, we now
   write the shard file after every target (with partial=True until
   the last one). If the shard times out, all completed targets
   survive on disk.

Motivation: today's recovery run had 9/12 shards time out at the
40-minute wall, all in get_stellar_properties() (MAST TIC catalog).
Three shards had completed 1-7 targets each; those rows were lost
because the shard file was never written."
COMMIT_EXIT=$?
echo "  commit exit=$COMMIT_EXIT"
git --no-pager log -1 --format="%h %s"
git status --short | head -10

echo
echo "== PATCH DONE =="
