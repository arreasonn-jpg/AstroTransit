"""run_reproduction_fmea mutabakat sözleşmesi testleri (sentetik özetler)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.validation.run_reproduction_fmea import (
    compare_summaries,
    main,
)

SOURCE_SHA = "6dff856f848b89b17b14dca33a938ab2bc13ae5830fd25795998ed4dea199a47"


def _source(path_value: str = "/frozen/trials.csv") -> dict:
    return {"path": path_value, "sha256": SOURCE_SHA, "recorded_rows": 960}


def _summary(**overrides) -> dict:
    base = {
        "schema_version": "1.0",
        "campaign": "real_noise_injection_parameter_recovery_v1",
        "status": "measured",
        "source": _source(),
        "cohorts": {
            "strict_period_recovery": {
                "row_count": 500,
                "host_count": 10,
                "parameters": {
                    "period": {
                        "bias": 0.0001, "rmse": 0.01, "p95_absolute_error": 0.02,
                    },
                    "rp_rs": {
                        "bias": 0.001, "rmse": 0.02, "p95_absolute_error": 0.03,
                    },
                },
            },
            "all_pipeline_candidates": {
                "row_count": 700,
                "host_count": 10,
                "parameters": {
                    "period": {
                        "bias": -0.0005, "rmse": 0.015, "p95_absolute_error": 0.03,
                    },
                },
            },
        },
    }
    return {**base, **overrides}


def _payload_with_params(params_per_cohort: dict[str, dict[str, dict]]) -> dict:
    s = _summary()
    for cohort, params in params_per_cohort.items():
        s["cohorts"][cohort]["parameters"] = params
    return s


def test_compare_full_agreement_is_measured():
    base = _summary()
    ind = _summary()
    # kopyayı bağımsız yol ile işaretle (aynı sha)
    ind["source"]["path"] = "/independent/trials.csv"
    verdict = compare_summaries(base, ind)
    assert verdict["pooled_agreement_score"] == 1.0
    assert verdict["only_in_baseline_cohorts"] == []
    rows = verdict["cohorts"]["strict_period_recovery"]["rows"]
    assert all(r["agree"] for r in rows)


def test_compare_partial_disagreement_detected():
    base = _summary()
    ind_params = {
        "period": {"bias": 0.0001, "rmse": 0.01, "p95_absolute_error": 0.02},
        "rp_rs": {"bias": 0.02, "rmse": 0.03, "p95_absolute_error": 0.03},  # rmse sapma %50!
    }
    ind = _payload_with_params({"strict_period_recovery": ind_params})
    ind["source"]["path"] = "/independent/trials.csv"
    verdict = compare_summaries(base, ind)
    cohort = verdict["cohorts"]["strict_period_recovery"]
    assert cohort["agreement_score"] == 0.5
    rp_row = next(r for r in cohort["rows"] if r["parameter"] == "rp_rs")
    assert rp_row["rmse_agree"] is False
    assert rp_row["agree"] is False


def test_compare_missing_parameter_listed():
    base = _summary()
    ind = _summary()
    del ind["cohorts"]["strict_period_recovery"]["parameters"]["rp_rs"]
    verdict = compare_summaries(base, ind)
    cohort = verdict["cohorts"]["strict_period_recovery"]
    # Eksik parametre de mutabakatsız hata modu olarak listelenecek (FMEA).
    assert cohort["only_in_baseline"] == ["rp_rs"]
    assert any(r.get("only_in") == "baseline" for r in cohort["rows"])
    assert cohort["agreement_score"] == 0.5


def test_wrong_summary_rejected(tmp_path: Path):
    bad = _summary(campaign="wrong_v0")
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    code = main(["--baseline", str(path), "--independent", str(path),
                 "--output", str(tmp_path / "out.json")])
    assert code == 2
    assert not (tmp_path / "out.json").exists()


def test_status_fail_when_cohort_sets_differ(tmp_path: Path):
    base = _summary()
    ind = _summary()
    del ind["cohorts"]["all_pipeline_candidates"]
    base_path = tmp_path / "base.json"
    ind_path = tmp_path / "ind.json"
    base_path.write_text(json.dumps(base), encoding="utf-8")
    ind_path.write_text(json.dumps(ind), encoding="utf-8")
    out = tmp_path / "reproduction" / "report.json"
    code = main(["--baseline", str(base_path), "--independent", str(ind_path), "--output", str(out)])
    assert code == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "measured_fail"
    assert "all_pipeline_candidates" in "".join(payload["blocking_reasons"])


def test_measured_report_written(tmp_path: Path):
    base = _summary()
    ind = _summary()
    ind["source"]["path"] = "/independent/trials.csv"
    base_path = tmp_path / "base.json"
    ind_path = tmp_path / "ind.json"
    base_path.write_text(json.dumps(base), encoding="utf-8")
    ind_path.write_text(json.dumps(ind), encoding="utf-8")
    out = tmp_path / "reproduction" / "report.json"
    code = main(["--baseline", str(base_path), "--independent", str(ind_path), "--output", str(out)])
    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "measured"
    assert payload["declared"]["expected_rows"] == 960
    assert payload["result"]["pooled_agreement_score"] == 1.0
