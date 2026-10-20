"""Bağımsız üretim (independent reproduction) + FMEA mutabakat koşucusu.

``independent_reproduction_fmea`` kapısının (program.json)
`required_output` kanıtını üretir:
``validation_runs/final_acceptance_v1/reproduction/report.json``.

Sözleşme: dondurulmuş gerçek gürültü enjeksiyon kanıtı
(`scripts/validation/analyze_real_noise_injection_parameters.py`,
sha kilitli 960 satır) üzerinde, **iki ayrı üretim** karşılaştırılır:
1. `baseline`    : referans ortamda üretilmiş analitik özet (schema v1.0)
2. `independent` : bağımsız ortam/uygulamadan gelen özet (aynı soma yapısı)

Kapı bir FMEA mutabakatı döndürür: her parametre bir hata modudur; bias ve
RMSE'nin bağımsız üretimler arasında ilan edilen bağıl toleranslar içinde
kalması = hata modu etki analizi anlaşılmış demektir. Toleranslar kanıt
öncesi CLI ile dondurulur.

Kullanım:
    python scripts/validation/run_reproduction_fmea.py \\
        --baseline outputs/injection/baseline_summary.json \\
        --independent outputs/injection/independent_summary.json \\
        --output validation_runs/final_acceptance_v1/reproduction/report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

EXPECTED_CAMPAIGN = "real_noise_injection_parameter_recovery_v1"
EXPECTED_ROWS = 960

# Varsayılan toleranslar (varsayılan ilan; CLI ile değiştirilebilir ama kanıt
# yazılmadan once sabitleniyor):
DEFAULT_BIAS_REL_TOLERANCE = 0.02
DEFAULT_RMSE_REL_TOLERANCE = 0.05


def _load_summary(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("campaign") != EXPECTED_CAMPAIGN:
        raise ValueError(f"{path}: campaign alanı {EXPECTED_CAMPAIGN} olmalı")
    if payload.get("status") != "measured":
        raise ValueError(f"{path}: status 'measured' olmalı")
    if payload.get("source", {}).get("recorded_rows") != EXPECTED_ROWS:
        raise ValueError(f"{path}: 960 satır kanıt bekleniyor")
    return payload


def _compare_cohort(
    baseline: dict[str, Any],
    independent: dict[str, Any],
    *,
    bias_rel_tolerance: float,
    rmse_rel_tolerance: float,
) -> dict[str, Any]:
    """Tek kohortun FMEA mutabakat tablosunu üretir."""

    base_params = baseline.get("parameters", {})
    ind_params = independent.get("parameters", {})
    rows: list[dict[str, Any]] = []
    for name in sorted(set(base_params) & set(ind_params)):
        b = base_params[name]
        i = ind_params[name]
        missing = [
            key for key in ("bias", "rmse", "p95_absolute_error")
            if key not in b or key not in i
        ]
        if missing:
            rows.append({"parameter": name, "missing_fields": missing, "agree": False})
            continue
        bias_b, bias_i = float(b["bias"]), float(i["bias"])
        rmse_b, rmse_i = float(b["rmse"]), float(i["rmse"])
        bias_diff = abs(bias_b - bias_i)
        bias_scale = max(abs(bias_b), 1e-12)
        rmse_diff = abs(rmse_b - rmse_i)
        rmse_scale = max(abs(rmse_b), 1e-12)
        bias_ok = bias_diff <= bias_rel_tolerance * max(bias_scale, rmse_scale)
        rmse_ok = rmse_diff <= rmse_rel_tolerance * rmse_scale
        rows.append(
            {
                "parameter": name,
                "baseline_bias": bias_b,
                "independent_bias": bias_i,
                "bias_abs_diff": bias_diff,
                "bias_agree": bias_ok,
                "baseline_rmse": rmse_b,
                "independent_rmse": rmse_i,
                "rmse_abs_diff": rmse_diff,
                "rmse_agree": rmse_ok,
                "agree": bool(bias_ok and rmse_ok),
            }
        )
    # FMEA: bir tarafta eksik olan parametre de mutabakatsız hata modudur.
    for name in sorted(set(base_params) - set(ind_params)):
        rows.append({"parameter": name, "only_in": "baseline", "agree": False})
    for name in sorted(set(ind_params) - set(base_params)):
        rows.append({"parameter": name, "only_in": "independent", "agree": False})
    agreed = [r for r in rows if r.get("agree")]
    return {
        "n_parameters": len(rows),
        "n_agree": len(agreed),
        "agreement_score": (len(agreed) / len(rows)) if rows else None,
        "only_in_baseline": sorted(set(base_params) - set(ind_params)),
        "only_in_independent": sorted(set(ind_params) - set(base_params)),
        "rows": rows,
    }


def compare_summaries(
    baseline: dict[str, Any],
    independent: dict[str, Any],
    *,
    bias_rel_tolerance: float = DEFAULT_BIAS_REL_TOLERANCE,
    rmse_rel_tolerance: float = DEFAULT_RMSE_REL_TOLERANCE,
) -> dict[str, Any]:
    """İki üretim özetini tüm kohortlar üstünden mutabakata döker."""

    base = baseline
    ind = independent
    base_cohorts = base.get("cohorts", {})
    ind_cohorts = ind.get("cohorts", {})
    cohort_names = sorted(set(base_cohorts) & set(ind_cohorts))
    cohort_agreements = {
        name: _compare_cohort(
            base_cohorts[name],
            ind_cohorts[name],
            bias_rel_tolerance=bias_rel_tolerance,
            rmse_rel_tolerance=rmse_rel_tolerance,
        )
        for name in cohort_names
    }
    scores = [
        c["agreement_score"]
        for c in cohort_agreements.values()
        if c["agreement_score"] is not None
    ]
    pooled = min(scores) if scores else None
    return {
        "cohorts": cohort_agreements,
        "only_in_baseline_cohorts": sorted(set(base_cohorts) - set(ind_cohorts)),
        "only_in_independent_cohorts": sorted(set(ind_cohorts) - set(base_cohorts)),
        "pooled_agreement_score": pooled,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.validation.run_reproduction_fmea")
    parser.add_argument("--baseline", required=True, help="referans ortam özeti (analyze_raw_noise... çıktısı)")
    parser.add_argument("--independent", required=True, help="bağımsız ortam özeti")
    parser.add_argument("--bias-rel-tolerance", type=float, default=DEFAULT_BIAS_REL_TOLERANCE)
    parser.add_argument("--rmse-rel-tolerance", type=float, default=DEFAULT_RMSE_REL_TOLERANCE)
    parser.add_argument(
        "--output", default="validation_runs/final_acceptance_v1/reproduction/report.json"
    )
    args = parser.parse_args(argv)

    try:
        baseline = _load_summary(Path(args.baseline))
        independent = _load_summary(Path(args.independent))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    verdict = compare_summaries(
        baseline,
        independent,
        bias_rel_tolerance=args.bias_rel_tolerance,
        rmse_rel_tolerance=args.rmse_rel_tolerance,
    )
    status = (
        "measured"
        if verdict["pooled_agreement_score"] == 1.0
        and not verdict["only_in_baseline_cohorts"]
        and not verdict["only_in_independent_cohorts"]
        else "measured_fail"
    )
    blocking: list[str] = []
    if verdict["pooled_agreement_score"] != 1.0:
        blocking.append(
            f"pooled_agreement_score={verdict['pooled_agreement_score']} (1.0 gerekli)"
        )
    for cohort_name in verdict["only_in_baseline_cohorts"]:
        blocking.append(f"kohort yalnız baseline'da: {cohort_name}")
    for cohort_name in verdict["only_in_independent_cohorts"]:
        blocking.append(f"kohort yalnız independent'ta: {cohort_name}")
    payload = {
        "gate": "independent_reproduction_fmea",
        "status": status,
        "declared": {
            "bias_rel_tolerance": args.bias_rel_tolerance,
            "rmse_rel_tolerance": args.rmse_rel_tolerance,
            "expected_rows": EXPECTED_ROWS,
            "hash_locked_source": True,
        },
        "blocking_reasons": blocking,
        "result": verdict,
        "claim_boundary": (
            "Mutabakat, parametre-recovery FMEA'sının bağımsız üretilebilirliği "
            "hakkındadır; model doğruluğu veya kapsama değildir. Özetlerin "
            "ikisi de aynı sha-kilitli kanıt üstünden 'measured' olmalıdır."
        ),
    }
    from astrotransit.validation.artifacts import write_artifact

    write_artifact(payload, args.output)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if status == "measured" else 1


if __name__ == "__main__":
    raise SystemExit(main())
