"""FPP kalibrasyon kampanyasının kohort seçimi, raporu ve kapı sözleşmesi.

Testler çevrimdışı koşar: hiçbir MAST erişimi gerekmez, yalnızca dondurulmuş
seçim kuralları ve sentetik kampanya satırları kullanılır.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import scripts.validation.run_fpp_calibration_campaign as campaign
from astrotransit.validation.fpp_calibration import (
    FPP_CALIBRATION_SEED,
    MIN_BLIND_TEST_CASES,
    build_fpp_calibration_report,
)



def _corpus(path: Path, fp: int, planets: int, quiet: int = 0) -> Path:
    cases = []
    for index in range(fp):
        cases.append(
            {
                "target_id": f"TIC {1000 + index}",
                "label": "false_positive",
                "reference": f"tfop:FP:{1000 + index}",
                "sectors": [],
                "notes": "",
            }
        )
    for index in range(planets):
        cases.append(
            {
                "target_id": f"TIC {2000 + index}",
                "label": "planet",
                "reference": f"tfop:KP:{2000 + index}",
                "sectors": [],
                "notes": "",
            }
        )
    for index in range(quiet):
        cases.append(
            {
                "target_id": f"TIC {3000 + index}",
                "label": "quiet_star",
                "reference": f"catalog_negative:{3000 + index}",
                "sectors": [],
                "notes": "",
            }
        )
    path.write_text(json.dumps({"corpus_version": "test", "cases": cases}), encoding="utf-8")
    return path


def _prior_hosts(path: Path, ids: list[str]) -> Path:
    path.write_text(json.dumps({"hosts": [{"target_id": item} for item in ids]}), encoding="utf-8")
    return path


def test_cohort_selection_is_deterministic_and_detector_independent(tmp_path: Path):
    corpus = _corpus(tmp_path / "corpus.json", fp=150, planets=120)
    hosts = _prior_hosts(tmp_path / "hosts.json", [])
    first, first_audit = campaign.select_cohorts(corpus, hosts, required=100, seed=campaign.COHORT_SEED)
    second, second_audit = campaign.select_cohorts(corpus, hosts, required=100, seed=campaign.COHORT_SEED)

    assert first == second
    assert first_audit["cohort_sha256"] == second_audit["cohort_sha256"]
    assert first["status"] == "frozen"
    assert first["counts"] == {"false_positive": 100, "planet": 100}
    assert first["selection"]["detector_used_for_selection"] is False
    ids = [row["target_id"] for row in first["cases"]]
    assert len(ids) == len(set(ids)) == 200
    fp_ids = {row["target_id"] for row in first["cases"] if row["label"] == "false_positive"}
    planet_ids = {row["target_id"] for row in first["cases"] if row["label"] == "planet"}
    assert not fp_ids & planet_ids


def test_cohort_selection_excludes_prior_injection_hosts(tmp_path: Path):
    corpus = _corpus(tmp_path / "corpus.json", fp=150, planets=120)
    all_ids = [f"TIC {1000 + index}" for index in range(150)]
    hosts = _prior_hosts(tmp_path / "hosts.json", all_ids[:40])
    payload, audit = campaign.select_cohorts(corpus, hosts, required=100, seed=campaign.COHORT_SEED)
    selected = {row["target_id"] for row in payload["cases"]}
    assert not selected & {f"TIC {1000 + index}" for index in range(40)}
    assert audit["rejection_counts"]["prior_injection_host"] == 40


def test_cohort_selection_reports_insufficient_pool(tmp_path: Path):
    corpus = _corpus(tmp_path / "corpus.json", fp=30, planets=25)
    hosts = _prior_hosts(tmp_path / "hosts.json", [])
    payload, audit = campaign.select_cohorts(corpus, hosts, required=100, seed=campaign.COHORT_SEED)
    assert payload["status"] == "insufficient_candidates"
    assert audit["rejection_counts"]["insufficient_pool_for_false_positive"] == 1
    assert audit["rejection_counts"]["insufficient_pool_for_planet"] == 1


def test_frozen_manifest_verification_rejects_drift(tmp_path: Path):
    corpus = _corpus(tmp_path / "corpus.json", fp=150, planets=150)
    hosts = _prior_hosts(tmp_path / "hosts.json", [])
    payload, audit = campaign.select_cohorts(corpus, hosts, required=100, seed=campaign.COHORT_SEED)
    good = tmp_path / "manifest.json"
    good.write_text(json.dumps({"cohort_sha256": audit["cohort_sha256"],
                                "selected_count": payload["selected_count"],
                                "seed": audit["seed"],
                                "sources": audit["sources"]}), encoding="utf-8")
    campaign._verify_frozen_manifest(payload, audit, good)

    drifted = tmp_path / "drifted.json"
    drifted.write_text(json.dumps({"cohort_sha256": "0" * 64,
                                    "selected_count": payload["selected_count"],
                                    "seed": audit["seed"],
                                    "sources": audit["sources"]}), encoding="utf-8")
    with pytest.raises(ValueError, match="cohort_sha256"):
        campaign._verify_frozen_manifest(payload, audit, drifted)

    with pytest.raises(ValueError, match="frozen cohort manifest missing"):
        campaign._verify_frozen_manifest(payload, audit, tmp_path / "absent.json")


def _rows(fp_count: int, planet_count: int, *, fp_fpp, planet_fpp, quiet_count: int = 0):
    rows = []
    for index in range(fp_count):
        value = fp_fpp(index)
        rows.append(
            {
                "target_id": f"TIC {5000 + index}",
                "label": "false_positive",
                "evaluated": True,
                "accepted_candidate": True,
                "error": "",
                "target_fpp_available": True,
                "target_fpp": value,
                "target_fpp_method": "heuristic_vetting_weighted_vote",
                "target_fpp_availability_reason": "ok",
            }
        )
    for index in range(planet_count):
        value = planet_fpp(index)
        rows.append(
            {
                "target_id": f"TIC {6000 + index}",
                "label": "planet",
                "evaluated": True,
                "accepted_candidate": True,
                "error": "",
                "target_fpp_available": True,
                "target_fpp": value,
                "target_fpp_method": "heuristic_vetting_weighted_vote",
                "target_fpp_availability_reason": "ok",
            }
        )
    for index in range(quiet_count):
        rows.append(
            {
                "target_id": f"TIC {7000 + index}",
                "label": "quiet_star",
                "evaluated": True,
                "accepted_candidate": index % 5 == 0,
                "error": "",
                "target_fpp_available": True,
                "target_fpp": 0.4,
                "target_fpp_method": "heuristic_vetting_weighted_vote",
                "target_fpp_availability_reason": "ok",
            }
        )
    return rows


def test_separable_cohorts_close_the_report_status(tmp_path: Path):
    rows = _rows(80, 80, fp_fpp=lambda i: 0.75 + 0.002 * i, planet_fpp=lambda i: 0.02 + 0.002 * i, quiet_count=40)
    report = build_fpp_calibration_report(rows, seed=FPP_CALIBRATION_SEED)
    assert report["status"] == "measured", report["blocking_reasons"]
    assert report["blocking_reasons"] == []
    assert report["cases"]["n_cases"] == 160
    assert report["cases"]["false_positive_cases"] == 80
    assert report["cases"]["planet_cases"] == 80
    assert set(report["splits"]) == {"development", "validation", "blind_test"}
    assert report["splits"]["blind_test"]["n_cases"] >= MIN_BLIND_TEST_CASES
    assert report["splits"]["blind_test"]["roc_auc"] >= 0.5
    assert report["splits"]["blind_test"]["brier_score"] < 0.25
    # quiet_star satırları etiket değildir: 40 satır metrikleri etkilemez.
    assert report["cohorts"]["quiet_controls"]["labelled_count"] == 40
    assert report["cohorts"]["quiet_controls"]["role"] == "reported_only_not_a_calibration_label"
    assert report["cohorts"]["quiet_controls"]["accepted_candidate_count"] == 8
    assert report["method"]["calibration_transform_applied"] is False
    assert report["threshold_sweep"]["development_only"] is True
    assert report["threshold_sweep"]["minimum_brier_threshold"] is not None


def test_uninformative_proxy_cannot_close_the_gate():
    rows = _rows(80, 80, fp_fpp=lambda i: 0.5, planet_fpp=lambda i: 0.5)
    report = build_fpp_calibration_report(rows, seed=FPP_CALIBRATION_SEED)
    assert report["status"] == "pending_run"
    assert any("blind_test_roc_auc" in reason for reason in report["blocking_reasons"])


def test_report_detects_label_conflicts_and_duplicates():
    rows = _rows(80, 80, fp_fpp=lambda i: 0.8, planet_fpp=lambda i: 0.1)
    rows.append(dict(rows[0], label="planet"))
    report = build_fpp_calibration_report(rows, seed=FPP_CALIBRATION_SEED)
    assert report["data_integrity"]["duplicate_target_ids"] == 1
    assert report["data_integrity"]["conflicting_label_targets"]


def test_empty_input_is_rejected_not_scored():
    with pytest.raises(ValueError, match="en az bir kampanya satırı"):
        build_fpp_calibration_report([])


def _write_shards(tmp_path: Path, rows: list[dict], shard_count: int = 4) -> Path:
    shards = tmp_path / "shards"
    shards.mkdir(parents=True, exist_ok=True)
    for index in range(shard_count):
        selected = [row for position, row in enumerate(rows) if position % shard_count == index]
        payload = {
            "schema_version": "1.0",
            "campaign": campaign.CAMPAIGN,
            "shard_index": index,
            "shard_count": shard_count,
            "case_count": len(selected),
            "rows": selected,
        }
        (shards / f"shard-{index:02d}.json").write_text(json.dumps(payload), encoding="utf-8")
    return shards


def _args(tmp_path: Path, shards: Path, **overrides):
    values = {
        "shards": shards,
        "rows": None,
        "shard_count": 4,
        "min_per_label": 60,
        "threshold": 0.5,
        "split_seed": FPP_CALIBRATION_SEED,
        "cohort_manifest": tmp_path / "absent-manifest.json",
        "config": tmp_path / "config.toml",
        "output": tmp_path / "report.json",
        "cases_output": tmp_path / "cases.json",
        "rows_out": tmp_path / "rows.jsonl",
        "manifest": tmp_path / "manifest.json",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_aggregate_produces_gate_artifact(tmp_path: Path):
    (tmp_path / "config.toml").write_text("[general]\nseed = 42\n", encoding="utf-8")
    corpus = _corpus(tmp_path / "corpus.json", fp=150, planets=150)
    hosts = _prior_hosts(tmp_path / "hosts.json", [])
    payload, audit = campaign.select_cohorts(corpus, hosts, required=100, seed=campaign.COHORT_SEED)
    manifest = tmp_path / "cohort_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "selection": payload["selection"],
                "cohort_sha256": audit["cohort_sha256"],
                "selected_count": payload["selected_count"],
                "sources": audit["sources"],
            }
        ),
        encoding="utf-8",
    )

    rows = _rows(80, 80, fp_fpp=lambda i: 0.75 + 0.002 * i, planet_fpp=lambda i: 0.02 + 0.002 * i)
    args = _args(tmp_path, _write_shards(tmp_path, rows), cohort_manifest=manifest)
    assert campaign.aggregate(args) == 0

    report = json.loads(args.output.read_text(encoding="utf-8"))
    assert report["campaign"] == "fpp_quality_calibration_v1"
    assert report["status"] == "measured"
    assert report["recorded_rows"] == 160
    assert report["cohorts"]["frozen_selection"]["detector_used_for_selection"] is False
    assert report["cohorts"]["frozen_selection"]["cohort_sha256"] == audit["cohort_sha256"]
    assert report["provenance"]["git_commit"]
    assert len(report["rows_sha256"]) == 64
    assert report["data_integrity"]["zero_filled_missing_fpp_count"] == 0
    cases_payload = json.loads(args.cases_output.read_text(encoding="utf-8"))
    assert len(cases_payload["cases"]) == 160
    assert all(0.0 <= case["fpp"] <= 1.0 for case in cases_payload["cases"])
    gate_manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    assert gate_manifest["status"] == "measured"
    assert gate_manifest["rows_sha256"] == report["rows_sha256"]
    assert gate_manifest["recorded_rows"] == 160


def test_aggregate_refuses_incomplete_shards(tmp_path: Path):
    (tmp_path / "config.toml").write_text("[general]\n", encoding="utf-8")
    rows = _rows(80, 80, fp_fpp=lambda i: 0.8, planet_fpp=lambda i: 0.1)
    shards = _write_shards(tmp_path, rows, shard_count=4)
    (shards / "shard-03.json").unlink()
    with pytest.raises(FileNotFoundError, match="missing shard"):
        campaign.aggregate(_args(tmp_path, shards))

    short = tmp_path / "short"
    short.mkdir()
    rows_missing_planets = [row for row in rows if row["label"] == "false_positive"]
    for index in range(4):
        (short / f"shard-{index:02d}.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "campaign": campaign.CAMPAIGN,
                    "shard_index": index,
                    "shard_count": 4,
                    "case_count": 0,
                    "rows": [row for pos, row in enumerate(rows_missing_planets) if pos % 4 == index],
                }
            ),
            encoding="utf-8",
        )
    with pytest.raises(ValueError, match="insufficient labelled planet"):
        campaign.aggregate(_args(tmp_path, short))


def test_aggregate_rejects_foreign_campaign_shards(tmp_path: Path):
    (tmp_path / "config.toml").write_text("[general]\n", encoding="utf-8")
    rows = _rows(80, 80, fp_fpp=lambda i: 0.8, planet_fpp=lambda i: 0.1)
    shards = tmp_path / "foreign"
    shards.mkdir()
    for index in range(4):
        (shards / f"shard-{index:02d}.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "campaign": "something_else",
                    "shard_index": index,
                    "shard_count": 4,
                    "case_count": 0,
                    "rows": [row for pos, row in enumerate(rows) if pos % 4 == index],
                }
            ),
            encoding="utf-8",
        )
    with pytest.raises(ValueError, match="unexpected campaign"):
        campaign.aggregate(_args(tmp_path, shards))


FROZEN_MANIFEST = Path(__file__).resolve().parents[1] / (
    "validation_runs/final_acceptance_v1/fpp_calibration/cohort_manifest.json"
)
PROGRAM = Path(__file__).resolve().parents[1] / "validation_runs/final_acceptance_v1/program.json"


def test_committed_cohort_manifest_rebuilds_from_frozen_sources():
    """Dondurulmuş kohort manifesti repo'daki girdilerden yeniden üretilir."""

    payload, audit = campaign.select_cohorts(
        campaign.ROOT / campaign.LABELLED_CORPUS,
        campaign.ROOT / campaign.PRIOR_INJECTION_HOSTS,
    )
    frozen = json.loads(FROZEN_MANIFEST.read_text(encoding="utf-8"))
    assert frozen["cohort_sha256"] == audit["cohort_sha256"]
    assert frozen["status"] == "frozen"
    assert frozen["selected_count"] == 200
    assert frozen["selection"]["detector_used_for_selection"] is False
    assert payload["status"] == "frozen"


