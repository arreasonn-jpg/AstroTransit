"""DEV-only ölçüm: ikincil tutulma (secondary eclipse) bayraklarının planet vs
FP dağılımı — körlü holdout'a dokunmaz.

``docs/blind_recall_roadmap.md`` Bulgu 1, madde 1: ``secondary_eclipse`` ve
``secondary_eclipse_snr`` testlerinin verdict dağılımı ile ölçüm değerlerinin
(derinlik oranı, SNR) gerçek gezegen ve yanlış-pozitif satırlarda nasıl
ayrıştığını eğitim/dev corpora üzerinde ölçer. Hiçbir eşik değiştirmez; yalnızca
teşhis üretir.

Giriş: ``run_dev_vetting_eval.py`` çıktısı (``validation_runs/_triage/dev_eval_shard0.json``)
veya ``run_blind_holdout`` shard satırları (``--rows`` ile, salt-okunur).

Kullanım:
    python scripts/validation/analyze_dev_secondary_eclipse.py \
        --rows validation_runs/_triage/dev_eval_shard0.json \
        --output validation_runs/_triage/dev_secondary_eclipse.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SEC_TESTS = ("secondary_eclipse", "secondary_eclipse_snr")


def _load_rows(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl" or not text.lstrip().startswith("{"):
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    payload = json.loads(text)
    if isinstance(payload, list):
        return list(payload)
    if isinstance(payload.get("rows"), list):
        return list(payload["rows"])
    raise ValueError(f"{path}: satır listesi bulunamadı (rows alanı veya JSONL beklenir)")


def _bucket(label: Any) -> str:
    return "false_positive" if str(label) == "false_positive" else "planet"


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower, upper = int(position), min(int(position) + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "min": min(values),
        "p25": _percentile(values, 0.25),
        "median": _percentile(values, 0.5),
        "p75": _percentile(values, 0.75),
        "max": max(values),
    }


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Satırlardan ikincil tutulma teşhis raporu üretir (gate belirtmez)."""

    if not rows:
        raise ValueError("rows boş olamaz")

    verdict_counts: dict[str, Counter] = {"planet": Counter(), "false_positive": Counter()}
    ratio_values: dict[str, list[float]] = defaultdict(list)
    snr_values: dict[str, list[float]] = defaultdict(list)
    # Aday derinliğine göre normalize ikincil derinlik (secondary / primary)
    normalized: dict[str, list[float]] = defaultdict(list)
    # Korelasyon: aynı sektörde iki testin birlikte verdict kombinasyonları
    combo_counts: dict[str, Counter] = {"planet": Counter(), "false_positive": Counter()}
    # Kabul/veto ile bayrak ilişkisi (satır bazında: vetoed satırlardaki bayraklar)
    vetoed_flags: Counter = Counter()
    accepted_flags: Counter = Counter()
    # Sessiz sızma: FP olup hiç fail/warn bayrağı almadan kabul edilenler
    silent_leaks: list[str] = []

    for row in rows:
        label = _bucket(row.get("label"))
        accepted = row.get("accepted_candidate")
        for sector in row.get("per_sector") or []:
            if not sector.get("has_candidate"):
                continue
            verdicts: dict[str, str] = {}
            sec_value = None
            sec_snr = None
            for test in sector.get("vetting_tests") or []:
                name = str(test.get("name") or "")
                verdict = str(test.get("verdict") or "")
                if name in SEC_TESTS:
                    verdicts[name] = verdict
                    verdict_counts[label][f"{name}:{verdict}"] += 1
                    if name == "secondary_eclipse":
                        sec_value = test.get("value")
                    if name == "secondary_eclipse_snr":
                        sec_snr = test.get("value")
            combo = f"sec={verdicts.get('secondary_eclipse', '-')}/snr={verdicts.get('secondary_eclipse_snr', '-')}"
            combo_counts[label][combo] += 1
            cand_depth = sector.get("candidate_depth_ppm")
            sec_depth = sector.get("metric_secondary_eclipse_depth_ppm")
            if sec_depth is not None:
                snr_values[label].append(float(sec_snr or 0.0))
                if cand_depth:
                    normalized[label].append(float(sec_depth) / float(cand_depth))
                else:
                    normalized[label].append(float("nan"))
            if sec_value is not None:
                ratio_values[label].append(float(sec_value))
        flags = [f for s in row.get("per_sector") or [] for f in s.get("vetting_fp_flags") or []]
        if accepted is True:
            accepted_flags.update(flags)
            if label == "false_positive" and not any(
                str(t.get("verdict")) in {"fail", "warn"}
                for s in row.get("per_sector") or []
                for t in s.get("vetting_tests") or []
            ):
                silent_leaks.append(str(row.get("target_id") or "?"))
        elif accepted is False and any(s.get("has_candidate") for s in row.get("per_sector") or []):
            vetoed_flags.update(flags)

    def _clean(values: list[float]) -> list[float]:
        return [v for v in values if v == v]

    return {
        "n_rows": len(rows),
        "label_counts": dict(Counter(_bucket(r.get("label")) for r in rows)),
        "secondary_test_verdicts": {
            label: dict(counter.most_common()) for label, counter in verdict_counts.items() if counter
        },
        "verdict_combinations": {
            label: dict(counter.most_common()) for label, counter in combo_counts.items() if counter
        },
        "secondary_depth_ratio_stats": {label: _stats(_clean(vals)) for label, vals in ratio_values.items()},
        "secondary_snr_stats": {label: _stats(_clean(vals)) for label, vals in snr_values.items()},
        "secondary_normalized_depth_stats": {label: _stats(_clean(vals)) for label, vals in normalized.items()},
        "vetoed_flag_counts": dict(vetoed_flags.most_common()),
        "accepted_flag_counts": dict(accepted_flags.most_common()),
        "silent_leak_targets": silent_leaks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.validation.analyze_dev_secondary_eclipse")
    parser.add_argument(
        "--rows",
        nargs="+",
        required=True,
        help="Dev eval veya shard dosyaları: .jsonl veya rows alanı içeren JSON",
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
