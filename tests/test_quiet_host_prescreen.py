"""Offline contracts for deterministic quiet-host preselection."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path("scripts/validation/prescreen_quiet_hosts.py")
SPEC = importlib.util.spec_from_file_location("prescreen_quiet_hosts", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_candidate_pool_excludes_labels_and_requires_two_sectors(tmp_path: Path) -> None:
    pool = tmp_path / "pool.csv"
    pool.write_text(
        "tid,source_id,sector_count,sector_list,st_tmag,st_teff,st_rad\n"
        "1,TIC 1,2,\"1,2\",10,5000,1\n"
        "2,TIC 2,2,\"3,8\",9,4800,0.8\n"
        "3,TIC 3,1,4,9,4700,0.7\n",
        encoding="utf-8",
    )
    labelled = tmp_path / "labels.json"
    labelled.write_text(json.dumps({"cases": [{"target_id": "TIC 1"}]}), encoding="utf-8")
    rows = MODULE._candidate_rows(pool, MODULE._excluded_ids(labelled))
    assert [row["target_id"] for row in rows] == ["TIC 2"]
    assert rows[0]["screen_sectors"] == [3, 8]


def test_current_host_corpus_state_is_consistent() -> None:
    root = Path("validation_runs/v1_injection_recovery/real_noise_v1")
    contract = json.loads((root / "contract.json").read_text(encoding="utf-8"))
    quiet_path = root / "input/quiet_hosts.json"
    if not quiet_path.exists():
        assert contract["status"] == "pending_data"
        assert contract["host_corpus"]["status"] == "pending_data"
        return
    payload = json.loads(quiet_path.read_text(encoding="utf-8"))
    assert payload["status"] == "frozen"
    assert payload["selected_host_count"] == payload["required_host_count"] == 10
    assert len(payload["hosts"]) == 10
    assert contract["status"] == "pending_run"
    assert contract["host_corpus"]["status"] == "frozen"
    assert len({host["target_id"] for host in payload["hosts"]}) == 10
    for host in payload["hosts"]:
        assert len(host["sectors"]) == 2
        assert host["stellar"]["radius_rsun"] > 0
        assert host["stellar"]["mass_msun"] > 0
        assert all(not row["pre_injection_candidate"] for row in host["sector_measurements"])
