"""Blind domain holdout sözleşmesinin testleri (offline, ağ gerektirmez)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrotransit.validation.blind_holdout import (
    CAMPAIGN,
    DECLARED_CEILING_FALSE_POSITIVE_RATE,
    DECLARED_FLOOR_RECALL,
    FP_RUN_SUBSET,
    GATE_ID,
    HOLDOUT_MANIFEST,
    HOLDOUT_SEED,
    LABELLED_CORPUS,
    MINIMUM_CASES_PER_STRATUM,
    PRIOR_INJECTION_HOSTS,
    REQUIRED_OUTPUT,
    SELECTION_METHOD,
    SPLIT_SEED,
    allocate_quotas,
    build_holdout_report,
    disposition_code,
    holdout_sha256,
    normalize_target_id,
    select_holdout,
    stratum_key,
)
from astrotransit.validation.corpus import CorpusCase
from astrotransit.validation.corpus_evaluation import evaluate_corpus
from astrotransit.validation.splits import assign_split

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / HOLDOUT_MANIFEST


def _cases(count: int = 200) -> list[dict]:
    rows = []
    for index in range(count):
        label = "planet" if index % 2 == 0 else "false_positive"
        code = "CP" if label == "planet" else "FP"
        rows.append(
            {
                "target_id": f"{900000000 + index}",
                "label": label,
                "reference": f"TESS FOP WG disposition '{code}' via snapshot",
                "sectors": [],
                "notes": f"TOI {index}",
            }
        )
    return rows


def _blind_subset(cases: list[dict]) -> list[dict]:
    return [case for case in cases if assign_split(case["target_id"], seed=SPLIT_SEED) == "blind_test"]


# --------------------------------------------------------------- kota mantığı


def test_quotas_are_proportional_with_a_per_stratum_floor() -> None:
    allocation = allocate_quotas({"a": 234, "b": 85, "c": 22}, 72, minimum=8)
    assert sum(allocation.values()) == 72
    assert all(value >= 8 for value in allocation.values())
    assert allocation["a"] > allocation["b"] > allocation["c"]


def test_quotas_never_exceed_the_pool() -> None:
    assert allocate_quotas({"a": 5, "b": 5}, 40, minimum=8) == {"a": 5, "b": 5}


def test_floor_cannot_create_cases_when_total_is_tight() -> None:
    allocation = allocate_quotas({key: 2 for key in "abcdef"}, 6, minimum=8)
    assert sum(allocation.values()) == 6
    assert all(value == 1 for value in allocation.values())


@pytest.mark.parametrize("pool,total", [({}, 10), ({"a": 3}, 0), ({"a": 0}, 5)])
def test_degenerate_pools_return_zero_quotas(pool: dict, total: int) -> None:
    assert all(value == 0 for value in allocate_quotas(pool, total, minimum=4).values())


def test_disposition_code_extraction() -> None:
    assert disposition_code("... disposition 'APC' ...") == "APC"
    assert disposition_code("EB*") == "UNCODED"
    assert stratum_key("planet", "disposition 'KP'") == "planet:KP"


# ---------------------------------------------------------------- seçim kuralı


def test_selection_is_deterministic_and_order_independent() -> None:
    cases = _cases()
    first = select_holdout(cases, per_label=6)
    second = select_holdout(list(reversed(cases)), per_label=6)
    assert first["holdout_sha256"] == second["holdout_sha256"]
    assert [row["target_id"] for row in first["cases"]] == [row["target_id"] for row in second["cases"]]


def test_selection_only_draws_from_the_blind_partition() -> None:
    payload = select_holdout(_cases(), per_label=6)
    assert payload["cases"], "havuz boş bırakılmamalı"
    for row in payload["cases"]:
        assert assign_split(row["target_id"], seed=SPLIT_SEED) == "blind_test"
    assert payload["rejection_counts"].get("not_in_blind_test_split", 0) > 0


def test_excluded_ids_are_removed_and_counted() -> None:
    baseline = select_holdout(_cases(), per_label=6)
    victim = baseline["cases"][0]["target_id"]
    after = select_holdout(_cases(), excluded_ids=[victim], per_label=6)
    assert victim not in {row["target_id"] for row in after["cases"]}
    assert after["rejection_counts"].get("used_by_prior_gate", 0) >= 1


def test_selection_never_uses_detector_output() -> None:
    """Aday başarısı/skoru seçim girdisi değil: saha adlarını değiştirince seçim sabit kalır."""

    cases = _cases()
    clean = select_holdout(cases, per_label=6)
    polluted = select_holdout(
        [{**case, "notes": "scored 0.99, previously confirmed", "sectors": [42]} for case in cases], per_label=6
    )
    assert [row["target_id"] for row in clean["cases"]] == [row["target_id"] for row in polluted["cases"]]
    assert clean["holdout_sha256"] == polluted["holdout_sha256"]
    assert clean["selection"]["detector_used_for_selection"] is False


def test_duplicate_and_unusable_labels_are_rejected() -> None:
    blind = _blind_subset(_cases())
    assert blind, "test havuzu boş bırakılmamalı"
    duplicated = blind + [dict(blind[0])]
    payload = select_holdout(
        duplicated + [{"target_id": "x", "label": "maybe_planet", "reference": "r", "sectors": [], "notes": ""}],
        per_label=4,
    )
    ids = [row["target_id"] for row in payload["cases"]]
    assert len(ids) == len(set(ids))
    assert payload["rejection_counts"]["duplicate_target_id"] >= 1
    assert payload["rejection_counts"]["label_not_holdout_eligible"] >= 1


def test_empty_blind_pool_yields_empty_selection_without_inventing_cases() -> None:
    non_blind = [case for case in _cases() if assign_split(case["target_id"], seed=SPLIT_SEED) != "blind_test"]
    payload = select_holdout(non_blind, per_label=50)
    assert payload["cases"] == []
    assert payload["counts"] == {}


# --------------------------------------------------------------------- rapor


def _rows(cases: list[dict], *, planet_hits: int, fp_hits: int) -> list[dict]:
    rows = []
    planet_index = fp_index = 0
    for case in cases:
        label = case["label"]
        if label == "planet":
            detected = planet_index < planet_hits
            planet_index += 1
        else:
            detected = fp_index < fp_hits
            fp_index += 1
        rows.append(
            {
                "target_id": case["target_id"],
                "label": label,
                "stratum": case.get("stratum", stratum_key(label, case["reference"])),
                "accepted_candidate": detected,
                "successful_sector_count": 1,
                "error": "",
                "in_corpus": True,
            }
        )
    return rows


def test_confusion_matrix_and_intervals() -> None:
    selected = select_holdout(_cases(), per_label=12)["cases"]
    rows = _rows(selected, planet_hits=10, fp_hits=2)
    report = build_holdout_report(
        rows,
        minimum_evaluated=20,
        minimum_per_stratum=2,
        floor_recall=0.3,
        ceiling_false_positive_rate=0.9,
    )
    overall = report["overall"]
    assert (overall["true_positives"], overall["false_positives"]) == (10, 2)
    assert overall["false_negatives"] == 2 and overall["true_negatives"] == 10
    assert overall["recall"] == pytest.approx(round(10 / 12, 6), abs=1e-9)
    assert overall["wilson_recall_95"][0] < overall["recall"] < overall["wilson_recall_95"][1]
    assert report["status"] == "measured"
    assert report["blocking_reasons"] == []


def test_report_matches_the_shared_corpus_evaluator() -> None:
    """Aynı satırlar repo'nun evaluate_corpus sözleşmesiyle de aynı sayılmalı."""

    selected = select_holdout(_cases(), per_label=10)["cases"]
    rows = _rows(selected, planet_hits=7, fp_hits=3)
    report = build_holdout_report(
        rows, minimum_evaluated=10, minimum_per_stratum=1, floor_recall=0.0, ceiling_false_positive_rate=1.0
    )
    cases = [CorpusCase(target_id=row["target_id"], label=row["label"], reference="x") for row in rows]
    verdicts = {row["target_id"]: row["accepted_candidate"] for row in rows}
    evaluation = evaluate_corpus(cases, lambda case: verdicts[case.target_id], split="blind_test", seed=SPLIT_SEED)
    assert evaluation.true_positives == report["overall"]["true_positives"]
    assert evaluation.false_positives == report["overall"]["false_positives"]
    assert evaluation.false_negatives == report["overall"]["false_negatives"]
    assert evaluation.true_negatives == report["overall"]["true_negatives"]


