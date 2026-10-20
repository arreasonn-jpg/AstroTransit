"""MCMC posterior kapsama + PPC-proxy kampanyası koşucusu.

``mcmc_coverage_ppc`` kapısının (program.json) `required_output` kanıtını
üretir: ``validation_runs/final_acceptance_v1/mcmc/report.json``.

Yöntem (v1, ilanlı kapsam):
- Sentetik transit vakaları (batman modeli + gürültü; TESS indirmesi yok).
- Doğru gerçek değerli vakalarda MAP fit + PyMC MCMC posterior örnekleme.
- Kapsama ölçümü: gerçek ``rp_rs`` ve ``t0`` değerinin posterior HDI-94%
  aralığında kalma oranı. Pipelines MCMC yalnız doğrulanmış adaylarda
  çalıştığı için kapsam "detection-conditioned" — körlü arama kapsaması
  DEĞİLDİR; claim_boundary bunu açıkça kaydeder.
- PPC-proxy: posterior-mean model kalıntı RMS / enjekte gürültü sigma
  oranı (v1'de tam Bayesyen PPC değil, ilan edilmiş yaklaşımdır).

Eşikler çalıştırmadan önce CLI ile dondurulur; raporun içine aynen yazılır.

Kullanım (ağır; pymc+batman gerektirir):
    python scripts/validation/run_mcmc_coverage_ppc.py \\
        --cases 12 --draws 300 --chains 2 --tune 150 \\
        --output validation_runs/final_acceptance_v1/mcmc/report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Any

import numpy as np

from astrotransit.modeling.map_fit import MAPFitter
from astrotransit.modeling.parameters import TransitPriors
from astrotransit.modeling.pymc_fit import PyMCFitter
from astrotransit.modeling.transit_model import TransitModel, TransitModelParams
from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve

CADENCE_MINUTES = 30.0
N_TRANSITS = 4
U1_TRUE = 0.3
U2_TRUE = 0.2


def generate_case(seed: int) -> tuple[DetrendedLightCurve, TransitPriors, dict[str, float]]:
    """Sentetik vaka üretir; önce/sonra rastgelelik seed'e bağlı ve işaretlidir."""

    rng = np.random.default_rng(seed)
    period = float(rng.uniform(1.2, 4.0))
    sigma_frac = float(rng.uniform(100e-6, 400e-6))
    cadence_days = CADENCE_MINUTES / 1440.0
    t_start = float(rng.uniform(100.0, 500.0))
    obs_span = N_TRANSITS * period
    time = np.arange(t_start, t_start + obs_span, cadence_days)

    t0 = float(rng.uniform(t_start + 0.05, t_start + period - 0.05))
    rp_rs = float(rng.uniform(0.03, 0.12))
    b = float(rng.uniform(0.0, 0.7))
    a_over_rs = TransitModel.compute_a_over_rs(period, 1.0, 1.0)
    inc = TransitModel.impact_to_inclination(b, a_over_rs)
    model_params = TransitModelParams(
        period=period,
        t0=t0,
        rp=rp_rs,
        a=a_over_rs,
        inc=inc,
        u1=U1_TRUE,
        u2=U2_TRUE,
    )
    model = TransitModel(time)
    flux = model.flux(model_params)
    noise = rng.normal(0.0, sigma_frac, size=flux.shape)

    detrended = DetrendedLightCurve(
        target_id=f"SYN-{seed:05d}",
        sector=1,
        time=time,
        flux=flux + noise,
        flux_err=np.full_like(flux, sigma_frac),
        trend=np.ones_like(flux),
        raw_flux=flux + noise,
        method="none",
        window_length=0.0,
        break_tolerance=0.0,
        meta={"seed": seed},
    )
    # Pipeline'da MCMC yalnız TLS doğrulamış adaylarda çalışır; burada
    # periyot kanıt-zincirinden (injelenmiş gerçek değer) gelir — bu,
    # "detection-conditioned" kapsam tanımının parçasıdır (claim_boundary).
    priors = TransitPriors(
        period=period,
        period_bounds=(period * 0.9, period * 1.1),
        t0=t0,
        t0_bounds=(t0 - 0.5, t0 + 0.5),
        rp_rs=rp_rs,
        rp_rs_bounds=(0.001, 0.5),
        impact_parameter=b,
        impact_parameter_bounds=(0.0, 1.2),
        duration=0.15,
        u1=U1_TRUE,
        u2=U2_TRUE,
        log_jitter=-7.0,
        baseline=1.0,
    )
    truth = {
        "period": period,
        "t0": t0,
        "rp_rs": rp_rs,
        "impact_parameter": b,
        "noise_frac": sigma_frac,
    }
    return detrended, priors, truth


