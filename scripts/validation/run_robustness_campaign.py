"""Cadence-impact robustness kampanyasi koşucusu.

``detrending_cadence_impact_robustness`` kapısının (program.json)
`required_output` kanıtını üretir:
    validation_runs/final_acceptance_v1/robustness/report.json

Ölçüm sözleşmesi `astrotransit.validation.robustness` içinde tanımlıdır;
detector ve pertürbasyonlar enjekte edilir. Varsayılan pertürbasyonlar
``cadence_scale`` (0.5 → sektörlerin yarısı, 0.25 → çeyreği) üzerinden
algılayıcıya taşınır; gerçek pipeline algılayıcısı bunları sektör
alt kümesi olarak yorumlar. Gerekçe: pertürbasyonların anlamlı olması
için vaka sektör listelerinin dolu olması ŞARTtır (boş listede kıyım
no-op'a düşer ve recall düşüşü yapay olarak 0 çıkar); çalışma corpus'u
``scripts/validation/make_balanced24_corpus.py`` ile dengeli ve
sektör-dolulu üretilir.

Paralel mod (--workers > 1): tüm (vaka, varyant) koşumları süreç
havuzunda koşulur, sonuçlar koşum-cache.diske akar (kesinti toleransı);
sonrasında ölçüm, önceden hesaplanmış sonuçlarla anında yapılır.
Görev başına zaman aşımı (--task-timeout-min): aşan/çöken görev
``detected=False`` sayılır (muhafazakâr yön — recall düşüşü asla
iyileştirilmez). Varsayılan mod (--workers 1) eski seri davranıştır.

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
import multiprocessing
import os
import signal
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
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


def _task_key(case: Mapping[str, Any]) -> str:
    """Koşum önbellek anahtarı: (hedef, sektör-override kümesi).

    Override yoksa ``ALL`` (vakanın kendi sektör listesiyle koşum);
    override varsa virgülle birleştirilmiş sektör listesi. Bu fonksiyon
    hem seri checkpoint sarmalayıcı hem de paralel görev planlayıcı
    tarafından paylaşılır — anahtar türetmede sürüklenme olmasın.
    """

    target = str(case.get("target_id", "")).replace("TIC ", "")
    override = case.get("sectors_override")
    suffix = ",".join(str(s) for s in override) if override is not None else "ALL"
    return f"{target}|{suffix}"


def _load_cache_records(cache_path: Path, fingerprint: str) -> dict[str, bool]:
    """Önbellek dosyasını okur; yalnızca eşleşen parmak izini döndürür."""

    cache: dict[str, bool] = {}
    if not cache_path.exists():
        return cache
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
    return cache


def _append_cache_line(cache_path: Path, fingerprint: str, key: str, detected: bool) -> None:
    """Tek koşum sonucunu diske yazar (atomik küçük satır: O_APPEND)."""

    with cache_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"fingerprint": fingerprint, "key": key, "detected": detected}) + "\n")
        fh.flush()


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

    cache: dict[str, bool] = _load_cache_records(cache_path, fingerprint)

    completed = len(cache)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    fh = cache_path.open("a", encoding="utf-8")

    def detector(case: Mapping[str, Any]) -> bool:
        nonlocal completed
        key = _task_key(case)
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


def _build_task_list(
    cases: list[dict[str, Any]],
    perturbations: Mapping[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """Tüm (vaka, varyant) koşumlarını tekil görev listesine çevirir.

    Sıra: her vaka için baseline → 50% → 25%. Anahtar bazında tekilleştirme
    yapılır (aynı (hedef, sektör) çifti iki kez koşulmaz).
    """

    tasks: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for case in cases:
        variants: list[dict[str, Any]] = [dict(case)]
        for perturb in perturbations.values():
            variants.append(dict(perturb(case)))
        for variant in variants:
            key = _task_key(variant)
            if key in seen:
                continue
            seen.add(key)
            tasks.append((key, variant))
    return tasks


def _set_thread_caps(workers: int) -> None:
    """İşçi süreçleri için BLAS/numba iş parçağı üst sınırı.

    Spawn bağlamında çocuklar bu env değerlerini miras alır; numpy/numba
    import anında okuduğu için havuz kurulmadan ÖNCE çağrılmalıdır. 8 CPU'da
    N işçi × 2 thread → aşırı aboneliği önler.
    """

    cap = "2" if workers > 1 else "4"
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
        os.environ.setdefault(var, cap)


def _alarm_handler(signum: int, frame: Any) -> None:
    """SIGALRM'u TimeoutError'a çevirir (görev düzeyi zaman aşımı)."""

    raise TimeoutError(f"SIGALRM ({signum})")


def _task_worker(
    task: tuple[str, dict[str, Any]],
    *,
    detector_name: str,
    timeout_sec: int,
    force_map: bool,
    skip_visualizations: bool,
    skip_catalog: bool,
    cache_path: str,
    fingerprint: str,
) -> tuple[str, bool]:
    """Tek (vaka, varyant) koşumunu işçi süreçte çalıştırır.

    Zaman aşımı: SIGALRM görev süresini sınırlar; aşılan görev
    ``detected=False`` sayılır (muhafazakâr yön — recall düşüşünü
    asla iyileştirmez). Beklenmeyen çöküş de aynı yönde False üretir;
    kampanya tek vakanın patolojisiyle kilitlenmez. Sonuç anında
    önbelleğe yazılır (kesinti toleransı ana süreçten bağımsız).
    """

    key, case = task
    started = time.monotonic()
    have_alarm = hasattr(signal, "SIGALRM")
    if have_alarm:
        signal.signal(signal.SIGALRM, _alarm_handler)
        signal.alarm(max(1, timeout_sec))
    detected: bool
    try:
        detector = make_detector(
            detector_name,
            force_map=force_map,
            skip_visualizations=skip_visualizations,
            skip_catalog=skip_catalog,
        )
        detected = bool(detector(case))
    except TimeoutError:
        print(f"[timeout] {key}: {timeout_sec} sn içinde bitmedi -> detected=False", flush=True)
        detected = False
    except Exception as exc:
        print(f"[error] {key}: {type(exc).__name__}: {exc} -> detected=False", flush=True)
        detected = False
    finally:
        if have_alarm:
            signal.alarm(0)
    elapsed = time.monotonic() - started
    _append_cache_line(Path(cache_path), fingerprint, key, detected)
    print(f"[task] {key} -> detected={detected} ({elapsed:.0f} sn)", flush=True)
    return key, detected


def _precomputed_detector(results: Mapping[str, bool]):
    """Önceden hesaplanmış sonuçlarla anında yanıt veren detector.

    Kütüphane sözleşmesi (detector callable) korunur; ağır iş havuzda
    bittiği için ölçüm döngüsü burada sıfır maliyetli çalışır. Eksik
    anahtar sessizce varsayılmaz — hataya düşer.
    """

    def detector(case: Mapping[str, Any]) -> bool:
        key = _task_key(case)
        if key not in results:
            raise RuntimeError(f"önbellekte eksik koşum: {key}")
        return results[key]

    return detector


def _run_parallel_tasks(
    tasks: list[tuple[str, dict[str, Any]]],
    *,
    detector_name: str,
    workers: int,
    mp_method: str,
    timeout_sec: int,
    force_map: bool,
    skip_visualizations: bool,
    skip_catalog: bool,
    cache_path: Path,
    fingerprint: str,
) -> None:
    """Eksik görevleri süreç havuzunda koşar; sonuçlar önbelleğe akar."""

    if not tasks:
        return
    _set_thread_caps(workers)
    ctx = multiprocessing.get_context(mp_method)
    total = len(tasks)
    print(f"[paralel] {workers} işçi, {total} görev, görev zaman aşımı {timeout_sec // 60} dk", flush=True)
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as pool:
        futures = {
            pool.submit(
                _task_worker,
                task,
                detector_name=detector_name,
                timeout_sec=timeout_sec,
                force_map=force_map,
                skip_visualizations=skip_visualizations,
                skip_catalog=skip_catalog,
                cache_path=str(cache_path),
                fingerprint=fingerprint,
            ): task[0]
            for task in tasks
        }
        for done, future in enumerate(as_completed(futures), start=1):
            key = futures[future]
            try:
                future.result()
            except Exception as exc:
                # İşçi süreci kendisi çöktü (ör. OOM): muhafazakâr False
                # kaydet; kampanya tek görevle ölmesin.
                print(f"[{done}/{total}] {key} -> İŞÇİ ÇÖKÜŞÜ: {exc} (False kaydediliyor)", flush=True)
                _append_cache_line(cache_path, fingerprint, key, False)


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
    parser.add_argument("--workers", type=int, default=1,
                        help="Paralel işçi süreci sayısı (yalnız pipeline detector; 1=seri)")
    parser.add_argument("--task-timeout-min", type=int, default=45,
                        help="Görev başına zaman aşımı (dk); aşılan görev False sayılır")
    parser.add_argument("--mp-method", default="spawn", choices=["spawn", "fork"],
                        help="Çok işlemci bağlamı (testler fork kullanabilir)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Ölçüm yapmadan yalnızca eşik özetini döker")
    parser.add_argument("--output", default="validation_runs/final_acceptance_v1/robustness/report.json")
    args = parser.parse_args(argv)

    declared = {
        "min_cases": args.min_cases,
        "declared_max_recall_drop": args.declared_max_recall_drop,
        "detector": args.detector,
        "corpus": args.corpus,
        "workers": args.workers,
        "task_timeout_min": args.task_timeout_min,
    }
    if args.dry_run:
        print(json.dumps({"gate": "detrending_cadence_impact_robustness",
                          "declared": declared, "status": "pending_run"}, indent=2))
        return 0

    cases = load_cases(Path(args.corpus), args.max_cases)
    if not cases:
        print(f"[error] corpus boş: {args.corpus}", file=sys.stderr)
        return 2

    cache_path = Path(args.output).parent / "runs_cache.jsonl"
    fingerprint = _run_fingerprint(args.corpus, args.detector, args.force_map)

    if args.workers > 1:
        # ── paralel yol: görevleri havuzda koş, sonra ölçümü önceden
        # hesaplanmış sonuçlarla anında yap (library sözleşmesi korunur).
        # Mock detector da bu yolu kullanabilir (test edilebilirlik) ──
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        perturbations = _perturbations()
        tasks = _build_task_list(cases, perturbations)
        known = _load_cache_records(cache_path, fingerprint)
        todo = [(key, case) for key, case in tasks if key not in known]
        print(
            f"[checkpoint] önbellek: {cache_path} fingerprint={fingerprint} "
            f"görev={len(tasks)} hazır={len(tasks) - len(todo)} kalan={len(todo)}",
            flush=True,
        )
        _run_parallel_tasks(
            todo,
            detector_name=args.detector,
            workers=args.workers,
            mp_method=args.mp_method,
            timeout_sec=args.task_timeout_min * 60,
            force_map=args.force_map,
            skip_visualizations=args.skip_visualizations,
            skip_catalog=args.skip_catalog,
            cache_path=cache_path,
            fingerprint=fingerprint,
        )
        known = _load_cache_records(cache_path, fingerprint)
        missing = [key for key, _ in tasks if key not in known]
        if missing:
            raise RuntimeError(f"paralel koşum sonrası eksik görev: {missing}")
        detector = _precomputed_detector(known)
    else:
        detector = make_detector(
            args.detector,
            force_map=args.force_map,
            skip_visualizations=args.skip_visualizations,
            skip_catalog=args.skip_catalog,
        )
        if args.detector == "pipeline":
            cache_path.parent.mkdir(parents=True, exist_ok=True)
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
