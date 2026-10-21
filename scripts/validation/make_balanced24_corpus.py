"""Robustness için çok-sektörlü, dengeli 24'lük çalışma corpus'u üretir.

Arka plan (epistemik düzeltme, 2026-10-21):
1) dev_manifest.json'da tüm vaka sektör listeleri boştu (sectors=[]);
   kadans kıyımı pertürbasyonları (50%/25%) sektör alt kümesi olarak
   tanımlı olduğundan pertürbasyonlar no-op'a düşüyor, recall düşüşü
   matematiksel olarak 0 çıkacaktı (boş kanıt).
2) Corpus FP-önce sıralı olduğundan ilk 24 vakanın tamamı false_positive
   idi; "recall" metriği gezegen vakalarında hiç ölçülmeyecekti.
3) Yerel lightkurve önbelleği eski kapı koşumlarından kalma tek-sektörlü
   indirmeler içeriyor: 72 planet hedefinin 71'inde 1 sektör, >=4 sektörü
   olan 0. Yerel veriyle anlamlı kadans kıyımı kurulamaz — MAST
   kullanılabilirlik taraması gereklidir.

Yöntem:
- Kullanılabilirlik: yerel önbellek ∪ MAST SPOC mission-search
  (lightkurve; metadata sorgusu, veri indirmez). Sonuçlar
  ``sector_availability.json`` dosyasında birikir (yeniden koşularda
  ağ sorgusu tekrarı olmaz).
- Seçim: corpus sırasında >=4 sektörlü İLK 12 planet + İLK 12
  false_positive (veri-varlığı kriteri; dedektör çıktısına danışılmaz,
  deterministik).
- Baseline maliyet sınırı: sektör listesi artan sıralı İLK 6 ile
  kesilir (yazılan ``sectors`` alanı); 50% → 3, 25% → 1-2 sektör.
  Ham kullanılabilirlik listesi ``sectors_available`` alanında saklanır.

Çıktı: dev_holdout/dev_manifest_balanced24.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SOURCE = Path("validation_runs/final_acceptance_v1/dev_holdout/dev_manifest.json")
TARGET_PATH = Path("validation_runs/final_acceptance_v1/dev_holdout/dev_manifest_balanced24.json")
AVAILABILITY_PATH = Path(
    "validation_runs/final_acceptance_v1/dev_holdout/sector_availability.json"
)

N_PER_LABEL = 12
MIN_SECTORS = 4
MAX_BASELINE_SECTORS = 6


def sectors_from_cache(target: str) -> list[int]:
    """Yerel lightkurve önbelleğinden sektörleri toplar.

    Ad biçimi: ``tess<zamanDamgasi>-s<sektor>-<sifirliTIC>-<versiyon>``;
    ilk sayı kümesi zaman damgasıdır, TIC üçüncü token'dadır.
    """

    base = Path.home() / ".cache/lightkurve/mastDownload/TESS"
    if not base.exists():
        return []
    sectors: set[int] = set()
    for path in base.iterdir():
        tokens = path.name.split("-")
        if len(tokens) < 3 or not tokens[2].isdigit():
            continue
        if str(int(tokens[2])) != target:
            continue
        sector_token = tokens[1].lstrip("s")
        if sector_token.isdigit():
            sectors.add(int(sector_token))
    return sorted(sectors)


def sectors_from_mast(target: str) -> list[int]:
    """MAST mission-search (lightkurve) ile SPOC sektörlerini sorgular.

    Metadata sorgusudur — ışık eğrisi indirmez. Boş sonuçta
    kolon farklarından korumalıdır.
    """

    import warnings

    warnings.filterwarnings("ignore")
    import lightkurve as lk

    result = lk.search_lightcurve(f"TIC {int(target)}", author="SPOC")
    sectors: set[int] = set()
    if len(result) == 0:
        return []
    table = result.table
    if "mission" not in table.colnames:
        return []
    for mission in table["mission"]:
        match = re.search(r"Sector\s+(\d+)", str(mission))
        if match:
            sectors.add(int(match.group(1)))
    return sorted(sectors)


def load_availability() -> dict[str, list[int]]:
    if AVAILABILITY_PATH.exists():
        payload = json.loads(AVAILABILITY_PATH.read_text(encoding="utf-8"))
        return {str(k): [int(s) for s in v] for k, v in payload.items()}
    return {}


def save_availability(known: dict[str, list[int]]) -> None:
    AVAILABILITY_PATH.write_text(
        json.dumps(known, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def availability_for(target: str, known: dict[str, list[int]]) -> list[int]:
    """Önbellek ∪ MAST taraması; sonuç birikimli dosyada saklanır."""

    if target in known:
        return known[target]
    sectors = sorted(set(sectors_from_cache(target)) | set(sectors_from_mast(target)))
    known[target] = sectors
    save_availability(known)
    return sectors


def main() -> int:
    raw = json.loads(SOURCE.read_text(encoding="utf-8"))
    cases = raw["cases"] if isinstance(raw, dict) else raw
    known_availability = load_availability()

    selected: list[dict] = []
    scanned = 0
    for label in ("planet", "false_positive"):
        picked = 0
        for case in cases:
            if picked >= N_PER_LABEL:
                break
            if case.get("label") != label:
                continue
            target = str(case["target_id"]).replace("TIC ", "").strip()
            scanned += 1
            available = availability_for(target, known_availability)
            if len(available) < MIN_SECTORS:
                continue
            picked += 1
            entry = dict(case)
            entry["sectors_available"] = list(available)
            entry["sectors"] = list(available[:MAX_BASELINE_SECTORS])
            entry["sectors_source"] = "cache+mast"
            selected.append(entry)
            print(
                f"[{label} {picked}/{N_PER_LABEL}] TIC {target}: "
                f"{len(available)} sektör (baseline ilk {len(entry['sectors'])})",
                flush=True,
            )
        if picked < N_PER_LABEL:
            print(f"UYARI: {label} için yeterli >=4 sektör hedefi yok ({picked})")

    write_output(selected)
    return 0 if len(selected) == 2 * N_PER_LABEL else 1


def write_output(selected: list[dict]) -> None:
    payload = {
        "schema_version": 1,
        "derived_from": "dev_manifest.json",
        "selection": (
            "dengeli_24: corpus sırasında >=4 SPOC sektörü olan ilk 12 "
            "'planet' + ilk 12 'false_positive' (veri-varlığı kriteri; "
            "dedektöre danışılmadan, deterministik)"
        ),
        "sector_fill": (
            "kullanılabilirlik: yerel önbellek ∪ MAST SPOC mission-search; "
            "baseline sektör listesi artan sıralı ilk 6 ile sınırlandırılır "
            "(sectors_available ham liste, sectors yazılan baseline)"
        ),
        "cases": selected,
    }
    TARGET_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"yazıldı: {TARGET_PATH} (vaka={len(selected)})")


if __name__ == "__main__":
    raise SystemExit(main())
