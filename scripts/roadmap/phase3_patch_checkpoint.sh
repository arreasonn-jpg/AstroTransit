#!/usr/bin/env bash
# Add incremental checkpoint to FP+Quiet runner.
set -uo pipefail
cd "$HOME/AstroTransit" || exit 1
source .venv/bin/activate || exit 1

LOG="$HOME/phase3_patch_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "== patch incremental checkpoint =="

R="scripts/validation/run_false_positive_controls.py"
cp "$R" /tmp/run_fp_controls.py.faz3.bak3

echo
echo "########## 1) Inspect target loop (lines 240-290) ##########"
sed -n '240,290p' "$R"

echo
echo "########## 2) Apply patch ##########"
python - <<'PY'
from pathlib import Path

p = Path("scripts/validation/run_false_positive_controls.py")
src = p.read_text()

# The list comprehension to replace
old = '        rows = [_evaluate_case(case, orchestrator, sector_client) for case in selected]\n'
new = '''        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)

        def _save_partial(rows_so_far):
            payload_partial = {
                "shard_index": args.shard_index,
                "shard_count": args.shard_count,
                "case_count": len(rows_so_far),
                "partial": True,
                "rows": rows_so_far,
            }
            try:
                output.write_text(json.dumps(payload_partial, indent=2, sort_keys=True))
            except Exception as exc:
                print(f"  checkpoint write failed: {exc}", flush=True)

        rows = []
        for idx, case in enumerate(selected, 1):
            row = _evaluate_case(case, orchestrator, sector_client)
            rows.append(row)
            tid = row.get("target_id", "?")
            if row.get("error"):
                status = f"error({str(row['error'])[:60]})"
            else:
                status = str(row.get("outcome", "?"))
            print(f"  [{idx}/{len(selected)}] {tid}: {status}", flush=True)
            _save_partial(rows)
'''

if old not in src:
    print("FATAL: pattern not found")
    raise SystemExit(1)

src = src.replace(old, new, 1)
p.write_text(src)
print("  checkpoint added")
PY

echo
echo "########## 3) Verify ##########"
python -c "import ast; ast.parse(open('$R').read()); print('  syntax OK')"
ruff check "$R" 2>&1 | tail -3

echo
echo "########## 4) Show checkpoint code ##########"
grep -n "_save_partial\|for idx, case in enumerate(selected" "$R"

echo
echo "== DONE =="