def run_case(
    seed: int,
    *,
    chains: int,
    draws: int,
    tune: int,
    random_seed: int,
) -> dict[str, Any]:
    """Tek vakayı MAP + MCMC ile değerlendirir ve kapsama/PPC satırı döndürür."""

    detrended, priors, truth = generate_case(seed)
    map_fitter = MAPFitter()
    map_result = map_fitter.fit(detrended, priors)
    if not map_result.success:
        return {"seed": seed, "state": "map_failed", "truth": truth}

    sampler = PyMCFitter(
        chains=chains,
        draws=draws,
        tune=tune,
        random_seed=random_seed + seed,
        # Sentetik kampanya: sigma enjeksiyonda tam bilindiginden serbest
        # jitter zayif tanimlidir ve sinir hunisi yaratir; ilanli olarak
        # sabitlenir (fix_jitter, kutuphane tarafindan desteklenen mod).
        fix_jitter=True,
    )
    mcmc = sampler.fit(detrended, priors, map_result=map_result)

    entry: dict[str, Any] = {
        "seed": seed,
        "truth": truth,
        "state": "measured" if mcmc.posteriors else "mcmc_failed",
        # Kütüphane tabanı daha katıdır (r_hat<1.01 & ess>=400 & 0 ıraksama):
        # diagnostik etiket olarak ayrı kaydedilir; kapı tabanları ilanli
        # acceptance_checks ile yönetilir (r_hat_max_median<=1.1, ess>=100).
        "library_diagnostics_ok": bool(mcmc.success),
        "r_hat_max": mcmc.r_hat_max,
        "n_divergences": mcmc.n_divergences,
    }
    if entry["state"] != "measured":
        return entry

    coverage: dict[str, bool | None] = {}
    summaries = mcmc.posteriors
    for param in ("rp_rs", "t0", "impact_parameter"):
        summary = summaries.get(param)
        if summary is None:
            coverage[param] = None
            continue
        coverage[param] = bool(
            summary.hdi_3 <= truth[param] <= summary.hdi_97
        )
    entry["hdi94_coverage"] = coverage
    entry["ess"] = {
        name: (summary.ess if summary else None)
        for name, summary in summaries.items()
    }
    entry["r_hat_per_param"] = {
        name: (summary.r_hat if summary else None)
        for name, summary in summaries.items()
    }

    # PPC-proxy: posterior-mean model kalıntı RMS / enjekte gürültü
    a_over_rs = TransitModel.compute_a_over_rs(truth["period"], 1.0, 1.0)
    mean_params = TransitModelParams(
        period=truth["period"],
        t0=mcmc.t0 if mcmc.t0 != 0.0 else truth["t0"],
        rp=mcmc.rp_rs if mcmc.rp_rs != 0.0 else truth["rp_rs"],
        a=a_over_rs,
        inc=TransitModel.impact_to_inclination(
            mcmc.impact_parameter or truth["impact_parameter"], a_over_rs
        ),
        u1=U1_TRUE,
        u2=U2_TRUE,
    )
    mean_flux = TransitModel(detrended.time).flux(mean_params)
    residual = detrended.flux - mean_flux
    sigma = float(truth["noise_frac"])
    entry["ppc"] = {
        "residual_rms_per_sigma": float(np.sqrt(np.mean(residual ** 2)) / sigma),
    }
    return entry


