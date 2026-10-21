"""Cadence-impact robustness kampanyasi koşucusu.

``detrending_cadence_impact_robustness`` kapısının (program.json)
`required_output` kanıtını üretir:
    validation_runs/final_acceptance_v1/robustness/report.json

Ölçüm sözleşmesi `astrotransit.validation.robustness` içinde tanımlıdır;
detector ve pertürbasyonlar enjekte edilir. Varsayılan pertürbasyonlar
``cadence_scale`` (0.5 → sektörlerin yarısı, 0.25 → çeyreği) üzerinden
algılayıcıya taşınır; gerçek pipeline algılayıcısı bunları sektör
alt kümesi olarak yorumlar.

Eşikler ÇALIŞTIRILMADAN ONCE CLI üzerinden dondurulur ve rapora aynen
kaydedilir (post-hoc esik kaydirmak kapıyı geçersiz kılar).

Kullanım:
    # hızlı sözleşme doğrulaması (mock algılayıcı)
    python scripts/validation/run_robustness_campaign.py \
        --corpus validation_runs/corpus.json --max-cases 50 \
        --detector mock --output validation_runs/final_acceptance_v1/robustness/report.json

    # gerçek pipeline algılayıcısı (ağır; TESS indirir)
    python scripts/validation/run_robustness_campaign.py \
        --corpus validation_runs/corpus.json --max-cases 100 \
        --detector pipeline --force-map --skip-visualizations
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from astrotransit.validation import robustness
from astrotransit.validation.artifacts import write_artifact

MOD = "scripts.validation.run_robustness_campaign"


def load_cases(path: Path, max_cases: int) -> list[dict[str, Any]]:
    from astrotransit.validation.corpus import load_corpus

    cases = load_corpus(path)
    rows: list[dict[str, Any]] = []
    for case in cases:
        rows.append(
            {
                "target_id": case.target_id,
                "label": case.label,
                "reference": case.reference,
                "sectors": list(case.sectors),
                "notes": case.notes,
            }
        )
        if len(rows) >= max_cases:
            break
    return rows


def make_detector(
    detector_name: str,
    *,
    force_map: bool,
    skip_visualizations: bool,
    skip_catalog: bool,
):
    """Kapı sözleşmesine uyumlu detector callable'ı döndürür."""

    if detector_name == "mock":
        return _mock_detector
    if detector_name == "pipeline":
        return _pipeline_detector_factory(
            force_map=force_map,
            skip_visualizations=skip_visualizations,
            skip_catalog=skip_catalog,
        )
    raise ValueError(f"bilinmeyen detector: {detector_name}")


def _sectors_after_scale(case: Mapping[str, Any], scale: float) -> list[int] | None:
    sectors = case.get("sectors") or []
    if not sectors:
        return None  # algilayici tum sektörleri kendi seçer
    keep = max(1, round(len(sectors) * scale))
    return list(sectors[:keep])


def _mock_detector(case: Mapping[str, Any]) -> bool:
    """Deterministik sözleşme algılayıcısı: güçlü S/N şimletir.

    Gerçek kampanya için kullanılmaz; artefakt şema ve runner
    entegrasyonunu test etmek içindir.
    """

    score = sum(1 for c in str(case.get("target_id", "")) if c.isdigit())
    return score % 2 == 0 or bool(case.get("label") == "planet")


def _pipeline_detector_factory(
    *,
    force_map: bool,
    skip_visualizations: bool,
    skip_catalog: bool,
):
    def detector(case: Mapping[str, Any]) -> bool:
        from astrotransit.pipelines.orchestrator import AstroTransitOrchestrator

        target = str(case.get("target_id", "")).replace("TIC ", "")
        sectors_override = case.get("sectors_override")
        sectors = sectors_override if sectors_override is not None else case.get("sectors")
        with AstroTransitOrchestrator(
            force_map=force_map,
            force_mcmc=False,
            skip_visualization=skip_visualizations,
            skip_catalog=skip_catalog,
            log_level="WARNING",
        ) as orchestrator:
            result = orchestrator.run_single(target, sectors=sectors)
        return bool(result.success and result.candidates_found > 0)

    return detector


