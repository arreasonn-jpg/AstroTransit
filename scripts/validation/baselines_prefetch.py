"""Baselines koşumu için TESS-SPOC ışık eğrilerini ÖNDEN indirir.

İlanlı sözleşme DEĞİŞMEDİ (aynı görevler, aynı kurallar, aynı parmak izi):
yalnızca indirme aşaması koşumdan AYRILDI — MAST ağ hatası zehri kesilir;
koşum daha sonra önbellekten saf hesaplama yapar.

Kaynak: dev_manifest_balanced24.json (24 durum × 6 ilanlı sektör).
Işık eğrisi seçimi koşucu ile BİREBİR aynı:
    lk.search_lightcurve(f"TIC {target_id}", author="SPOC")
    mission'daki "Sector N" ∈ case["sectors"] ise her eşleşen sonuç indirilir.
"""

from __future__ import annotations

import json
import re
import sys
import time
import warnings
from pathlib import Path

MANIFEST = Path(
    "/home/erdem/AstroTransit/validation_runs/final_acceptance_v1/"
    "dev_holdout/dev_manifest_balanced24.json"
)
DELAYS = [30, 60, 120, 240, 480, 600]  # 6 deneme; kademeli bekleme


def main() -> int:
    warnings.filterwarnings("ignore")
    import lightkurve as lk

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cases = manifest["cases"]
    missing: list[str] = []

    for case in cases:
        target_id = str(case["target_id"]).replace("TIC ", "").strip()
        wanted = set(int(s) for s in case["sectors"])
        print(f"[pf] TIC {target_id} istenen sektörler={sorted(wanted)}", flush=True)
        search = lk.search_lightcurve(f"TIC {target_id}", author="SPOC")
        if len(search) == 0:
            print(f"[pf] TIC {target_id} HATA: SPOC arama boş", flush=True)
            missing.append(f"TIC {target_id} (arama boş)")
            continue
        table = search.table
        covered: set[int] = set()
        for idx in range(len(search)):
            mission = str(table["mission"][idx])
            m = re.search(r"Sector\s+(\d+)", mission)
            if not (m and int(m.group(1)) in wanted):
                continue
            sec = int(m.group(1))
            covered.add(sec)
            tag = f"TIC{target_id} S{sec} idx{idx}"
            for attempt in range(len(DELAYS)):
                try:
                    t0 = time.time()
                    search[idx].download()
                    print(f"[pf] {tag} ok ({time.time() - t0:.1f} sn)", flush=True)
                    break
                except Exception as exc:  # noqa: BLE001
                    msg = f"{type(exc).__name__}: {str(exc)[:120]}"
                    if attempt == len(DELAYS) - 1:
                        print(f"[pf] {tag} FAIL {msg}", flush=True)
                        missing.append(f"{tag} {msg}")
                    else:
                        delay = DELAYS[attempt]
                        print(
                            f"[pf] {tag} tekrar {attempt + 1}/{len(DELAYS)} ({msg}); {delay} sn",
                            flush=True,
                        )
                        time.sleep(delay)
        eksik = sorted(wanted - covered)
        if eksik:
            print(f"[pf] TIC {target_id} UYARI: istenirken aramada bulunamadı: {eksik}", flush=True)
            missing.append(f"TIC {target_id} sektör yok {eksik}")

    print("[pf] BİTTİ", flush=True)
    if missing:
        print(f"[pf] eksik satırlar: {len(missing)}", flush=True)
        for m in missing:
            print(f"  - {m}", flush=True)
        return 1
    print("[pf] TÜM DOSYALAR ÖN-İNDİRME TAM", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