def test_gate_contract_is_satisfiable_and_auditable(tmp_path: Path):
    """program.json'daki FPP kapısı, gerçek rapor biçimiyle kapanabilir olmalı."""

    import scripts.validation.final_acceptance_audit as audit_module

    (tmp_path / "config.toml").write_text("[general]\n", encoding="utf-8")
    rows = _rows(100, 100, fp_fpp=lambda i: 0.70 + 0.002 * i, planet_fpp=lambda i: 0.02 + 0.001 * i)
    args = _args(
        tmp_path,
        _write_shards(tmp_path, rows, shard_count=4),
        cohort_manifest=FROZEN_MANIFEST,
        min_per_label=100,
    )
    assert campaign.aggregate(args) == 0
    report = json.loads(args.output.read_text(encoding="utf-8"))
    assert report["status"] == "measured", report["blocking_reasons"]

    program = json.loads(PROGRAM.read_text(encoding="utf-8"))
    gate = next(gate for gate in program["gates"] if gate["id"] == "fpp_quality_calibration")
    assert gate["status"] == "pending_run"
    checks = gate["acceptance_checks"]
    assert checks, "kapı için önceden ilan edilmiş acceptance check'leri olmalı"

    # Check'lerin kendisi üretilen raporda geçmeli; kapı yalnızca kayıtlı
    # durum "measured" olduğunda kapanır.
    program["gates"] = [dict(gate, status="measured", required_output=str(args.output))]
    tmp_program = tmp_path / "program.json"
    tmp_program.write_text(json.dumps(program), encoding="utf-8")
    result = audit_module.audit(tmp_program)
    assert result["closed_gates"] == 1
    assert [item["id"] for item in result["gates"] if item["closed"]] == ["fpp_quality_calibration"]
    assert all(item["passed"] for item in result["gates"][0]["acceptance_results"])

    # Aynı rapor, kapı henüz "pending_run" kayıtlıyken kapanmaz.
    program["gates"] = [dict(gate, required_output=str(args.output))]
    tmp_program.write_text(json.dumps(program), encoding="utf-8")
    assert audit_module.audit(tmp_program)["closed_gates"] == 0