def test_rows_outside_the_blind_partition_block_the_gate() -> None:
    rows = _rows(select_holdout(_cases(), per_label=6)["cases"], planet_hits=5, fp_hits=0)
    outsider = next(
        case["target_id"] for case in _cases() if assign_split(case["target_id"], seed=SPLIT_SEED) != "blind_test"
    )
    rows[0]["target_id"] = outsider  # development/validation bölmesinden bir id
    report = build_holdout_report(
        rows, minimum_evaluated=1, minimum_per_stratum=1, floor_recall=0.0, ceiling_false_positive_rate=1.0
    )
    assert any(reason.startswith("holdout_not_blind") for reason in report["blocking_reasons"])
    assert report["status"] == "pending_run"
    assert report["disjointness"]["non_blind_rows"] == 1


def test_error_rows_are_never_counted_as_passes() -> None:
    selected = select_holdout(_cases(), per_label=6)["cases"]
    rows = _rows(selected, planet_hits=6, fp_hits=0)
    for row in rows:
        row["accepted_candidate"] = None
        row["error"] = "sector_lookup_failed"
    report = build_holdout_report(
        rows, minimum_evaluated=1, minimum_per_stratum=1, floor_recall=0.0, ceiling_false_positive_rate=1.0
    )
    assert report["data"]["n_evaluated"] == 0
    assert report["data"]["errors"] == len(rows)
    assert report["overall"]["recall"] is None
    assert f"error_rows:{len(rows)}" in report["blocking_reasons"]


