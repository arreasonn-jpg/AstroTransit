"""Blind holdout başarısızlık modu triyaj analizörü.

``blind_domain_holdout`` kampanyasının satır shard'larını okuyup
recall çöküşünü ve sızan yanlış pozitifleri **olgu bazında** kategorize
eder. Bu araç hiçbir eşiği değiştirmez, yeniden ölçmez ve sonucu geçerli
kabak yapmaz: yalnızca günlük-iyileştirme döngüsü için teşhis üretir.

Triyaj taksonomisi (satır başına tek mod):
    data_error   : hata ile sonuçlanmış (indirme, zaman aşımı, ...)
    no_sector    : sektör bulunamamış (sem Query)
    no_data      : sektör istenmiş ama hiçbir işlenen sektör başarılı
    no_candidate : aday üretilmemiş (algılama boşluğu — period kurtarılamadı)
    vetoed       : aday vardı ama kalite kapısı/fpp vetosu ile ele
    accepted     : kabul edilen (yalnız planet satırlarında beklenir)
    fp_leak      : FP etiketli satırda aday kabul edilmiş (sızma)

Kullanım:
    python scripts/validation/analyze_blind_holdout_failures.py \
        --rows validation_runs/blind_holdout/rows_shard*.jsonl \
        --output validation_runs/_triage/blind_triage.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

FAILURE_MODES = (
    "data_error",
    "no_sector",
    "no_data",
    "no_candidate",
    "vetoed",
    "accepted",
    "fp_leak",
)


def _load_rows(path: Path) -> list[dict[str, Any]]:
    """``run_blind_holdout`` shard formatlarını okur (.jsonl veya .json)."""

    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl" or not text.lstrip().startswith("{"):
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    payload = json.loads(text)
    if isinstance(payload, list):
        return payload
    if isinstance(payload.get("rows"), list):
        return list(payload["rows"])
    raise ValueError(f"{path}: satır listesi bulunamadı (rows alanı veya JSONL beklenir)")


def classify_row(row: dict[str, Any]) -> str:
    """Satırı taksonomiye göre tek moda koyar."""

    error = str(row.get("error") or "")
    if (
        "sector_lookup_failed" in error.lower()
        or "no_available_spoc" in error.lower()
        or not row.get("requested_sectors")
    ):
        return "no_sector"
    if error:
        return "data_error"
    label = str(row.get("label") or "")
    accepted = row.get("accepted_candidate")
    successful = int(row.get("successful_sector_count") or 0)
    if accepted is None or not isinstance(accepted, bool):
        return "data_error"
    if accepted:
        return "fp_leak" if label == "false_positive" else "accepted"
    if successful == 0:
        return "no_data"
    if not row.get("per_sector"):
        return "no_data"
    # Aday vardı mı? (hangi sektörde olursa)
    has_candidate = any(s.get("has_candidate") for s in row["per_sector"])
    return "no_candidate" if not has_candidate else "vetoed"


def _test_verdict_counts(rows: list[dict[str, Any]]) -> dict[str, Counter]:
    """Per-sector vetting test başına verdict sayaçları (planets + fp ayrımı)."""

    counts: dict[str, Counter] = {"planet": Counter(), "false_positive": Counter()}
    for row in rows:
        label = str(row.get("label") or "")
        bucket = counts.get(label)
        if bucket is None:
            continue
        for sector in row.get("per_sector") or []:
            for test in sector.get("vetting_tests") or []:
                if str(test.get("verdict") or "") in {"fail", "warn"}:
                    bucket[f"{test.get('name')}:{test.get('verdict')}"] += 1
    return counts


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Satır listesinden teşhis raporu üretir (gate belirtmez)."""

    if not rows:
        raise ValueError("rows boş olamaz; shard/rows.jsonl beklenir")

    buckets: Counter = Counter()
    samples_by: dict[str, list[str]] = defaultdict(list)
    errors_by_prefix: Counter = Counter()
    veto_flag_counts: Counter = Counter()
    fp_leak_flag_counts: Counter = Counter()

    for row in rows:
        mode = classify_row(row)
        buckets[mode] += 1
        tid = str(row.get("target_id") or "?")
        error = str(row.get("error") or "")
        if error:
            errors_by_prefix[error.split(":", 1)[0]] += 1
        if mode in {"vetoed", "fp_leak", "no_candidate"} and len(samples_by[mode]) < 8:
            samples_by[mode].append(tid)
        if mode == "vetoed":
            for sector in row.get("per_sector") or []:
                veto_flag_counts.update(sector.get("vetting_fp_flags") or [])
        if mode == "fp_leak":
            for sector in row.get("per_sector") or []:
                fp_leak_flag_counts.update(sector.get("vetting_fp_flags") or [])

    label_counts = Counter((("false_positive" if r.get("label") == "false_positive" else "planet")) for r in rows)
    test_counts = _test_verdict_counts(rows)

    return {
        "n_rows": len(rows),
        "label_counts": dict(label_counts),
        "modes": {mode: int(buckets.get(mode, 0)) for mode in FAILURE_MODES},
        "error_prefixes": dict(errors_by_prefix.most_common()),
        "veto_flag_counts": dict(veto_flag_counts.most_common()),
        "fp_leak_flag_counts": dict(fp_leak_flag_counts.most_common()),
        "vetting_test_verdicts": {
            label: dict(counter.most_common()) for label, counter in test_counts.items() if counter
        },
        "mode_samples": {mode: list(ids) for mode, ids in samples_by.items()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.validation.analyze_blind_holdout_failures")
    parser.add_argument(
        "--rows",
        nargs="+",
        required=True,
        help="Shard dosyaları: .jsonl veya run_blind_holdout report.json (rows alanı)",
    )
    parser.add_argument("--output", help="Teşhis raporu yazılacak yol (opsiyonel JSON)")
    args = parser.parse_args(argv)

    rows: list[dict[str, Any]] = []
    for raw_path in args.rows:
        path = Path(raw_path)
        if not path.is_file():
            print(f"[error] dosya yok: {path}", file=sys.stderr)
            return 2
        rows.extend(_load_rows(path))

    verdict = analyze(rows)
    summary = json.dumps(verdict, indent=2, ensure_ascii=False)
    print(summary)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(summary + "\n", encoding="utf-8")
        print(f"[ok] teşhis yazıldı: {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
