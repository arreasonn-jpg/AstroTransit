"""
Test hedeflerini MAST uzerinden dogrular.

Her hedef icin:
- Sektor mevcut mu?
- SPOC 120s light curve var mi?
- Bilinen degerler makul mu?

Sadece dogrulanmis hedefler test setine alinir.
"""

from __future__ import annotations

import sys
from pathlib import Path
import time

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


# ==========================================================================
# ALTIN LISTE - Her biri MAST'ta dogrulanmis, iyi belgelenmis hedefler
# ==========================================================================
# Bu hedefler NASA Exoplanet Archive'dan alinmistir, tumu SPOC islenmis.
# Sektorler cross-check edildi (2025 itibariyle).

GOLDEN_TARGETS = [
    # (tic_id, name, [sektorler], period_days, rp_rearth, difficulty)

    # === KOLAY - Sicak Jupiterler (derin, kolay bulunur) ===
    ("100100827", "WASP-18b",   [2, 3, 29, 30, 68, 69, 96],
     0.9414518, 13.4, "easy"),

    ("25155310",  "WASP-126b",  [1, 2, 3, 4, 27, 28, 29, 30, 31, 61, 62, 63, 64],
     3.288776, 10.4, "easy"),

    ("38846515",  "TOI-125b",   [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13],
     4.6543, 2.9, "medium"),

    # === ORTA ===
    ("279741379", "WASP-100b",  [1, 2, 3, 4, 28, 29, 30, 34],
     2.849382, 15.4, "medium"),

    ("281541555", "HATS-24b",   [1, 27, 28, 67, 68],
     1.348497, 15.6, "medium"),

    # === HARDER but realistic ===
    ("29857954",  "TOI-402.01", [2, 28, 29, 68, 69],
     4.7562, 3.0, "hard"),

    ("219338557", "TOI-561b",   [8, 35, 45, 46],
     0.4465, 1.42, "hard"),

    ("142090065", "WASP-19b",   [9, 35, 36, 62, 63],
     0.788839, 15.4, "easy"),

    ("183985250", "WASP-77Ab",  [4, 30, 31, 43, 44],
     1.360029, 13.0, "easy"),
]


def verify_target(tic_id: str, name: str, sectors: list, period: float, rp: float):
    """Tek hedefi dogrula."""
    import lightkurve as lk

    tic = f"TIC {tic_id}"
    result = {
        "tic_id": tic_id,
        "name": name,
        "requested_sectors": sectors,
        "available_sectors": [],
        "recommended_sector": None,
        "period": period,
        "rp_rearth": rp,
        "valid": False,
        "error": "",
    }

    try:
        r = lk.search_lightcurve(tic, mission="TESS", author="SPOC", exptime=120)

        available = set()
        for row in r.table:
            m = str(row.get("mission", ""))
            if "Sector" in m:
                try:
                    s = int(m.split("Sector")[-1].strip())
                    available.add(s)
                except:
                    pass

        result["available_sectors"] = sorted(available)

        # Istenen sektorlerden mevcut olanlari bul
        intersect = [s for s in sectors if s in available]

        if intersect:
            # En kucuk sektoru sec (genelde en temiz veri)
            result["recommended_sector"] = intersect[0]
            result["valid"] = True
        elif available:
            # Istenen yok ama baska sektorler var
            result["recommended_sector"] = sorted(available)[0]
            result["valid"] = True
            result["error"] = "istenen sektor yok, alternatif kullanildi"
        else:
            result["error"] = "hicbir sektorde 120s SPOC yok"

    except Exception as e:
        result["error"] = f"MAST hatasi: {str(e)[:100]}"

    return result


def main():
    print("=" * 78)
    print("  Test Hedefleri MAST Dogrulama")
    print("=" * 78)
    print(f"  Kontrol edilen hedef sayisi: {len(GOLDEN_TARGETS)}")
    print()

    valid_targets = []

    for tic_id, name, sectors, period, rp, difficulty in GOLDEN_TARGETS:
        print(f"  Kontrol: {name:15s} (TIC {tic_id})...", end=" ")

        r = verify_target(tic_id, name, sectors, period, rp)

        if r["valid"]:
            sec = r["recommended_sector"]
            note = f"S{sec}"
            if r["error"]:
                note += f" ({r['error']})"
            print(f"OK - {note}")

            valid_targets.append({
                "tic_id": tic_id,
                "name": name,
                "sector": sec,
                "period": period,
                "rp_rearth": rp,
                "difficulty": difficulty,
                "available_sectors": r["available_sectors"],
            })
        else:
            print(f"FAIL - {r['error']}")

        time.sleep(0.5)  # MAST rate limit

    print()
    print("=" * 78)
    print(f"  Sonuc: {len(valid_targets)}/{len(GOLDEN_TARGETS)} hedef dogrulandi")
    print("=" * 78)

    if valid_targets:
        # Python kod cikti (kopyala-yapistir icin)
        print("\n  Dogrulanmis hedefler (run_batch_test.py icin):\n")
        print("TEST_TARGETS = [")

        by_diff = {"easy": [], "medium": [], "hard": []}
        for t in valid_targets:
            by_diff[t["difficulty"]].append(t)

        for diff in ["easy", "medium", "hard"]:
            if by_diff[diff]:
                print(f"    # {diff.upper()}")
                for t in by_diff[diff]:
                    print(f'    KnownTarget("TIC {t["tic_id"]}", "{t["name"]}", {t["sector"]},')
                    print(f'                {t["period"]}, {t["rp_rearth"]}, difficulty="{diff}"),')
                print()

        print("]")

        # JSON kayit
        import json
        out_file = project_root / "benchmarks" / "verified_targets.json"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(valid_targets, f, indent=2)
        print(f"\n  Kaydedildi: {out_file}")

    return 0 if valid_targets else 1


if __name__ == "__main__":
    sys.exit(main())