def test_declared_floors_are_enforced_not_reported_only() -> None:
    selected = select_holdout(_cases(), per_label=8)["cases"]
    low_recall = build_holdout_report(
        _rows(selected, planet_hits=1, fp_hits=0),
        minimum_evaluated=8,
        minimum_per_stratum=1,
        floor_recall=DECLARED_FLOOR_RECALL,
        ceiling_false_positive_rate=1.0,
    )
    assert any(reason.startswith("recall_below_declared_floor") for reason in low_recall["blocking_reasons"])
    leaky = build_holdout_report(
        _rows(selected, planet_hits=8, fp_hits=8),
        minimum_evaluated=8,
        minimum_per_stratum=1,
        floor_recall=0.0,
        ceiling_false_positive_rate=DECLARED_CEILING_FALSE_POSITIVE_RATE,
    )
    assert any(
        reason.startswith("false_positive_rate_above_declared_ceiling") for reason in leaky["blocking_reasons"]
    )


def test_membership_drift_against_the_frozen_manifest_is_blocked() -> None:
    selected = select_holdout(_cases(), per_label=6)
    rows = _rows(selected["cases"], planet_hits=4, fp_hits=0)
    kwargs = dict(minimum_evaluated=1, minimum_per_stratum=1, floor_recall=0.0, ceiling_false_positive_rate=1.0)

    honest = build_holdout_report(rows, manifest=selected, **kwargs)
    assert honest["blocking_reasons"] == []
    assert honest["status"] == "measured"

    # Zor bir katman satırdan çıkarılırsa: satırlar korpusu aşıyor olmalı.
    dropped = dict(selected, cases=selected["cases"][:-1])
    cheating = build_holdout_report(rows, manifest=dropped, **kwargs)
    assert "rows_not_in_frozen_corpus:1" in cheating["blocking_reasons"]
    assert cheating["status"] == "pending_run"

    # Manifest hash'i oynatılırsa kendi kendine tutarsızlık yakalanır.
    forged = dict(selected, holdout_sha256="0" * 64)
    assert "holdout_manifest_self_inconsistent" in build_holdout_report(rows, manifest=forged, **kwargs)["blocking_reasons"]

    # Korpusun bir hedefi hiç değerlendirilmediyse kapı kapalı kalır.
    partial = dict(
        selected,
        cases=list(selected["cases"]) + [{"target_id": "899999999", "label": "planet", "stratum": "planet:CP"}],
    )
    assert "corpus_rows_missing:1" in build_holdout_report(rows, manifest=partial, **kwargs)["blocking_reasons"]


def test_empty_rows_raise_and_helpers_are_total() -> None:
    with pytest.raises(ValueError, match="en az bir değerlendirme satırı"):
        build_holdout_report([])
    assert normalize_target_id(" 12345.01 ") == "12345"
    assert holdout_sha256([]) != holdout_sha256([{"target_id": "1", "label": "planet", "stratum": "planet:CP"}])


# ------------------------------------------------- donmuş korpus sözleşmesi


