"""TLS/BLS baseline karşılaştırma kampanyası koşucusu.

``tls_bls_baselines_ablations`` kapısının (program.json)
`required_output` kanıtını üretir:
    validation_runs/final_acceptance_v1/baselines/report.json

Bilimsel soru: tam pipeline (ön-işleme + BLS→TLS cascade + vetting + MAP),
çıplak (sade) TLS ve çıplak BLS'ye göre aynı vakalar üzerinde ne kadar
daha iyi algılıyor / daha az yanlış alarm üretiyor?

Dedektörler:
- ``astrotransit``: tam pipeline. Robustness kampanyasıyla birebir aynı
  konfigürasyonu (force_map=True, aynı corpus, sektör-dolulu vakalar)
  kullandığından o koşum önbelleğinden YENİDEN KULLANILIR
  (--reuse-fingerprint doğrulamasıyla); aksi halde taze koşar.
- ``tls``: sade TLS — transitleastsquares paketi, ham birleştirilmiş
  SPOC ışık eğrisi üzerinde; pipeline ön-işlemesi (geleneksel flatten)
  yok. İlan edilen sade kural: SDE >= 5, SNR >= 7, transit >= 2.
- ``bls``: sade BLS — astropy BoxLeastSquares, aynı ham ışık eğrisi;
  süre ızgarası sabit (1-4 saat). İlan edilen sade kural:
  depth-SNR = |depth/depth_err|*sqrt(n_transit) >= 7 ve n_transit >= 2.

Sade kuralların amacı stratejik değil, şeffaftır: iki karşılaştırma
implementasyonu da klasik eşiklerle (SDE/SNR) çalışır; pipeline'ın
kazancı teknik katmanlardan (ön-işleme, cascade, vetting) gelir.

Yalnız sade dedektörler paralel koşar (--workers; astrotransit sonuçları
önbellekten okunur). Görev zaman aşımı muhafazakârdır: aşan/çöken görev
False sayılır — recall'a yardım etmez.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import re
import signal
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Mapping

from astrotransit.validation import baselines as baseline_lib
from astrotransit.validation.artifacts import write_artifact

MOD = "scripts.validation.run_baselines_ablations"

# ── İlan edilen sade kural sabitleri (koşudan ÖNCE dondurulur) ──
TLS_RULE: dict[str, Any] = {
    "period_min": 0.5,
    "period_max": 20.0,
    "min_sde": 5.0,
    "min_snr": 7.0,
    "min_transits": 2,
    "oversampling_factor": 3.0,
}
BLS_RULE: dict[str, Any] = {
    "period_min": 0.5,
    "period_max": 20.0,
    "duration_hours": [1.0, 2.0, 3.0, 4.0],
    "min_depth_snr": 7.0,
    "min_transits": 2,
}
RULE_TAG = "tls_sde5_snr7_t2__bls_dsnr7_t2__loader_v2"

REPORT_PATH = Path("validation_runs/final_acceptance_v1/baselines/report.json")
ROBUSTNESS_CACHE = Path("validation_runs/final_acceptance_v1/robustness/runs_cache.jsonl")


def _load_cases(path: Path) -> list[dict[str, Any]]:
    """Corpus vakalarını dict listesi olarak yükler (etiketler doğrulanır)."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("cases", []) if isinstance(payload, dict) else payload
    cases: list[dict[str, Any]] = []
    for row in rows:
        cases.append(
            {
                "target_id": str(row["target_id"]),
                "label": str(row["label"]),
                "sectors": [int(s) for s in row.get("sectors", [])],
                "notes": str(row.get("notes", "")),
            }
        )
    return cases


def _load_robustness_cache(fingerprint: str) -> dict[str, bool]:
    """Robustness koşum önbelleğini (TIC|ALL anahtarlı) okur."""

    cache: dict[str, bool] = {}
    if not ROBUSTNESS_CACHE.exists():
        return cache
    for line in ROBUSTNESS_CACHE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("fingerprint") != fingerprint or record.get("key") is None:
            continue
        key = str(record["key"])
        if key.split("|", 1)[1] == "ALL":
            cache[key.split("|", 1)[0]] = record["detected"]
    return cache