def _run_fingerprint(corpus: str, detector_name: str, force_map: bool) -> str:
    """Önbellek geçerliliği: corpus + dedektör konfigürasyonu parmak izi."""
    import hashlib

    payload = json.dumps(
        {"corpus": corpus, "detector": detector_name, "force_map": force_map},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _cached_detector_factory(
    base_detector,
    *,
    cache_path: Path,
    fingerprint: str,
):
    """Koşum-bazlı checkpoint sarmalayıcı (kesinti toleransı).

    Anahtar: (hedef, sektör-override kümesi). Aynı (hedef, sektör) çifti
    tekrar istenirse pipeline yeniden koşulmadan önbellekten döner; her yeni
    sonuç anında diske yazılır (append + flush) — kesintide tamamlanan
    koşumlar korunur. Yanlış-bilgilendirme riski yönlüdür: geçici ağ hatası
    False saklanabilir; bu, recall düşüşünü ASLA iyileştirmez, ancak
    gerektiğinde aşırı muhafazakâr sonuç (measured_fail) üretebilir.
    """

    cache: dict[str, bool] = {}
    if cache_path.exists():
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("fingerprint") != fingerprint:
                continue
            cache[record["key"]] = record["detected"]

    completed = len(cache)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    fh = cache_path.open("a", encoding="utf-8")

    def detector(case: Mapping[str, Any]) -> bool:
        nonlocal completed
        target = str(case.get("target_id", "")).replace("TIC ", "")
        override = case.get("sectors_override")
        key = target + "|" + (",".join(str(s) for s in override) if override is not None else "ALL")
        if key in cache:
            return cache[key]
        detected = bool(base_detector(case))
        cache[key] = detected
        fh.write(json.dumps({"fingerprint": fingerprint, "key": key, "detected": detected}) + "\n")
        fh.flush()
        completed += 1
        print(f"[run {completed}] {key} -> detected={detected}", flush=True)
        return detected

    return detector


def _perturbations() -> dict[str, Any]:
    """Kadans azaltma pertürbasyonları (sözleşme sabitleri)."""

    return {
        "cadence_50pct": lambda case: {**dict(case), "sectors_override": _sectors_after_scale(case, 0.5)},
        "cadence_25pct": lambda case: {**dict(case), "sectors_override": _sectors_after_scale(case, 0.25)},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=MOD)
    parser.add_argument("--corpus", required=True, help="Labelled corpus JSON")
    parser.add_argument("--max-cases", type=int, default=100)
    parser.add_argument("--detector", choices=["mock", "pipeline"], default="mock")
    parser.add_argument("--min-cases", type=int, default=100,
                        help="Dondurulan alt sinir (kapı eşik öncesi ilan edilir)")
    parser.add_argument("--declared-max-recall-drop", type=float, default=0.05,
                        help="Dondurulan kabul tavanı (kapı eşik öncesi ilan edilir)")
    parser.add_argument("--force-map", action="store_true")
    parser.add_argument("--skip-visualizations", action="store_true")
    parser.add_argument("--skip-catalog", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="Ölçüm yapmadan yalnızca eşik özetini döker")
    parser.add_argument("--output", default="validation_runs/final_acceptance_v1/robustness/report.json")
    args = parser.parse_args(argv)

    declared = {
        "min_cases": args.min_cases,
        "declared_max_recall_drop": args.declared_max_recall_drop,
        "detector": args.detector,
        "corpus": args.corpus,
    }
    if args.dry_run:
        print(json.dumps({"gate": "detrending_cadence_impact_robustness",
                          "declared": declared, "status": "pending_run"}, indent=2))
        return 0

    cases = load_cases(Path(args.corpus), args.max_cases)
    if not cases:
        print(f"[error] corpus boş: {args.corpus}", file=sys.stderr)
        return 2

    detector = make_detector(
        args.detector,
        force_map=args.force_map,
        skip_visualizations=args.skip_visualizations,
        skip_catalog=args.skip_catalog,
    )
    if args.detector == "pipeline":
        cache_path = Path(args.output).parent / "runs_cache.jsonl"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        fingerprint = _run_fingerprint(args.corpus, args.detector, args.force_map)
        detector = _cached_detector_factory(
            detector, cache_path=cache_path, fingerprint=fingerprint
        )
        print(f"[checkpoint] önbellek: {cache_path} fingerprint={fingerprint}", flush=True)
    campaign = robustness.measure_cadence_robustness(
        cases, detector, _perturbations()
    )
    gate = robustness.evaluate_cadence_robustness_gate(
        campaign,
        min_cases=args.min_cases,
        declared_max_recall_drop=args.declared_max_recall_drop,
    )
    payload = {
        "gate": "detrending_cadence_impact_robustness",
        "status": gate.status,
        "declared": declared,
        "blocking_reasons": list(gate.blocking_reasons),
        "result": gate.to_dict(),
    }
    write_artifact(payload, args.output)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if gate.status == "measured" else 1


if __name__ == "__main__":
    raise SystemExit(main())