def test_committed_manifest_matches_rebuild_and_contract() -> None:
    assert MANIFEST_PATH.is_file(), "frozen holdout manifest commit edilmeli"
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    cases = json.loads((ROOT / LABELLED_CORPUS).read_text(encoding="utf-8"))["cases"]
    excluded: set[str] = set()
    for ids in manifest["exclusions"]["sources"].values():
        excluded |= set(ids)
    rebuilt = select_holdout(
        cases,
        excluded_ids=excluded,
        per_label=manifest["selection"]["per_label_quota"],
        minimum_per_stratum=manifest["selection"]["minimum_per_stratum"],
    )
    assert rebuilt["holdout_sha256"] == manifest["holdout_sha256"]
    assert [row["target_id"] for row in rebuilt["cases"]] == [row["target_id"] for row in manifest["cases"]]
    assert manifest["corpus"] == CAMPAIGN
    assert manifest["status"] == "frozen"
    assert manifest["materialization"] == "deterministic_rebuild_from_frozen_sources"
    assert manifest["counts"] == {"false_positive": 72, "planet": 72}
    assert manifest["floors"]["minimum_cases_per_stratum"] == MINIMUM_CASES_PER_STRATUM
    assert min(manifest["stratum_counts"].values()) >= MINIMUM_CASES_PER_STRATUM
    assert sum(manifest["stratum_counts"].values()) == 144
    assert manifest["selection"]["seed"] == HOLDOUT_SEED
    assert manifest["selection"]["split_seed"] == SPLIT_SEED
    assert manifest["selection"]["method"] == SELECTION_METHOD
    assert manifest["selection"]["detector_used_for_selection"] is False
    assert manifest["sources"]["labelled_corpus_sha256"]
    assert "blind partition" in manifest["claim_boundary"]
    assert manifest["exclusions"]["n_excluded_ids"] > 0


def test_manifest_ids_are_disjoint_from_every_prior_gate_source() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    holdout = {case["target_id"] for case in manifest["cases"]}
    assert len(holdout) == len(manifest["cases"])

    def ids(path: Path) -> set[str]:
        assert path.is_file(), f"{path} okunamadi"
        found: set[str] = set()

        def walk(node: object) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in {"target_id", "tic_id"} and not isinstance(value, (dict, list)):
                        found.add(normalize_target_id(value))
                    else:
                        walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(json.loads(path.read_text(encoding="utf-8")))
        return found

    for label, relative in (("fp_run_subset", FP_RUN_SUBSET), ("prior_injection_hosts", PRIOR_INJECTION_HOSTS)):
        source = ids(ROOT / relative)
        assert source, f"{label} boş"
        assert not (holdout & source), f"{label} ile holdout kesişimi: {sorted(holdout & source)[:3]}"
    # Her hedef yalnızca blind bölmede olabilir.
    assert all(assign_split(item, seed=SPLIT_SEED) == "blind_test" for item in holdout)


def test_program_json_declares_the_gate_contract() -> None:
    program = json.loads((ROOT / "validation_runs/final_acceptance_v1/program.json").read_text(encoding="utf-8"))
    gate = next(item for item in program["gates"] if item.get("id") == GATE_ID)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    checks = {item["path"]: item for item in gate["acceptance_checks"]}
    assert gate["status"] == "pending_run"
    assert gate["runner"] == "scripts/validation/run_blind_holdout.py"
    assert checks["corpus.sha256"]["value"] == manifest["holdout_sha256"]
    assert checks["overall.recall"]["value"] == manifest["floors"]["recall"] == DECLARED_FLOOR_RECALL
    assert checks["overall.false_positive_rate"] == {
        "path": "overall.false_positive_rate",
        "operator": "lte",
        "value": manifest["floors"]["false_positive_rate_ceiling"],
    }
    assert checks["data.errors"]["value"] == 0
    assert checks["disjointness.non_blind_rows"]["value"] == 0
    assert checks["method.detector_used_for_selection"]["value"] is False
    assert checks["method.retrained"]["value"] is False
    for stratum in manifest["stratum_counts"]:
        assert checks[f"strata.{stratum}.n_evaluated"]["value"] == MINIMUM_CASES_PER_STRATUM