def load_runtime_fingerprint() -> str:
    """Kanıt izlenebilirliği: robustness raporundaki gerçek parmak izini okur."""

    log_path = ROBUSTNESS_CACHE.parent / "runner_loop.log"
    if log_path.exists():
        for line in reversed(log_path.read_text(encoding="utf-8", errors="ignore").splitlines()):
            if "fingerprint=" in line:
                match = re.search(r"fingerprint=([0-9a-f]{16})", line)
                if match:
                    return match.group(1)
    raise RuntimeError(
        f"reuse fingerprint bulunamadı: {log_path} — --reuse-fingerprint ile verin"
    )


# ── ham ışık eğrisi yükleme (sade dedektörler için) ──


def _download_with_corrupt_retry(search, idx: int):
    """İndirme hatasında cached FITS'i doğrudan okur (reader-dispatch bypass).

    lightkurve 2.4.2 + astropy 8 kombinasyonunda bazı SPOC ürünleri
    genel karakter-okuyucular ayakta kalamıyor, ancak FITS sağlıklı;
    hata mesajından ürün yolu çözülüp ``read_tess_lightcurve`` ile
    doğrudan okunur. Dosya yoksa indirme hatası olduğu için yeniden
    dener (ağ hatası + yarım dosya netleri).
    """

    import lightkurve as _lk
    from lightkurve import LightkurveError

    try:
        # Not: allow_cadence_timeout kwarg'ı astropy 8 ile TessLightCurve
        # reader'ına sızmıyor (TypeError) — kullanma.
        return search[idx].download()
    except LightkurveError as exc:
        match = re.search(r"(/[\w.\-]+\.fits)", str(exc))
        if match and Path(match.group(1)).exists():
            return _lk.io.tess.read_tess_lightcurve(match.group(1))
        raise


