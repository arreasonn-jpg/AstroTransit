"""Etiketli kohortlardan FPP proxy kalibrasyon raporu (kabul kapısı artifact'ı).

``validation_runs/final_acceptance_v1/program.json`` içindeki
``fpp_quality_calibration`` kapısının beklediği tek dosya budur. Bu modül,
kampanya satırlarını etiketli kalibrasyon vakalarına çevirir, deterministik
development/validation/blind_test bölünmelerinde ``fpp_benchmark``
metriklerini hesaplar ve kapının kapanabilmesi için gerekli **iç geçerlik
sözleşmesini** raporun kendisine gömer.

Epistemik sınırlar (raporda ``claim_boundary`` olarak da taşınır):

- Proxy kalibre edilmez, yalnızca **puanlanır**: hiçbir FPP değeri
  yeniden ölçeklenmez veya dönüştürülmez.
- Eşik süpürmesi yalnızca ``development`` bölünmesinde koşar; ``validation``
  raporlama, ``blind_test`` tek yönlü son değerlendirmedir.
- ``quiet_star`` bir kalibrasyon etiketi değildir (katalog-negatif kontrol
  gezegen yokluğunu kanıtlamaz); tek yönlü spurious-acceptance metriği olur.
- FPP değeri olmayan hedef ``0.0`` yapılmaz; ``not_evaluated`` olarak sayılır.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping, Optional

from astrotransit.validation.fpp_benchmark import (
    FPPBenchmarkCase,
    evaluate_fpp_benchmark,
    split_fpp_cases,
)
from astrotransit.validation.fpp_telemetry import (
    CALIBRATION_LABELS,
    NON_CALIBRATION_LABELS,
    finite_unit_interval,
    read_row_fpp,
)
from astrotransit.validation.splits import assign_split

FPP_CALIBRATION_SCHEMA_VERSION = "1.0"
FPP_CALIBRATION_CAMPAIGN = "fpp_quality_calibration_v1"
FPP_CALIBRATION_SEED = 20260912
FPP_CALIBRATION_THRESHOLD = 0.5

#: İç geçerlik sözleşmesi — bunlar sağlanmadan kapı **kapanmaz**.
MIN_FPP_CASES_PER_COHORT = 40
MIN_BLIND_TEST_CASES = 10
#: Blind bölünmede istenen ayrım gücü; 0.5 ve altı (şans seviyesi) bloke edilir.
MIN_BLIND_TEST_ROC_AUC = 0.5

#: Eşik süpürmesi yalnızca development üzerinde koşar.
THRESHOLD_SWEEP = tuple(round(0.05 * step, 2) for step in range(2, 18))

_FALSE_POSITIVE = "false_positive"
_PLANET = "planet"


def _ratio(numerator: int, denominator: int) -> Optional[float]:
    return numerator / denominator if denominator else None


def _row_fpp_present(row: Mapping[str, Any]) -> bool:
    """Satırda okunabilir, sonlu bir FPP gözlemi var mı (etiketten bağımsız)."""

    for key in ("target_fpp", "fpp", "false_positive_probability"):
        if key in row and finite_unit_interval(row[key]) is not None:
            return True
    return False


def _cohort_block(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    evaluated = [row for row in rows if bool(row.get("evaluated"))]
    reasons: Counter[str] = Counter()
    for row in rows:
        reasons[read_row_fpp(row)[2]] += 1
    return {
        "labelled_count": len(rows),
        "evaluated_count": len(evaluated),
        "unevaluated_count": len(rows) - len(evaluated),
        "accepted_candidate_count": sum(bool(row.get("accepted_candidate")) for row in rows),
        "fpp_available_count": reasons["ok"],
        "not_evaluated": {key: value for key, value in sorted(reasons.items()) if key != "ok"},
    }


def _quiet_block(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    evaluated = [row for row in rows if bool(row.get("evaluated"))]
    spurious = sum(bool(row.get("accepted_candidate")) for row in evaluated)
    return {
        "role": "reported_only_not_a_calibration_label",
        "labelled_count": len(rows),
        "evaluated_count": len(evaluated),
        "accepted_candidate_count": spurious,
        "spurious_acceptance_rate": _ratio(spurious, len(evaluated)),
        "fpp_observed_count": sum(1 for row in rows if _row_fpp_present(row)),
    }


def _split_metrics(
    cases: list[FPPBenchmarkCase],
    *,
    threshold: float,
    seed: int,
) -> dict[str, dict[str, Any]]:
    partitions = split_fpp_cases(cases, seed=seed)
    return {
        name: evaluate_fpp_benchmark(partition, threshold=threshold).to_dict()
        for name, partition in partitions.items()
    }


def _sweep(cases: list[FPPBenchmarkCase]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for threshold in THRESHOLD_SWEEP:
        report = evaluate_fpp_benchmark(cases, threshold=threshold)
        rows.append(
            {
                "threshold": threshold,
                "brier_score": report.brier_score,
                "false_positive_recall": report.false_positive_recall,
                "planet_precision": report.planet_precision,
            }
        )
    scored = [row for row in rows if row["brier_score"] is not None]
    best = min(scored, key=lambda row: (row["brier_score"], row["threshold"])) if scored else None
    return {
        "split": "development",
        "development_only": True,
        "rows": rows,
        "minimum_brier_threshold": None if best is None else best["threshold"],
    }


def build_fpp_calibration_report(
    rows: Iterable[Mapping[str, Any]],
    *,
    threshold: float = FPP_CALIBRATION_THRESHOLD,
    seed: int = FPP_CALIBRATION_SEED,
    cohorts: Optional[Mapping[str, Any]] = None,
    provenance: Optional[Mapping[str, Any]] = None,
    environment: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Kampanya satırlarından kapı artifact'ının sözlüğünü üretir."""

    materialized = [dict(row) for row in rows]
    if not materialized:
        raise ValueError("FPP kalibrasyon raporu en az bir kampanya satırı gerektirir.")

    fp_rows = [row for row in materialized if str(row.get("label")) == _FALSE_POSITIVE]
    planet_rows = [row for row in materialized if str(row.get("label")) == _PLANET]
    quiet_rows = [row for row in materialized if str(row.get("label")) in NON_CALIBRATION_LABELS]
    unknown_rows = [
        row
        for row in materialized
        if str(row.get("label")) not in {*CALIBRATION_LABELS, *NON_CALIBRATION_LABELS}
    ]

    cases: list[FPPBenchmarkCase] = []
    dropped: Counter[str] = Counter()
    measured_zeros = 0
    for row in (*fp_rows, *planet_rows):
        value, _method, reason = read_row_fpp(row)
        if reason != "ok" or value is None:
            dropped[reason] += 1
            continue
        if value == 0.0:
            # Ölçülmüş tam sıfır mümkündür; uydurulmuş sıfır değildir.
            measured_zeros += 1
        cases.append(
            FPPBenchmarkCase(
                str(row.get("target_id", "")),
                CALIBRATION_LABELS[str(row.get("label"))],
                float(value),
            )
        )

    case_ids = [case.target_id for case in cases]
    duplicates = len(case_ids) - len(set(case_ids))
    labels_by_id: dict[str, set[str]] = {}
    for row in (*fp_rows, *planet_rows):
        labels_by_id.setdefault(str(row.get("target_id", "")), set()).add(str(row.get("label")))
    conflicting = sorted(target for target, labels in labels_by_id.items() if len(labels) > 1)

    false_positive_cases = sum(1 for case in cases if case.is_false_positive)
    planet_cases = len(cases) - false_positive_cases
    splits = _split_metrics(cases, threshold=threshold, seed=seed)
    development_cases = [case for case in cases if assign_split(case.target_id, seed=seed) == "development"]
    blind = splits.get("blind_test", {})

    blockers: list[str] = []
    if not cases:
        blockers.append("no_labelled_fpp_cases")
    if false_positive_cases < MIN_FPP_CASES_PER_COHORT:
        blockers.append(
            f"false_positive_cohort_below_minimum:{false_positive_cases}<{MIN_FPP_CASES_PER_COHORT}"
        )
    if planet_cases < MIN_FPP_CASES_PER_COHORT:
        blockers.append(
            f"planet_cohort_below_minimum:{planet_cases}<{MIN_FPP_CASES_PER_COHORT}"
        )
    if duplicates:
        blockers.append(f"duplicate_target_ids:{duplicates}")
    if conflicting:
        blockers.append(f"conflicting_labels_for_same_target:{len(conflicting)}")
    blind_count = int(blind.get("n_cases") or 0)
    if blind_count < MIN_BLIND_TEST_CASES:
        blockers.append(f"blind_test_below_minimum:{blind_count}<{MIN_BLIND_TEST_CASES}")
    blind_auc = blind.get("roc_auc")
    if blind_auc is None:
        blockers.append("blind_test_roc_auc_unavailable")
    elif float(blind_auc) <= MIN_BLIND_TEST_ROC_AUC:
        blockers.append(
            f"blind_test_roc_auc_at_or_below_chance:{float(blind_auc):.4f}<{MIN_BLIND_TEST_ROC_AUC}"
        )

    return {
        "schema_version": FPP_CALIBRATION_SCHEMA_VERSION,
        "campaign": FPP_CALIBRATION_CAMPAIGN,
        "status": "measured" if not blockers else "pending_run",
        "blocking_reasons": blockers,
        "claim_policy": (
            "A gate closes only when its declared status and immutable evidence are "
            "measured/pass and every predeclared acceptance check passes; pending work is "
            "never a score."
        ),
        "method": {
            "fpp_semantics": "heuristic_risk_proxy_not_bayesian",
            "calibration_transform_applied": False,
            "metric_owner": "astrotransit/validation/fpp_benchmark.py",
            "decision_rule": "fpp >= threshold is a false-positive call",
            "threshold": float(threshold),
            "split_seed": int(seed),
            "split_fractions": [0.6, 0.2, 0.2],
            "adopted_fpp_rule": "max_total_score_then_lowest_sector",
            "threshold_selection_split": "development",
            "blind_test_role": "single_directional_final_report",
        },
        "cohorts": {
            "false_positives": _cohort_block(fp_rows),
            "planets": _cohort_block(planet_rows),
            "quiet_controls": _quiet_block(quiet_rows),
            "frozen_selection": dict(cohorts or {}),
        },
        "cases": {
            "n_cases": len(cases),
            "false_positive_cases": false_positive_cases,
            "planet_cases": planet_cases,
            "measured_exact_zero_count": measured_zeros,
            "not_evaluated": dict(sorted(dropped.items())),
        },
        "splits": splits,
        "threshold_sweep": _sweep(development_cases),
        "data_integrity": {
            # Yapısal garanti: eksik FPP'yi sıfıra dolduran bir kod yolu yok.
            "zero_filled_missing_fpp_count": 0,
            "missing_fpp_rows_kept_as_not_evaluated": int(sum(dropped.values())),
            "duplicate_target_ids": duplicates,
            "conflicting_label_targets": conflicting,
            "unknown_label_rows": len(unknown_rows),
        },
        "environment": dict(environment or {}),
        "provenance": dict(provenance or {}),
        "claim_boundary": (
            "Calibration of a heuristic risk proxy on two frozen, independently labelled "
            "cohorts. This is not a Bayesian false-positive probability, not a population "
            "prevalence estimate, and not proof that any single candidate is or is not a "
            "planet. Targets without a scored candidate are reported as not_evaluated and "
            "are never converted into an FPP of zero."
        ),
    }


__all__ = [
    "FPP_CALIBRATION_CAMPAIGN",
    "FPP_CALIBRATION_SCHEMA_VERSION",
    "FPP_CALIBRATION_SEED",
    "FPP_CALIBRATION_THRESHOLD",
    "MIN_BLIND_TEST_CASES",
    "MIN_BLIND_TEST_ROC_AUC",
    "MIN_FPP_CASES_PER_COHORT",
    "THRESHOLD_SWEEP",
    "build_fpp_calibration_report",
]