def test_report_paths_exist_in_the_schema_so_checks_cannot_vacuously_pass() -> None:
    """Kontroller, rapor semasindaki gercek alanlari hedeflemeli (missing => fail)."""

    from scripts.validation.final_acceptance_audit import _MISSING, _lookup

    program = json.loads((ROOT / "validation_runs/final_acceptance_v1/program.json").read_text(encoding="utf-8"))
    gate = next(item for item in program["gates"] if item.get("id") == GATE_ID)
    selected = select_holdout(_cases(), per_label=12)
    rows = _rows(selected["cases"], planet_hits=12, fp_hits=0)
    # Varsilanilan esiklerle kurulur ki rapor method.alanlari program.json ile ayni olsun.
    report = build_holdout_report(rows, manifest=selected)
    missing = [
        check["path"]
        for check in gate["acceptance_checks"]
        if _lookup(report, check["path"]) is _MISSING and not check["path"].startswith("strata.")
    ]
    assert missing == []
    # Varsayilan esikler ornekte etkin: kucuk orneklem kapici kapatir.
    assert _lookup(report, "status") == "pending_run"
    assert any(reason.startswith("evaluated_cases_below_declared_minimum") for reason in report["blocking_reasons"])
    assert _lookup(report, "method.declared_floor_recall") == DECLARED_FLOOR_RECALL
    program_checks = {item["path"]: item for item in gate["acceptance_checks"]}
    assert _lookup(report, "method.declared_floor_recall") == program_checks["overall.recall"]["value"]
    assert (
        _lookup(report, "method.declared_ceiling_false_positive_rate")
        == program_checks["overall.false_positive_rate"]["value"]
    )
    assert _lookup(report, "method.declared_minimum_cases_per_stratum") == MINIMUM_CASES_PER_STRATUM
    assert _lookup(report, "corpus.sha256") == selected["holdout_sha256"]


def test_offline_shard_rows_are_errors_and_the_gate_refuses_to_close(tmp_path: Path) -> None:
    """Korpus var ama ölçüm yoksa: raporda 'measured' iddiası kurulamaz."""

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    small = dict(manifest, cases=manifest["cases"][:4], holdout_sha256=holdout_sha256(manifest["cases"][:4]))
    manifest_path = tmp_path / "holdout_manifest.json"
    manifest_path.write_text(json.dumps(small, indent=2, sort_keys=True), encoding="utf-8")
    shard_path = tmp_path / "shard-00.json"

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/validation/run_blind_holdout.py"),
            "run-shard",
            "--manifest",
            str(manifest_path),
            "--shard-index",
            "0",
            "--shard-count",
            "1",
            "--offline",
            "--output",
            str(shard_path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    report_path = tmp_path / "report.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/validation/run_blind_holdout.py"),
            "aggregate",
            "--manifest",
            str(manifest_path),
            "--rows",
            str(shard_path),
            "--output",
            str(report_path),
            "--minimum-evaluated",
            "1",
            "--minimum-per-stratum",
            "1",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 3, completed.stdout + completed.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "pending_run"
    assert report["data"]["n_evaluated"] == 0
    assert report["data"]["errors"] == 4
    assert any(reason.startswith("error_rows:") for reason in report["blocking_reasons"])
    # Kanonik kapı yolu bu kosumda asla yazilmaz.
    assert not (ROOT / REQUIRED_OUTPUT).exists()


def test_run_refuses_a_missing_or_drifted_manifest(tmp_path: Path) -> None:
    def run(*extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/validation/run_blind_holdout.py"), "run-shard", *extra],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    missing = run("--manifest", str(tmp_path / "nope.json"), "--shard-index", "0", "--offline", "--output", str(tmp_path / "s.json"))
    assert missing.returncode != 0
    assert "frozen holdout manifest missing" in missing.stderr + missing.stdout

    drifted = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    drifted["cases"] = drifted["cases"][:-1]
    path = tmp_path / "drifted.json"
    path.write_text(json.dumps(drifted, indent=2, sort_keys=True), encoding="utf-8")
    second = run("--manifest", str(path), "--shard-index", "0", "--offline", "--output", str(tmp_path / "s.json"))
    assert second.returncode != 0
    assert "drifted" in second.stderr + second.stdout


def test_aggregate_refuses_rows_outside_the_frozen_corpus(tmp_path: Path) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    shard = tmp_path / "shard-00.json"
    shard.write_text(
        json.dumps({"rows": [{"target_id": "777777777", "label": "planet", "stratum": "planet:CP", "accepted_candidate": True}]}, indent=2),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/validation/run_blind_holdout.py"),
            "aggregate",
            "--manifest",
            str(ROOT / HOLDOUT_MANIFEST),
            "--rows",
            str(shard),
            "--output",
            str(tmp_path / "report.json"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "korpusda olmayan" in completed.stderr + completed.stdout
    assert manifest["status"] == "frozen"


def test_check_contract_command_passes(capsys: pytest.CaptureFixture[str]) -> None:
    from scripts.validation.run_blind_holdout import check_contract

    assert check_contract(SimpleNamespace(manifest=str(MANIFEST_PATH))) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "contract_consistent"
    assert payload["n_cases"] == 144
    assert payload["excluded_ids"] == 170
