"""DEV-only evaluation: run the full pipeline on the balanced24 dev corpus and
dump per-sector vetting/metric rows. NEVER touches the blind holdout manifest.

Red line (docs/blind_recall_roadmap.md): all recall fixes are validated on this
dev corpus first; the blind holdout is run exactly once at the end.

Writes validation_runs/_triage/dev_eval_shard0.json (triage dir, not a gate).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from astrotransit.pipelines.orchestrator import AstroTransitOrchestrator
import scripts.validation.run_blind_holdout as blind_runner

# Windows has no SIGALRM; the dev runner is local-only, so use a no-op time limit.
if not hasattr(blind_runner.signal, "SIGALRM"):
    from contextlib import contextmanager

    @contextmanager
    def _noop_time_limit(seconds):
        yield

    blind_runner._time_limit = _noop_time_limit

_evaluate_case = blind_runner._evaluate_case

MANIFEST = ROOT / "validation_runs/final_acceptance_v1/dev_holdout/dev_manifest_balanced24.json"
OUT = ROOT / "validation_runs/_triage/dev_eval_shard0.json"


def _f(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = []
    with AstroTransitOrchestrator(force_map=True, skip_visualization=True, log_level="WARNING") as orch:
        for i, case in enumerate(manifest["cases"], 1):
            row = _evaluate_case(case, orch, sector_client=None)
            rows.append(row)
            print(f"[{i}/{len(manifest['cases'])}] {row['target_id']} ({case['label']}): accepted={row.get('accepted_candidate')} err={str(row.get('error',''))[:60]}", flush=True)
            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(json.dumps({"rows": rows}, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