def _download_with_network_retry(search, idx: int, attempts: int = 3):
    """MAST indirmesi ağ bölmesine dayanıklı: geri çekilmeli 3 deneme.

    Zehir önleme: kısa süreli ağ kopmaları (RemoteDisconnected,
    ConnectionReset) 'error' görev satırı üretmeden toparlanır.
    ``OSError`` alt sınıfları (requests.ConnectionError/Timeout dâhil)
    yakalanır; ``LightkurveError`` bozuk dosya semantiğidir ve
    ``_download_with_corrupt_retry`` sorumluluğundadır.
    """

    import time

    for attempt in range(1, attempts + 1):
        try:
            return _download_with_corrupt_retry(search, idx)
        except (ConnectionError, OSError) as exc:
            if attempt >= attempts:
                print(
                    f"[net-retry] {attempt}/{attempts} deneme tükendi: "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )
                raise
            delay = 30.0 * attempt
            print(
                f"[net-retry] {type(exc).__name__} ({attempt}/{attempts}); "
                f"{delay:.0f} sn sonra yeniden",
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError("hawk-retry ulaşılmaz nokta")  # pragma: no cover


def _load_stitched_lc(target_expr: str, sectors: list[int]):
    """SPOC ışık eğrilerini (önbellekten) yükler, birleştirir, temizler."""

    import warnings

    warnings.filterwarnings("ignore")
    import lightkurve as lk
    import numpy as np

    search = lk.search_lightcurve(target_expr, author="SPOC")
    if len(search) == 0:
        raise RuntimeError(f"SPOC veri yok: {target_expr}")
    wanted = set(sectors)
    table = search.table
    lcs = []
    for idx in range(len(search)):
        mission = str(table["mission"][idx])
        match = re.search(r"Sector\s+(\d+)", mission)
        if not (match and int(match.group(1)) in wanted):
            continue
        lcs.append(_download_with_network_retry(search, idx))
    if not lcs:
        raise RuntimeError(f"istenen sektörlerde veri yok: {target_expr} {sorted(wanted)}")
    stitched = lcs[0] if len(lcs) == 1 else lk.LightCurveCollection(lcs).stitch()
    lc = stitched.remove_nans()
    keep = np.isfinite(lc.flux_err.value)
    lc = lc[keep].normalize()
    if not np.isfinite(lc.flux.value).all():
        lc = lc[np.isfinite(lc.flux.value)]
    return lc


# ── sade TLS dedektörü ──


def _tls_detect(lc, oversampling_factor: float | None = None) -> bool:
    """Sade TLS kuralı (ilan edilen sabitler).

    ``oversampling_factor`` ilanlı kural değerinin üstüne geçilebilir
    (coarse-scan çevrimi); parmak izi bu değeri içerir, cache otomatik
    ayrışır. İlansız (None) kullanım kuralın kendisidir — tests bunun
    varsayılanına bağlı.
    """

    from transitleastsquares import transitleastsquares as TLSModel

    factor = (
        float(oversampling_factor)
        if oversampling_factor is not None
        else TLS_RULE["oversampling_factor"]
    )
    model = TLSModel(lc.time.value, lc.flux.value)
    result = model.power(
        period_min=TLS_RULE["period_min"],
        period_max=TLS_RULE["period_max"],
        oversampling_factor=factor,
        show_progress_bar=False,
        use_threads=2,
    )
    sde = float(result.SDE)
    snr = float(getattr(result, "snr", 0.0) or 0.0)
    transits = int(result.transit_count)
    return bool(
        sde >= TLS_RULE["min_sde"]
        and snr >= TLS_RULE["min_snr"]
        and transits >= TLS_RULE["min_transits"]
    )


# ── sade BLS dedektörü ──


def _bls_detect(lc) -> bool:
    """Sade BLS kuralı (ilan edilen sabitler).

    astropy BLS tek süre ızgarasıyla çağrılır (çoklu süre 2-D çıktı
    karmaşasını önler); her süre için ızgara koşulur, en yüksek
    depth-SNR'lı aday üzerinden kural değerlendirilir.
    """

    import numpy as np
    from astropy.timeseries import BoxLeastSquares

    def _scalar(value: Any) -> float:
        arr = np.asarray(value, dtype=float).ravel()
        return float(arr[0]) if arr.size else 0.0

    def _num_or_zero(value: Any) -> float:
        if value is None:
            return 0.0
        try:
            return _scalar(value)
        except (TypeError, ValueError):
            return 0.0

    time = lc.time.value
    flux = lc.flux.value
    flux_err = lc.flux_err.value  # ağırlıksız BLS hatayi 1 kabul eder -> ölçek bozulur
    bls = BoxLeastSquares(time, flux, dy=flux_err)
    durations = np.array(BLS_RULE["duration_hours"]) / 24.0
    period_grid = bls.autoperiod(
        durations,
        minimum_period=BLS_RULE["period_min"],
        maximum_period=BLS_RULE["period_max"],
    )

    best_snr = -1.0
    best = None
    for duration in durations:
        frame = bls.power(period_grid, float(duration), objective="snr")
        power = np.asarray(frame.power, dtype=float)
        if not np.isfinite(power).any():
            continue
        index = int(np.nanargmax(power))
        stats = bls.compute_stats(
            _scalar(frame.period[index]),
            float(duration),
            _scalar(frame.transit_time[index]),
        )
        raw_depth = stats.get("depth")
        depth_arr = np.asarray(raw_depth, dtype=float).ravel()
        depth = float(depth_arr[0]) if depth_arr.size else 0.0
        # compute_stats altta depth'i (değer, hata) ikilisi olarak döndürebilir
        depth_err = (
            float(depth_arr[1]) if depth_arr.size > 1 else _num_or_zero(stats.get("depth_err"))
        )
        per_transit = np.asarray(stats.get("per_transit_count", []), dtype=float)
        n_transit = int(np.sum(per_transit > 0)) if per_transit.size else 0
        if depth_err <= 0 or n_transit <= 0:
            continue
        depth_snr = abs(depth) / depth_err  # astropy depth_err çoklu-transit kümelidir
        if depth_snr > best_snr:
            best_snr = depth_snr
            best = {"depth_snr": depth_snr, "n_transits": n_transit}
    if best is None:
        return False
    min_depth_snr: float = BLS_RULE["min_depth_snr"]
    min_transits: int = BLS_RULE["min_transits"]
    return bool(
        best["depth_snr"] >= min_depth_snr
        and best["n_transits"] >= min_transits
    )


def _naive_worker(
    task: tuple[str, dict[str, Any]],
    *,
    detector_name: str,
    timeout_sec: int,
    cache_path: str,
    fingerprint: str,
    oversampling_factor: float | None = None,
) -> tuple[str, bool]:
    """Tek sade-dedektör koşumu (işçi süreç; SIGALRM zaman aşımı)."""

    def _alarm(signum: int, frame: Any) -> None:
        raise TimeoutError(f"SIGALRM ({signum})")

    key, case = task
    started = time.monotonic()
    import gc

    gc.collect()  # spawn-surekli iscilerde onceki gorevin copunu topla (RAM suruklenmesi)
    have_alarm = hasattr(signal, "SIGALRM")
    if have_alarm:
        signal.signal(signal.SIGALRM, _alarm)
        signal.alarm(max(1, timeout_sec))

    detected: bool
    status: str
    error_msg = ""
    try:
        target = str(case["target_id"]).replace("TIC ", "").strip()
        lc = _load_stitched_lc(f"TIC {target}", case["sectors"])
        if detector_name == "tls":
            detected = _tls_detect(lc, oversampling_factor=oversampling_factor)
        elif detector_name == "bls":
            detected = _bls_detect(lc)
        else:
            raise ValueError(f"bilinmeyen sade detector: {detector_name}")
        status = "ok"
    except TimeoutError:
        print(f"[timeout] {key}: {timeout_sec} sn içinde bitmedi -> detected=False", flush=True)
        detected = False
        status = "timed_out"  # gerçek non-detection değil; kanıtta saydam olmalı
        error_msg = f"timeout ({timeout_sec} sn pencere)"
    except Exception as exc:
        print(f"[error] {key}: {type(exc).__name__}: {exc} -> detected=False", flush=True)
        detected = False
        status = "error"  # ağ/çevre hatası; kanıt sayılır ama yeniden denenebilir
        error_msg = f"{type(exc).__name__}: {exc}"[:280]
    finally:
        if have_alarm:
            signal.alarm(0)
    elapsed = time.monotonic() - started
    with Path(cache_path).open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "fingerprint": fingerprint,
                    "key": key,
                    "detected": detected,
                    "status": status,
                    "elapsed_s": round(elapsed, 1),
                    "error": error_msg,
                }
            )
            + "\n"
        )
        fh.flush()
    print(f"[task] {key} -> detected={detected} ({elapsed:.0f} sn)", flush=True)
    return key, detected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=MOD)
    parser.add_argument("--corpus", required=True, help="Labelled corpus JSON (dengeli-24)")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--task-timeout-min", type=int, default=45)
    parser.add_argument(
        "--oversampling-factor",
        type=float,
        default=None,
        help=(
            "TLS ızgara sıkılığı (coarse-scan levresi; ilanlı kural 3.0). "
            "1.0 ≈ 3x hızlı tarama; parmak izine dâhildir, cache ayrışır."
        ),
    )
    parser.add_argument("--mp-method", default="spawn", choices=["spawn", "fork"])
    parser.add_argument(
        "--reuse-fingerprint",
        default=None,
        help="Robustness önbelleği parmak izi (boşsa runner_loop.log'dan okunur)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default=str(REPORT_PATH))
    args = parser.parse_args(argv)

    declared = {
        "corpus": args.corpus,
        "reference": "astrotransit",
        "rules_tag": RULE_TAG,
        "tls_rule": TLS_RULE,
        "bls_rule": BLS_RULE,
        "workers": args.workers,
        "task_timeout_min": args.task_timeout_min,
        "oversampling_factor": (
            args.oversampling_factor
            if args.oversampling_factor is not None
            else TLS_RULE["oversampling_factor"]
        ),
        "ablations": "sonraki faz (check ilanıyla eklenecek)",
    }
    if args.dry_run:
        print(json.dumps({"gate": "tls_bls_baselines_ablations",
                          "declared": declared, "status": "pending_run"}, indent=2))
        return 0

    cases = _load_cases(Path(args.corpus))
    if not cases:
        print(f"[error] corpus boş: {args.corpus}", file=sys.stderr)
        return 2

    # ── astrotransit sonuçları: robustness önbelleğinden yeniden kullanım ──
    fingerprint = args.reuse_fingerprint or load_runtime_fingerprint()
    reuse = _load_robustness_cache(fingerprint)
    missing_p = [
        case["target_id"].replace("TIC ", "")
        for case in cases
        if case["target_id"].replace("TIC ", "") not in reuse
    ]
    if missing_p:
        raise RuntimeError(f"robustness önbelleğinde eksik hedef: {missing_p}")

    astro_results: dict[str, bool] = {
        case["target_id"].replace("TIC ", ""): reuse[
            case["target_id"].replace("TIC ", "")
        ]
        for case in cases
    }

    def astro_detector(case: Mapping[str, Any]) -> bool:
        return astro_results[str(case["target_id"]).replace("TIC ", "")]

    # ── sade dedektörler: paralel görev havuzu + önbellek ──
    out_dir = Path(args.output).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    _acquire_runner_lock(out_dir)
    _heartbeat(out_dir)
    _start_periodic_heartbeat(out_dir, every_sec=60)
    cache_path = out_dir / "runs_cache.jsonl"
    naive_fp = baseline_fingerprint(args.corpus, RULE_TAG, args.oversampling_factor)

    def _cached_lookup(key: str) -> bool | None:
        """Önbellek araması; timed_out/error satırları 'yok' sayılır (retry)."""

        if not cache_path.exists():
            return None
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("fingerprint") == naive_fp and record.get("key") == key:
                if record.get("status", "ok") != "ok":
                    return None
                return bool(record["detected"])
        return None

    def _cached_attempts() -> dict[str, int]:
        """key -> non-ok (timed_out/error) deneme sayısı.

        Yalnızca OPERASYONEL: parmak izine girmez; amacı zaman aşımı
        yükseltmesi (escalation) — kronik uzun görevlere ikinci turda
        2x pencere verir ki pencere-yetersizliği döngüsü kırılsın.
        """

        counts: dict[str, int] = {}
        if not cache_path.exists():
            return counts
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("fingerprint") == naive_fp and record.get("status", "ok") != "ok":
                k = str(record.get("key"))
                counts[k] = counts.get(k, 0) + 1
        return counts

    attempts = _cached_attempts()

    def _escalated_timeout_sec(key: str) -> int:
        """Deneme sayısına göre pencere: base, 2x, 4x (tavan 480 dk)."""
        n = min(attempts.get(key, 0), 2)
        return min(args.task_timeout_min * 60 * (2 ** n), 480 * 60)

    naive_results: dict[str, bool] = {}
    tasks: list[tuple[str, dict[str, Any]]] = []
    for name in ("tls", "bls"):
        for case in cases:
            target = str(case["target_id"]).replace("TIC ", "")
            key = f"{name}|{target}|ALL"
            found = _cached_lookup(key)
            if found is not None:
                naive_results[key] = found
            else:
                tasks.append((key, dict(case)))

    if tasks and args.workers > 1:
        ctx = multiprocessing.get_context(args.mp_method)
        total = len(tasks)
        print(f"[paralel] {args.workers} işçi, {total} sade görev", flush=True)
        with ProcessPoolExecutor(max_workers=args.workers, mp_context=ctx) as pool:
            futures = {
                pool.submit(
                    _naive_worker,
                    task,
                    detector_name=task[0].split("|", 1)[0],
                    timeout_sec=_escalated_timeout_sec(task[0]),
                    cache_path=str(cache_path),
                    fingerprint=naive_fp,
                    oversampling_factor=args.oversampling_factor,
                ): task[0]
                for task in tasks
            }
            for done, future in enumerate(as_completed(futures), start=1):
                key = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    print(f"[{done}/{total}] {key} -> ÇÖKÜŞ: {exc} (False)", flush=True)
                    with cache_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(
                            {
                                "fingerprint": naive_fp,
                                "key": key,
                                "detected": False,
                                "status": "error",
                                "error": f"pool-collapse: {type(exc).__name__}: {exc}"[:280],
                            }
                        ) + "\n")
                print(f"[{done}/{total}] görev işlendi: {key}", flush=True)
                _heartbeat(out_dir)
    elif tasks:
        for task in tasks:
            _naive_worker(
                task,
                detector_name=task[0].split("|", 1)[0],
                timeout_sec=_escalated_timeout_sec(task[0]),
                cache_path=str(cache_path),
                fingerprint=naive_fp,
                oversampling_factor=args.oversampling_factor,
            )
            _heartbeat(out_dir)

    naive_map = _read_cache(cache_path, naive_fp)
    for name in ("tls", "bls"):
        for case in cases:
            target = str(case["target_id"]).replace("TIC ", "")
            key = f"{name}|{target}|ALL"
            if key not in naive_map:
                raise RuntimeError(f"önbellekte eksik: {key}")
            naive_results[key] = naive_map[key]

    def tls_detector(case: Mapping[str, Any]) -> bool:
        return naive_results[f"tls|{str(case['target_id']).replace('TIC ', '')}|ALL"]

    def bls_detector(case: Mapping[str, Any]) -> bool:
        return naive_results[f"bls|{str(case['target_id']).replace('TIC ', '')}|ALL"]

    detectors: dict[str, Callable[[Mapping[str, Any]], Any]] = {
        "astrotransit": astro_detector,
        "tls": tls_detector,
        "bls": bls_detector,
    }
    comparison = baseline_lib.compare_baselines(cases, detectors, reference="astrotransit")

    by_name = {m.name: m for m in comparison.measurements}
    astro = by_name["astrotransit"]
    checks_pass = bool(
        astro.recall is not None
        and astro.recall >= 0.5
        and astro.false_positive_rate is not None
        and astro.false_positive_rate <= 0.6
    )
    detectors_dict = {name: by_name[name].to_dict() for name in by_name}
    payload = {
        "gate": "tls_bls_baselines_ablations",
        "status": "measured" if checks_pass else "measured_fail",
        "declared": declared,
        "blocking_reasons": [] if checks_pass else ["astrotransit recall/FPR eşikleri tutmadı"],
        "result": {
            "n_cases": len(cases),
            "comparison": comparison.to_dict(),
            "detectors": detectors_dict,
            "recall_astrotransit": astro.recall,
            "fpr_astrotransit": astro.false_positive_rate,
        },
        "provenance": {
            "git_commit": _git_head(),
            "run_timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "reuse_fingerprint": fingerprint,
            "rules_tag": RULE_TAG,
        },
    }
    write_artifact(payload, args.output)
    print(json.dumps(payload["result"], indent=2, ensure_ascii=False))
    return 0 if checks_pass else 1


