"""
run_batch_test.py TEST_TARGETS listesini
verified_targets.json'dan otomatik gunceller.

Boylece test hedefleri MAST dogrulanmis olur ve
bir daha 'No data found' hatasi alinmaz.
"""

from __future__ import annotations

import sys
import json
import re
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent

verified_file = project_root / "benchmarks" / "verified_targets.json"
batch_script = project_root / "scripts" / "run_batch_test.py"


def main():
    if not verified_file.exists():
        print(f"HATA: {verified_file} bulunamadi")
        print("Once calistirin: python scripts/verify_test_targets.py")
        return 1

    if not batch_script.exists():
        print(f"HATA: {batch_script} bulunamadi")
        return 1

    # Yedek al
    import shutil
    backup = batch_script.with_suffix(".py.backup_targets")
    shutil.copy(batch_script, backup)
    print(f"OK Yedek: {backup.name}")

    # Doğrulanmış hedefleri yükle
    with open(verified_file, "r", encoding="utf-8") as f:
        targets = json.load(f)

    print(f"OK {len(targets)} dogrulanmis hedef yuklendi")

    # Difficulty'ye göre grupla
    by_diff = {"easy": [], "medium": [], "hard": []}
    for t in targets:
        by_diff.get(t["difficulty"], []).append(t)

    # Yeni TEST_TARGETS bloğunu oluştur
    lines = ["TEST_TARGETS = ["]

    difficulty_labels = {
        "easy": "KOLAY - Sicak Jupiterler",
        "medium": "ORTA - Cesitli boyutlar",
        "hard": "ZOR - Kucuk gezegenler",
    }

    for diff in ["easy", "medium", "hard"]:
        group = by_diff.get(diff, [])
        if not group:
            continue

        lines.append(f"    # === {difficulty_labels[diff]} ===")
        for t in group:
            name_short = t["name"].replace("'", "").replace('"', "")
            note = t.get("note", f"P={t['period']:.3f}d, Rp={t['rp_rearth']:.1f} R_earth")
            lines.append(
                f'    KnownTarget("TIC {t["tic_id"]}", "{name_short}", {t["sector"]},'
            )
            lines.append(
                f'                {t["period"]}, {t["rp_rearth"]}, difficulty="{diff}",'
            )
            lines.append(
                f'                note="{note}"),'
            )
        lines.append("")

    lines.append("]")

    new_targets_block = "\n".join(lines)

    # Mevcut dosyayı oku
    content = batch_script.read_text(encoding="utf-8")

    # TEST_TARGETS bloğunu regex ile bul ve değiştir
    # Başlangıç: "TEST_TARGETS = ["
    # Bitiş: satır başında sadece "]" olan yer
    pattern = re.compile(
        r"TEST_TARGETS\s*=\s*\[.*?\n\]",
        re.DOTALL,
    )

    if pattern.search(content):
        content = pattern.sub(new_targets_block, content)
        batch_script.write_text(content, encoding="utf-8")
        print(f"OK {batch_script.name} guncellendi")

        print("\n-- Yeni Test Seti --")
        for diff in ["easy", "medium", "hard"]:
            group = by_diff.get(diff, [])
            print(f"  {diff:6s}: {len(group)} hedef")
            for t in group:
                print(f"    - {t['name']:15s} (TIC {t['tic_id']}, S{t['sector']})")

        print("\n-- Kontrol --")
        # Sözdizim kontrolü
        try:
            import ast
            ast.parse(batch_script.read_text(encoding="utf-8"))
            print("  OK Python sozdizimi gecerli")
        except SyntaxError as e:
            print(f"  FAIL Sozdizim hatasi: {e}")
            print(f"  Geri yukle: copy {backup} {batch_script}")
            return 1

        return 0
    else:
        print("HATA: TEST_TARGETS blogu bulunamadi")
        print(f"Geri yukle: copy {backup} {batch_script}")
        return 1


if __name__ == "__main__":
    sys.exit(main())