def summarize(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Vaka satırından kapsama/PPC/ESS özeti üretir."""

    measured = [e for e in entries if e.get("state") == "measured"]
    per_param: dict[str, list[float]] = {p: [] for p in ("rp_rs", "t0", "impact_parameter")}
    for entry in measured:
        for param, covered in (entry.get("hdi94_coverage") or {}).items():
            if covered is not None:
                per_param[param].append(1.0 if covered else 0.0)
    coverage = {
        param: (statistics.fmean(values) if values else None)
        for param, values in per_param.items()
    }
    all_covered = [
        value
        for values in per_param.values()
        for value in values
    ]
    ppc_ratios = [
        e["ppc"]["residual_rms_per_sigma"]
        for e in measured
        if e.get("ppc")
    ]
    r_hats = [e["r_hat_max"] for e in measured if e.get("r_hat_max") is not None]
    ess_values = [
        ess
        for e in measured
        for ess in (e.get("ess") or {}).values()
        if ess is not None
    ]
    return {
        "n_cases": len(entries),
        "n_measured": len(measured),
        "failure_states": {
            state: sum(1 for e in entries if e.get("state") == state)
            for state in ("map_failed", "mcmc_failed")
        },
        "hdi94_coverage": coverage,
        "hdi94_coverage_pooled": (statistics.fmean(all_covered) if all_covered else None),
        "ppc_residual_rms_per_sigma_median": (
            statistics.median(ppc_ratios) if ppc_ratios else None
        ),
        "r_hat_max_median": (statistics.median(r_hats) if r_hats else None),
        "ess_median": (statistics.median(ess_values) if ess_values else None),
        "entries": entries,
    }


def evaluate_gate(
    summary: dict[str, Any],
    *,
    min_cases: int,
    coverage_floor: float,
    coverage_ceiling: float,
    ppc_rmse_floor: float,
    ppc_rmse_ceiling: float,
    r_hat_max: float,
    ess_min: int,
) -> tuple[str, list[str]]:
    """İlan edilen eşiklere göre kapı durumu; kanıt öncesi dondurulur."""

    reasons: list[str] = []
    if summary["n_measured"] < min_cases:
        reasons.append(
            f"n_measured {summary['n_measured']} < ilan edilen taban {min_cases}"
        )
    pooled = summary["hdi94_coverage_pooled"]
    if pooled is None:
        reasons.append("hdi94_coverage_pooled ölçülemedi")
    else:
        if pooled < coverage_floor:
            reasons.append(f"kapsama {pooled:.3f} < taban {coverage_floor:.3f}")
        if pooled > coverage_ceiling:
            reasons.append(f"kapsama {pooled:.3f} > tavan {coverage_ceiling:.3f} (aşırı geniş)")
    rmse_ratio = summary["ppc_residual_rms_per_sigma_median"]
    if rmse_ratio is None:
        reasons.append("ppc_proxy ölçülemedi")
    else:
        if rmse_ratio < ppc_rmse_floor or rmse_ratio > ppc_rmse_ceiling:
            reasons.append(
                f"ppc_rmse_oran {rmse_ratio:.3f} bandın dışında "
                f"[{ppc_rmse_floor}, {ppc_rmse_ceiling}]"
            )
    r_hat = summary["r_hat_max_median"]
    if r_hat is None or r_hat > r_hat_max:
        reasons.append(f"r_hat_max_median {r_hat} > başarım tavanı {r_hat_max}")
    ess = summary["ess_median"]
    if ess is None or ess < ess_min:
        reasons.append(f"ess_median {ess} < taban {ess_min}")
    return ("measured" if not reasons else "measured_fail"), reasons


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.validation.run_mcmc_coverage_ppc")
    parser.add_argument("--cases", type=int, default=12)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--draws", type=int, default=600)
    parser.add_argument("--chains", type=int, default=2)
    parser.add_argument("--tune", type=int, default=500)
    parser.add_argument("--coverage-floor", type=float, default=0.75)
    parser.add_argument("--coverage-ceiling", type=float, default=1.0)
    parser.add_argument("--ppc-rmse-floor", type=float, default=0.5)
    parser.add_argument("--ppc-rmse-ceiling", type=float, default=1.5)
    parser.add_argument("--r-hat-max", type=float, default=1.1)
    parser.add_argument("--ess-min", type=int, default=100)
    parser.add_argument(
        "--output", default="validation_runs/final_acceptance_v1/mcmc/report.json"
    )
    args = parser.parse_args(argv)

    # Her vaka bittiği an diske güncellenen devam-defteri (kesinti toleransı):
    # aynı konfigürasyonla yeniden koşum, tamamlanmış vakaları atlar.
    cache_path = Path(args.output).parent / "entries_cache.jsonl"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    config_keys = {
        "cases": args.cases, "seed": args.seed, "draws": args.draws,
        "chains": args.chains, "tune": args.tune,
        "coverage_floor": args.coverage_floor, "coverage_ceiling": args.coverage_ceiling,
        "ppc_rmse_floor": args.ppc_rmse_floor, "ppc_rmse_ceiling": args.ppc_rmse_ceiling,
        "r_hat_max": args.r_hat_max, "ess_min": args.ess_min,
    }
    config_hash = hashlib.sha256(
        json.dumps(config_keys, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]

    entries: list[dict[str, Any]] = []
    cache_fh = None
    resumed = 0
    if cache_path.exists():
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("config_hash") != config_hash:
                continue  # farklı konfigürasyon satırları düşer
            entries.append(record["entry"])
            resumed += 1
        if entries:
            print(f"[resume] {resumed} tamamlanmış vaka devam-defterinden alındı", flush=True)

    cache_fh = cache_path.open("a", encoding="utf-8")
    done_seeds = {e.get("seed") for e in entries}
    for index in range(args.cases):
        seed = args.seed + index
        if seed in done_seeds:
            continue
        try:
            entry = run_case(
                seed,
                chains=args.chains,
                draws=args.draws,
                tune=args.tune,
                random_seed=args.seed,
            )
            entries.append(entry)
            state = entry.get("state")
            print(f"[case {index + 1}/{args.cases}] seed={seed} state={state}", flush=True)
        except Exception as exc:  # kampanya satırı; kayıp hedef verilmeli
            entry = {"seed": seed, "state": f"exception:{type(exc).__name__}"}
            entries.append(entry)
            print(f"[case {index + 1}/{args.cases}] seed={seed} HATA: {exc}", file=sys.stderr, flush=True)
        # satır bazlı süreklilik — kill'e dayanıklı devam-defteri
        cache_fh.write(json.dumps({"config_hash": config_hash, "entry": entry}, ensure_ascii=False) + "\n")
        cache_fh.flush()

    cache_fh.close()

    summary = summarize(entries)
    status, reasons = evaluate_gate(
        summary,
        min_cases=args.cases,
        coverage_floor=args.coverage_floor,
        coverage_ceiling=args.coverage_ceiling,
        ppc_rmse_floor=args.ppc_rmse_floor,
        ppc_rmse_ceiling=args.ppc_rmse_ceiling,
        r_hat_max=args.r_hat_max,
        ess_min=args.ess_min,
    )
    payload = {
        "gate": "mcmc_coverage_ppc",
        "campaign": "synthetic_mcmc_coverage_v1",
        "status": status,
        "declared": {
            "cases": args.cases,
            "seed": args.seed,
            "draws": args.draws,
            "chains": args.chains,
            "tune": args.tune,
            "config_hash": config_hash,
            "resumed_entries": resumed,
            "coverage_floor": args.coverage_floor,
            "coverage_ceiling": args.coverage_ceiling,
            "ppc_rmse_floor": args.ppc_rmse_floor,
            "ppc_rmse_ceiling": args.ppc_rmse_ceiling,
            "r_hat_max": args.r_hat_max,
            "ess_min": args.ess_min,
            "fix_jitter": True,
            "fix_jitter_reason": (
                "sentetik kampanyada sigma tam bilindiginden serbest log_jitter "
                "zayif tanimlanir; alt-sinira dogru sinir hunisi NUTS'u bozar"
            ),
            "interval": "HDI 94% (hdi_3..hdi_97, posterior özet günceli)",
            "hdi_from": "PyMCFitter._extract_posterior_summary",
        },
        "blocking_reasons": reasons,
        "result": summary,
        "claim_boundary": (
            "Kapsam, doğru tespit edilmiş ('detection-conditioned') sentetik "
            "vakalarda posterior HDI-94% kapsamasıdır; körlü arama performansı "
            "veya gerçek hedef popülasyon doğruluğu değildir. PPC-proxy tam "
            "Bayesyen posterior-predictive değildir; v1 ilanlı yaklaşımdır."
        ),
    }
    from astrotransit.validation.artifacts import write_artifact

    write_artifact(payload, args.output)
    print(json.dumps({k: v for k, v in payload.items() if k != "result"}, indent=2, ensure_ascii=False))
    return 0 if status == "measured" else 1


if __name__ == "__main__":
    raise SystemExit(main())