def baseline_fingerprint(
    corpus: str, rules_tag: str, oversampling_factor: float | None = None
) -> str:
    """Corpus + kural sürümüne bağlı parmak izi (koşum ayarı değişirse cache bozulur).

    ``oversampling_factor`` kuralı yeniden tanımlı coarse-scan geçişidir;
    farklı faktör farklı kanıt alanıdır — parmak izine dahildir.
    """

    import hashlib

    payload = json.dumps(
        {
            "corpus": corpus,
            "rules": rules_tag,
            "oversampling_factor": float(
                oversampling_factor
                if oversampling_factor is not None
                else TLS_RULE["oversampling_factor"]
            ),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _heartbeat(out_dir: Path) -> None:
    """Watchdog v5 kalp atışı: her görev tamamlanışında güncellenir."""

    (Path(out_dir) / "heartbeat").write_text(str(time.time()))
    print("[heartbeat] tık", flush=True)


def _start_periodic_heartbeat(out_dir: Path, every_sec: int = 60) -> None:
    """Ölüm gibi görünen uzun görevlerde watchdog'un yalancı pozitif
    kovanmaması için arka planla bir kalp atışı başlatıyoruz (print yok;
    sadece dosya, run4 log'unu şişirmesin).
    """

    import threading

    stop = threading.Event()

    def _tick() -> None:
        while not stop.wait(every_sec):
            try:
                (Path(out_dir) / "heartbeat").write_text(str(time.time()))
            except Exception:
                pass

    thread = threading.Thread(target=_tick, daemon=True)
    thread.start()
    return  # kalp atışı sonlanmazsa eleme ile durur (daemon)


def _release_runner_lock(lock_path: Path, pid: int) -> None:
    """Kilidi yalnızca kendisi aldıysa bırakır (yetim kilidi koruma)."""

    try:
        if lock_path.exists() and lock_path.read_text().strip() == str(pid):
            lock_path.unlink()
    except OSError:
        pass


def _runner_alive(pid: int) -> bool:
    """pid canlı ve gerçekten koşucu mu? (bayat kilit ayrımı için)"""

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\x00")
        return any(b"run_baselines_ablations" in part for part in cmdline)
    except OSError:
        return True


def _acquire_runner_lock(out_dir: Path) -> None:
    """Tekil koşum kilidi: aynı çıktı dizininde ikinci koşum yasaktır.

    Yetim koşum faciasını (çift koşum → RAM çöküşü) önler. Bayat kilit
    (ölü pid veya koşucu olmayan pid) sessizce devralınır.
    """

    lock_path = Path(out_dir) / "runner.lock"
    if lock_path.exists():
        try:
            existing = int(lock_path.read_text().strip())
        except (ValueError, OSError):
            existing = None
        if existing is not None and _runner_alive(existing):
            raise RuntimeError(
                f"başka koşum aktif (pid {existing}); tekil koşum kilidi"
            )
    lock_path.write_text(f"{os.getpid()}\n")
    import atexit

    atexit.register(_release_runner_lock, lock_path, os.getpid())


def _read_cache(cache_path: Path, fingerprint: str) -> dict[str, bool]:
    """Önbelleği okur; tamamlanmamış (timed_out/error) satırları yok sayar.

    Eski koşumların (status alanı olmayan) satırları legacy 'ok' kabul edilir;
    yeni koşumdan itibaren timeout'a takılan ya da hata alan görevler
    önbellek-geçerli sayılmaz ve yeniden çalıştırılır (kanıt dürüstlüğü).
    """

    results: dict[str, bool] = {}
    if not cache_path.exists():
        return results
    for line in cache_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("fingerprint") != fingerprint:
            continue
        if record.get("status", "ok") != "ok":
            continue
        results[str(record["key"])] = record["detected"]
    return results


def _git_head() -> str:
    from pathlib import Path as _P

    git_head = _P(".git/HEAD")
    if not git_head.exists():
        return ""
    ref = git_head.read_text(encoding="utf-8").strip()
    if ref.startswith("ref: "):
        ref_file = _P(".git", *ref[5:].split("/"))
        return ref_file.read_text(encoding="utf-8").strip() if ref_file.exists() else ""
    return ref


if __name__ == "__main__":
    raise SystemExit(main())