def test_chance_level_proxy_never_closes_the_gate(tmp_path: Path):
    import scripts.validation.final_acceptance_audit as audit_module

    (tmp_path / "config.toml").write_text("[general]\n", encoding="utf-8")
    rows = _rows(100, 100, fp_fpp=lambda i: 0.5, planet_fpp=lambda i: 0.5)
    args = _args(tmp_path, _write_shards(tmp_path, rows, shard_count=4), cohort_manifest=FROZEN_MANIFEST, min_per_label=100)
    assert campaign.aggregate(args) == 0
    report = json.loads(args.output.read_text(encoding="utf-8"))
    assert report["status"] == "pending_run"
    assert report["cases"]["n_cases"] == 200  # ölçüm var, ama kapıyı kapatmıyor

    program = json.loads(PROGRAM.read_text(encoding="utf-8"))
    gate = next(gate for gate in program["gates"] if gate["id"] == "fpp_quality_calibration")
    program["gates"] = [dict(gate, status="measured", required_output=str(args.output))]
    tmp_program = tmp_path / "program.json"
    tmp_program.write_text(json.dumps(program), encoding="utf-8")
    result = audit_module.audit(tmp_program)
    assert result["closed_gates"] == 0
    failed = [item["path"] for item in result["gates"][0]["acceptance_results"] if not item["passed"]]
    assert "status" in failed
    assert "splits.blind_test.roc_auc" in failed
