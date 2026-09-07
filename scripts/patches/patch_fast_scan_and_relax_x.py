"""
Pilot tam tarama için iki düzeltme yapar:

1. cascade.py:
   - TLS'i 3 BLS adayi yerine sadece 1 adayda calistirir
   - boylece hiz artar

2. scorer.py:
   - physical_consistency bayraklarini Class X'e tasimayi durdurur
   - yani "BLS_SNR vs TLS_SDE tutarsiz" gibi durumlar
     Class X yapmaz, sadece skor etkisi olarak kalir
"""

from pathlib import Path
import shutil
import ast

project_root = Path(__file__).resolve().parent.parent

cascade_file = project_root / "astrotransit" / "detection" / "cascade.py"
scorer_file = project_root / "astrotransit" / "quality" / "scorer.py"


def patch_cascade():
    if not cascade_file.exists():
        print("HATA: cascade.py bulunamadi")
        return False

    shutil.copy(cascade_file, cascade_file.with_suffix(".py.fastscan_backup"))
    content = cascade_file.read_text(encoding="utf-8")

    changed = False

    # 1) 3 aday -> 1 aday
    old = "candidates_to_try = passed_peaks[:3]"
    new = "candidates_to_try = passed_peaks[:1]  # hizli tarama modu: sadece en iyi BLS adayi"
    if old in content:
        content = content.replace(old, new)
        print("OK cascade: TLS aday sayisi 3 -> 1")
        changed = True

    # 2) log satiri daha anlamli olsun
    old_log = 'f"BLS: {len(candidates_to_try)} aday TLS ile denenecek"'
    new_log = 'f"BLS: {len(candidates_to_try)} aday TLS ile denenecek (hizli mod)"'
    if old_log in content:
        content = content.replace(old_log, new_log)
        print("OK cascade: hizli mod log satiri guncellendi")
        changed = True

    if changed:
        cascade_file.write_text(content, encoding="utf-8")

    # syntax check
    ast.parse(cascade_file.read_text(encoding="utf-8"))
    return True


def patch_scorer():
    if not scorer_file.exists():
        print("HATA: scorer.py bulunamadi")
        return False

    shutil.copy(scorer_file, scorer_file.with_suffix(".py.relaxx_backup"))
    content = scorer_file.read_text(encoding="utf-8")

    changed = False

    # physical flags'i anomaly'ye tasiyan blok
    old_block = """        # Fiziksel tutarsizlik da anomali sayilir
        try:
            _, physical_flags = self._compute_physical_consistency_score(candidate, None)
            flags.extend(physical_flags)
        except Exception:
            pass

        is_anomalous = len(flags) > 0
        return is_anomalous, flags"""

    new_block = """        # Fiziksel tutarsizliklar skor cezasina katkida bulunur,
        # fakat tek basina Class X uretmez.
        # Class X sadece gercekten siradisi olaylar icin kalmali.
        is_anomalous = len(flags) > 0
        return is_anomalous, flags"""

    if old_block in content:
        content = content.replace(old_block, new_block)
        print("OK scorer: physical flags artik Class X uretmiyor")
        changed = True
    else:
        # blok biraz farkliysa daha yumusak kontrol
        alt_old = """        try:
            _, physical_flags = self._compute_physical_consistency_score(candidate, None)
            flags.extend(physical_flags)
        except Exception:
            pass

        is_anomalous = len(flags) > 0
        return is_anomalous, flags"""
        if alt_old in content:
            content = content.replace(
                alt_old,
                """        # Fiziksel tutarsizliklar skor cezasina katkida bulunur,
        # fakat tek basina Class X uretmez.
        is_anomalous = len(flags) > 0
        return is_anomalous, flags"""
            )
            print("OK scorer: alternate physical flag blogu temizlendi")
            changed = True

    if changed:
        scorer_file.write_text(content, encoding="utf-8")

    # syntax check
    ast.parse(scorer_file.read_text(encoding="utf-8"))
    return True


def main():
    print("=" * 64)
    print("  Fast Scan + Relaxed Class X Patch")
    print("=" * 64)

    ok1 = patch_cascade()
    ok2 = patch_scorer()

    print()
    if ok1 and ok2:
        print("BASARILI")
        print()
        print("Sonraki adimlar:")
        print("  1) Cache temizle")
        print("  2) 5 hedef mini test")
        print("  3) 100 hedef pilot tarama")
        return 0
    else:
        print("Bazi patchler uygulanamadi")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())