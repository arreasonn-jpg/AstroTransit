#!/usr/bin/env python3
"""Build, run and report the adversarial false-positive controls gate.

Offline by design: the corpus is synthetic, so no MAST access is required and
the whole gate is reproducible on any machine (and in CI).

Subcommands
-----------
``build-corpus``
    Write the frozen scenario grid manifest (deterministic).
``check``
    Prove the committed corpus manifest and the ``program.json`` thresholds still
    agree with the rebuilt grid, without running the pipeline (CI contract step).
``run``
    Execute the whole grid in one process and write the gate report plus an
    optional row dump.
``run-shard`` / ``aggregate``
    The same measurement split over N processes (CI parallelism): each shard
    writes rows, ``aggregate`` rebuilds the report from the shard files and
    refuses to call the gate closed when a grid scenario is missing.

The gate contract is pre-declared in ``validation_runs/final_acceptance_v1/
program.json``; this script never edits that file. Freezing the gate status is
a separate, explicit commit of the produced evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from astrotransit.validation.adversarial_fp import (  # noqa: E402
    ADVERSARIAL_FAMILIES,
    ADVERSARIAL_FPP_REJECT_THRESHOLD,
    BASELINE_DAYS,
    N_POINTS,
    NOISE_PPM,
    AdversarialScenario,
    build_adversarial_report,
    classify_outcome,
    grid_sha256,
    synthetic_lightcurve,
)

CAMPAIGN = "adversarial_false_positives_v1"
GATE_ID = "adversarial_false_positives"
CORPUS_MANIFEST = str(ROOT / "validation_runs/final_acceptance_v1/adversarial_fp/corpus_manifest.json")
REQUIRED_OUTPUT = str(ROOT / "validation_runs/final_acceptance_v1/adversarial_fp/report.json")
PROGRAM = str(ROOT / "validation_runs/final_acceptance_v1/program.json")
PER_FAMILY = 8
SEED_BASE = 20260917

#: Aile başına dondurulmuş parametrik çeşitlilik (RNG'ye değil tabloya bağlı).
_FAMILY_TEMPLATES: dict[str, dict[str, Any]] = {
    "eclipsing_binary_v": {
        "periods": (1.2, 2.1, 3.4, 5.0, 7.3, 9.1, 0.8, 4.4),
        "depths": (0.02, 0.035, 0.012, 0.05, 0.025, 0.018, 0.045, 0.03),
        "duration_days": (0.14, 0.1, 0.16, 0.12, 0.13, 0.15, 0.11, 0.12),
        "steepness": 1.0,
        "dilution": 1.0,
    },
    "grazing_eclipsing_binary": {
        "periods": (0.9, 1.7, 2.9, 3.8, 5.5, 6.6, 8.4, 11.2),
        "depths": (0.006, 0.011, 0.008, 0.014, 0.007, 0.012, 0.009, 0.013),
        "duration_days": (0.05, 0.045, 0.06, 0.055, 0.05, 0.048, 0.052, 0.06),
        "steepness": 0.85,
        "dilution": 1.0,
    },
    "blended_diluted_eb": {
        "periods": (1.0, 2.4, 3.1, 4.6, 6.0, 7.7, 9.9, 11.6),
        "depths": (0.05, 0.04, 0.06, 0.045, 0.055, 0.05, 0.04, 0.06),
        "duration_days": (0.06, 0.07, 0.05, 0.08, 0.06, 0.055, 0.07, 0.065),
        "steepness": 0.95,
        # Derin EB, seyreltme ile gezegen ölçeğine indirgenir (en zor aile).
        "dilution": (0.02, 0.025, 0.015, 0.03, 0.022, 0.018, 0.028, 0.02),
    },
    "eb_with_secondary_eclipse": {
        "periods": (1.4, 2.6, 3.9, 5.2, 6.8, 8.1, 10.4, 11.9),
        "depths": (0.02, 0.03, 0.015, 0.04, 0.025, 0.018, 0.035, 0.022),
        "duration_days": (0.12, 0.1, 0.13, 0.11, 0.12, 0.14, 0.1, 0.12),
        "steepness": 1.0,
        "dilution": 1.0,
        "secondary_fraction": (0.5, 0.35, 0.6, 0.25, 0.45, 0.55, 0.3, 0.4),
    },
    "odd_even_alternating_eb": {
        "periods": (1.1, 2.3, 3.6, 4.9, 6.4, 7.9, 9.6, 11.4),
        "depths": (0.02, 0.03, 0.016, 0.04, 0.024, 0.02, 0.03, 0.018),
        "duration_days": (0.11, 0.12, 0.1, 0.13, 0.115, 0.105, 0.125, 0.11),
        "steepness": 1.0,
        "dilution": 1.0,
        "alternate_ratio": (0.4, 0.55, 0.3, 0.65, 0.5, 0.45, 0.35, 0.6),
    },
    "spot_modulated_dip": {
        "periods": (1.3, 2.7, 3.2, 4.1, 5.9, 6.2, 8.8, 10.6),
        "depths": (0.012, 0.018, 0.01, 0.025, 0.014, 0.02, 0.011, 0.016),
        "duration_days": (0.04, 0.05, 0.045, 0.06, 0.042, 0.055, 0.048, 0.04),
        "steepness": 0.7,
        "dilution": 1.0,
        "variability_amplitude": (0.003, 0.005, 0.002, 0.006, 0.0035, 0.0045, 0.0025, 0.004),
        "variability_period": (12.0, 9.5, 15.0, 8.0, 11.0, 13.5, 10.0, 14.0),
    },
    "planetary_control": {
        "periods": (1.05, 1.9, 2.8, 3.7, 4.9, 6.1, 7.8, 9.4),
        "depths": (0.004, 0.0025, 0.006, 0.003, 0.005, 0.002, 0.0045, 0.0035),
        "duration_days": (0.13, 0.12, 0.14, 0.11, 0.125, 0.135, 0.12, 0.13),
        "steepness": 0.12,  # kutuya yakın: gerçek gezegen transiti
        "dilution": 1.0,
    },
}


def _template_value(template: dict[str, Any], key: str, index: int, default: Any = 0.0) -> Any:
    value = template.get(key, default)
    if isinstance(value, tuple):
        return value[index % len(value)]
    return value


def build_grid(*, per_family: int = PER_FAMILY) -> list[AdversarialScenario]:
    """Deterministik senaryo ızgarası (aile başına ``per_family`` senaryo)."""

    scenarios: list[AdversarialScenario] = []
    for family in sorted(ADVERSARIAL_FAMILIES):
        template = _FAMILY_TEMPLATES[family]
        for index in range(per_family):
            period = float(template["periods"][index % len(template["periods"])])
            duration = float(template["duration_days"][index % len(template["duration_days"])])
            scenario = AdversarialScenario(
                family=family,
                index=index,
                seed=SEED_BASE + 1000 * len(family) + index,
                period_days=period,
                depth=float(template["depths"][index % len(template["depths"])]),
                duration_days=min(duration, 0.45 * period),
                t0_days=0.35 * period,
                steepness=float(_template_value(template, "steepness", index, 1.0)),
                dilution=float(_template_value(template, "dilution", index, 1.0)),
                secondary_fraction=float(_template_value(template, "secondary_fraction", index, 0.0)),
                alternate_ratio=float(_template_value(template, "alternate_ratio", index, 1.0)),
                variability_amplitude=float(_template_value(template, "variability_amplitude", index, 0.0)),
                variability_period_days=float(_template_value(template, "variability_period", index, 0.0)),
                noise_ppm=NOISE_PPM,
            )
            scenario.validate()
            scenarios.append(scenario)
    return scenarios


def canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def corpus_payload(scenarios: list[AdversarialScenario]) -> dict[str, Any]:
    from collections import Counter

    counts = Counter(scenario.family for scenario in scenarios)
    return {
        "schema_version": "1.0",
        "corpus": CAMPAIGN,
        "status": "frozen",
        "materialization": "deterministic_rebuild_from_frozen_grid",
        "n_scenarios": len(scenarios),
        "per_family": PER_FAMILY,
        "counts": {family: counts[family] for family in sorted(counts)},
        "design": {
            "baseline_days": BASELINE_DAYS,
            "cadence_seconds": 600.0,
            "n_points": N_POINTS,
            "noise_ppm": NOISE_PPM,
            "shape_model": "analytic trapezoid/V; no limb darkening; uniform cadence (no gaps)",
            "families": {
                family: {"targets_test": spec["targets_test"], "expected": spec["expected"]}
                for family, spec in sorted(ADVERSARIAL_FAMILIES.items())
            },
        },
        "seed_base": SEED_BASE,
        "grid_sha256": grid_sha256(scenarios),
        "claim_boundary": (
            "Synthetic morphologies only. This corpus qualifies the pipeline's response to the declared "
            "shapes; it is not a survey false-positive rate and says nothing about real TESS systematics "
            "that are not represented here."
        ),
        "cases": [scenario.to_dict() for scenario in scenarios],
    }


def build_corpus(args: argparse.Namespace) -> int:
    scenarios = build_grid(per_family=args.per_family)
    payload = corpus_payload(scenarios)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(payload))
    print(
        json.dumps(
            {
                "n_scenarios": payload["n_scenarios"],
                "grid_sha256": payload["grid_sha256"],
                "counts": payload["counts"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _verify_frozen_grid(scenarios: list[AdversarialScenario], manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.is_file():
        raise ValueError(f"frozen corpus manifest missing: {manifest_path}; run build-corpus first")
    frozen = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = grid_sha256(scenarios)
    if frozen.get("grid_sha256") != digest:
        raise ValueError(
            f"grid drifted from the frozen corpus: {digest[:12]} != {str(frozen.get('grid_sha256'))[:12]}"
        )
    if frozen.get("n_scenarios") != len(scenarios):
        raise ValueError(f"scenario count drifted: {len(scenarios)} != {frozen.get('n_scenarios')}")
    return frozen


def check_contract(args: argparse.Namespace) -> int:
    """Korpus + program.json sozlesmesinin hala anlasiktigini kosmadan kanitlar."""

    scenarios = build_grid()
    frozen = _verify_frozen_grid(scenarios, args.corpus_manifest)
    if frozen.get("status") != "frozen":
        raise ValueError(f"corpus manifest is not frozen: {frozen.get('status')!r}")
    if frozen.get("materialization") != "deterministic_rebuild_from_frozen_grid":
        raise ValueError("corpus manifest materialization changed")
    if frozen.get("cases") != [scenario.to_dict() for scenario in scenarios]:
        raise ValueError("corpus manifest case list differs from the rebuilt grid")
    if min(frozen["counts"].values()) < args.minimum_per_family:
        raise ValueError(f"a family is undersampled in the frozen corpus: {frozen['counts']}")
    if frozen["counts"].get("planetary_control", 0) < args.minimum_per_family:
        raise ValueError("the positive control family must be present in the frozen corpus")

    program = json.loads(Path(PROGRAM).read_text(encoding="utf-8"))
    gate = next((item for item in program["gates"] if item.get("id") == GATE_ID), None)
    if gate is None:
        raise ValueError(f"gate {GATE_ID} missing from program.json")
    checks = {str(item.get("path")): item for item in gate.get("acceptance_checks", [])}
    declared = checks.get("corpus.grid_sha256")
    if declared is None:
        raise ValueError("program.json does not pin corpus.grid_sha256")
    if declared.get("value") != frozen.get("grid_sha256"):
        raise ValueError("program.json pins a different grid than the committed corpus manifest")
    floors = {
        "overall.adversarial_rejection_rate": 0.8,
        "overall.control_acceptance_rate": 0.5,
        "overall.total_errors": 0,
    }
    for path, value in floors.items():
        entry = checks.get(path)
        if entry is None:
            raise ValueError(f"program.json is missing the declared check {path}")
        if entry.get("operator") not in {"gte", "equals"} or entry.get("value") != value:
            raise ValueError(f"declared check {path} was edited: {entry}")
    for family in ADVERSARIAL_FAMILIES:
        if ADVERSARIAL_FAMILIES[family]["expected"] != "false_positive":
            continue
        entry = checks.get(f"families.{family}.rejection_rate")
        if entry is None or entry.get("operator") != "gte" or float(entry.get("value", 0)) < 0.5:
            raise ValueError(f"family floor missing or weakened for {family}")
    print(
        json.dumps(
            {
                "grid_sha256": frozen["grid_sha256"],
                "n_scenarios": frozen["n_scenarios"],
                "counts": frozen["counts"],
                "declared_checks": len(gate.get("acceptance_checks", [])),
                "status": "contract_consistent",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _evaluate_scenario(
    scenario: AdversarialScenario,
    cascade: Any,
    quality: Any,
    modelling: Any,
    *,
    period_tolerance: float,
    reject_threshold: float,
) -> dict[str, Any]:
    """Tek senaryo: üret → tespit → (MAP fit) → kalite/anomali → sınıf."""

    import numpy as np

    from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve

    row: dict[str, Any] = {
        "scenario_id": scenario.scenario_id,
        "family": scenario.family,
        "seed": scenario.seed,
        "expected": scenario.expected,
        "injected_period_days": round(scenario.period_days, 6),
        "injected_depth_ppm": round(scenario.depth * scenario.dilution * 1e6, 3),
    }
    try:
        time, flux, flux_err = synthetic_lightcurve(scenario)
        detrended = DetrendedLightCurve(
            target_id=scenario.scenario_id,
            sector=1,
            time=time,
            flux=flux,
            flux_err=flux_err,
            trend=np.ones_like(flux),
            raw_flux=flux.copy(),
            method="synthetic_adversarial_fp_v1",
            window_length=0.5,
            break_tolerance=0.5,
        )
        candidate = cascade.detect(detrended)
        quality_result = None
        row["fit_status"] = "skipped"
        if candidate is not None and candidate.has_candidate and candidate.confirmed:
            # Gercek pipeline sirasi: MAP fit -> kalite/vetting/anomali. Fit olmadan
            # anomali kademeleri kor olur ve kapic eksik olculurdu
            # (astrotransit/pipelines/tess_pipeline.py:564 ile ayni baglanti).
            fit_result = None
            if modelling is not None:
                try:
                    fit_result = modelling.fit(detrended, candidate)
                    row["fit_status"] = "map"
                except Exception as fit_error:  # noqa: BLE001
                    row["fit_status"] = f"failed:{type(fit_error).__name__}"
            quality_result = quality.evaluate(detrended, candidate, fit_result)
            row["quality_class"] = str(getattr(getattr(quality_result, "score", None), "candidate_class", "") or "")
        row.update(classify_outcome(candidate, quality_result, reject_threshold=reject_threshold))
        detected_period = float(getattr(candidate, "period", 0.0) or 0.0) if candidate is not None else 0.0
        row["detected_period_days"] = round(detected_period, 6) if detected_period > 0 else None
        row["period_within_tolerance"] = bool(
            detected_period > 0
            and abs(detected_period - scenario.period_days) / scenario.period_days <= period_tolerance
        )
    except Exception as exc:  # noqa: BLE001 - a failing scenario must not become a pass
        row["outcome"] = "error"
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def _pipeline_pair(args: argparse.Namespace) -> tuple[Any, Any, Any]:
    from astrotransit.detection.cascade import CascadeDetector
    from astrotransit.modeling.fitter import ModelingOrchestrator
    from astrotransit.quality.pipeline import QualityEvaluationPipeline
    from astrotransit.settings import load_settings

    settings = load_settings(args.config) if args.config else None
    cascade = CascadeDetector(settings=settings, stellar_radius=args.stellar_radius, stellar_mass=args.stellar_mass)
    quality = QualityEvaluationPipeline(settings=settings)
    modelling = ModelingOrchestrator(settings=settings) if args.with_fit else None
    return cascade, quality, modelling


def _write_report(
    args: argparse.Namespace,
    *,
    rows: list[dict[str, Any]],
    scenarios: list[AdversarialScenario],
    frozen_manifest: dict[str, Any],
    missing: list[str],
    sources: list[str],
    rows_dump_sha256: str | None = None,
) -> int:
    from astrotransit.validation.provenance import build_manifest

    provenance = build_manifest(
        input_path=args.corpus_manifest,
        config={
            "per_family": args.per_family,
            "reject_threshold": args.reject_threshold,
            "with_fit": args.with_fit,
            "config": None if args.config is None else str(args.config),
        },
        seed=SEED_BASE,
        root=ROOT,
    )
    provenance["corpus_manifest_sha256"] = hashlib.sha256(Path(args.corpus_manifest).read_bytes()).hexdigest()
    if sources:
        provenance["shard_files"] = [Path(item).name for item in sources]

    report = build_adversarial_report(
        rows,
        scenarios=scenarios,
        reject_threshold=args.reject_threshold,
        minimum_per_family=args.minimum_per_family,
        minimum_control_acceptance=args.minimum_control_acceptance,
        minimum_rejection_rate=args.minimum_rejection_rate,
        minimum_per_family_rejection_rate=args.minimum_per_family_rejection_rate,
        provenance=provenance,
        method_notes={
            "modelling_stage": "MAP fit before vetting/anomaly"
            if args.with_fit
            else "no fit: anomaly stages blind (weaker than the real pipeline)",
            "anomaly_rejection_definition": 'any anomaly report with anomaly_flag == "REJECT"',
            "wiring": "matches astrotransit/pipelines/tess_pipeline.py (evaluate(detrended, candidate, fit_result))",
        },
        environment={
            "python": sys.version,
            "platform": platform.platform(),
            "github_sha": os.environ.get("GITHUB_SHA"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    report["corpus"]["manifest_status"] = frozen_manifest.get("status")
    report["corpus"]["n_missing_rows"] = len(missing)
    report["corpus"]["missing_scenario_ids"] = missing[:20]
    if missing:
        report["blocking_reasons"].append(f"grid_rows_missing:{len(missing)}")
        report["status"] = "pending_run"
    # rows_sha256: satir listesinin canonical JSON'u; rows_dump_sha256: --rows-out
    # ile yazilan satir-ayrik dosyanin hash'i (ikisi farkli serileme, ikisi de kayitli).
    report["rows_sha256"] = hashlib.sha256(canonical_json(rows)).hexdigest()
    if rows_dump_sha256:
        report["rows_dump_sha256"] = rows_dump_sha256

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(report))
    print(
        json.dumps(
            {
                "status": report["status"],
                "blocking_reasons": report["blocking_reasons"],
                "overall": report["overall"],
                "grid_sha256": report["corpus"]["grid_sha256"],
                "families": {
                    family: {
                        "n": block["n_evaluated"],
                        block["rate_statistic"]: block["rejection_rate"]
                        if block["rejection_rate"] is not None
                        else block["control_acceptance_rate"],
                        "stages": block["rejected_by_stage"],
                    }
                    for family, block in report["families"].items()
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "measured" else 3


def run_shard(args: argparse.Namespace) -> int:
    """Izgaranin bir dilimini kosup satirlari dosyaya yazar (CI paralelligi)."""

    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        raise ValueError("invalid shard index/count")
    scenarios = build_grid(per_family=args.per_family)
    _verify_frozen_grid(scenarios, args.corpus_manifest)
    selected = [item for index, item in enumerate(scenarios) if index % args.shard_count == args.shard_index]
    cascade, quality, modelling = _pipeline_pair(args)

    rows = [
        _evaluate_scenario(
            scenario,
            cascade,
            quality,
            modelling,
            period_tolerance=args.period_tolerance,
            reject_threshold=args.reject_threshold,
        )
        for scenario in selected
    ]
    payload = {
        "schema_version": "1.0",
        "campaign": CAMPAIGN,
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "per_family": args.per_family,
        "case_count": len(rows),
        "grid_sha256": grid_sha256(scenarios),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(payload))
    print(f"Wrote shard {args.shard_index}: {len(rows)} scenarios -> {args.output}")
    return 0


def _collect_rows(shard_paths: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    sources: list[str] = []
    seen: set[str] = set()
    for path in shard_paths:
        sources.append(str(path))
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload["rows"]:
            if row["scenario_id"] in seen:
                continue
            seen.add(row["scenario_id"])
            rows.append(row)
    return rows, sources


def _shard_paths(value: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for item in value:
        if item.is_dir():
            paths.extend(sorted(item.glob("shard-*.json")) or sorted(item.glob("*.json")))
        else:
            paths.append(item)
    return paths


def aggregate(args: argparse.Namespace) -> int:
    scenarios = build_grid(per_family=args.per_family)
    frozen_manifest = _verify_frozen_grid(scenarios, args.corpus_manifest)
    paths = _shard_paths(args.shard)
    if not paths:
        raise ValueError("aggregate: shard dosyasi bulunamadi (--shard)")
    rows, sources = _collect_rows(paths)
    if not rows:
        raise ValueError("aggregate: shard satiri bulunamadi (--shard)")
    expected_ids = {scenario.scenario_id for scenario in scenarios}
    missing = sorted(expected_ids - {row["scenario_id"] for row in rows})
    return _write_report(
        args,
        rows=rows,
        scenarios=scenarios,
        frozen_manifest=frozen_manifest,
        missing=missing,
        sources=sources,
    )


def run(args: argparse.Namespace) -> int:
    """Tek proses: tum izgarayi kos, dogrula, raporu yaz (yerel kullanim)."""

    scenarios = build_grid(per_family=args.per_family)
    frozen_manifest = _verify_frozen_grid(scenarios, args.corpus_manifest)
    cascade, quality, modelling = _pipeline_pair(args)
    rows: list[dict[str, Any]] = []
    for position, scenario in enumerate(scenarios, start=1):
        rows.append(
            _evaluate_scenario(
                scenario,
                cascade,
                quality,
                modelling,
                period_tolerance=args.period_tolerance,
                reject_threshold=args.reject_threshold,
            )
        )
        if args.verbose:
            print(
                f"[{position}/{len(scenarios)}] {rows[-1]['scenario_id']} -> {rows[-1]['outcome']}",
                file=sys.stderr,
                flush=True,
            )
    dump_sha256 = None
    if args.rows_out:
        args.rows_out.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows)
        args.rows_out.write_text(payload, encoding="utf-8")
        dump_sha256 = hashlib.sha256(payload.encode()).hexdigest()
    return _write_report(
        args,
        rows=rows,
        scenarios=scenarios,
        frozen_manifest=frozen_manifest,
        missing=[],
        sources=[],
        rows_dump_sha256=dump_sha256,
    )


def _add_pipeline_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--corpus-manifest", type=Path, default=Path(CORPUS_MANIFEST))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--stellar-radius", type=float, default=1.0)
    parser.add_argument("--stellar-mass", type=float, default=1.0)
    parser.add_argument("--reject-threshold", type=float, default=ADVERSARIAL_FPP_REJECT_THRESHOLD)
    parser.add_argument("--no-fit", dest="with_fit", action="store_false")
    parser.set_defaults(with_fit=True)


def _add_report_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", type=Path, default=Path(REQUIRED_OUTPUT))
    parser.add_argument("--minimum-per-family", type=int, default=6)
    parser.add_argument("--minimum-rejection-rate", type=float, default=0.8)
    parser.add_argument("--minimum-per-family-rejection-rate", type=float, default=0.5)
    parser.add_argument("--minimum-control-acceptance", type=float, default=0.5)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build-corpus")
    build.add_argument("--per-family", type=int, default=PER_FAMILY)
    build.add_argument("--output", type=Path, default=Path(CORPUS_MANIFEST))
    build.set_defaults(handler=build_corpus)

    contract = sub.add_parser("check")
    contract.add_argument("--corpus-manifest", type=Path, default=Path(CORPUS_MANIFEST))
    contract.add_argument("--minimum-per-family", type=int, default=PER_FAMILY)
    contract.set_defaults(handler=check_contract)

    shard = sub.add_parser("run-shard")
    shard.add_argument("--per-family", type=int, default=PER_FAMILY)
    shard.add_argument("--shard-index", type=int, required=True)
    shard.add_argument("--shard-count", type=int, default=1)
    shard.add_argument("--period-tolerance", type=float, default=0.02)
    shard.add_argument("--output", type=Path, required=True)
    _add_pipeline_arguments(shard)
    shard.set_defaults(handler=run_shard)

    collect = sub.add_parser("aggregate")
    collect.add_argument("--per-family", type=int, default=PER_FAMILY)
    collect.add_argument("--shard", type=Path, nargs="+", required=True)
    _add_pipeline_arguments(collect)
    _add_report_arguments(collect)
    collect.set_defaults(handler=aggregate)

    execute = sub.add_parser("run")
    execute.add_argument("--per-family", type=int, default=PER_FAMILY)
    execute.add_argument("--rows-out", type=Path, dest="rows_out")
    execute.add_argument("--period-tolerance", type=float, default=0.02)
    execute.add_argument("--verbose", action="store_true")
    _add_pipeline_arguments(execute)
    _add_report_arguments(execute)
    execute.set_defaults(handler=run)
    return root


def main() -> int:
    args = parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
