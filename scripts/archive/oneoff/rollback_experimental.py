"""
Deneysel patch'leri geri alir, kararli sistemi geri yukler.

Korunacak:
- Katı skorlama (patch_scorer_strict, patch_scorer_component,
                 patch_scorer_penalties)
- Reality check (patch_batch_reality_check)
- MAST retry (patch_mast_retry)

Geri alinacak:
- Multi-mode TLS (yaniltici)
- Diverse peaks (WASP-18b'yi bozdu)
- Dealiasing (calisttmadi)
- Cascade simple (BLS/TLS dengesini bozdu)
"""

from pathlib import Path
import shutil
import sys

project_root = Path(__file__).resolve().parent.parent


def restore_from_backup(target_file: Path, backup_suffix: str):
    """Yedekten geri yukle."""
    backup = target_file.with_suffix(f".py.{backup_suffix}")
    if not backup.exists():
        print(f"UYARI Yedek bulunamadi: {backup.name}")
        return False

    shutil.copy(backup, target_file)
    print(f"OK Geri yuklendi: {target_file.name} <- {backup.name}")
    return True


def main():
    print("=" * 70)
    print("  Kararli Surume Geri Donus")
    print("=" * 70)

    # Cascade: multimode oncesine don
    cascade = project_root / "astrotransit" / "detection" / "cascade.py"
    restore_from_backup(cascade, "multimode_backup")

    # TLS: multimode oncesine don
    tls = project_root / "astrotransit" / "detection" / "tls_search.py"
    restore_from_backup(tls, "multimode_backup")

    # BLS: diverse peaks oncesine don
    bls = project_root / "astrotransit" / "detection" / "bls_search.py"
    restore_from_backup(bls, "diverse_backup")

    print()
    print("KORUNAN OZELLIKLER:")
    print("  - Kati skorlama sistemi")
    print("  - Fiziksel tutarlilik kontrolu")
    print("  - Reality check (BILIMSEL DOGRU raporlamasi)")
    print("  - MAST retry mekanizmasi")
    print()
    print("GERI ALINAN OZELLIKLER:")
    print("  - TLS multi-mode arama")
    print("  - BLS diverse peaks")
    print("  - Harmonic dealiasing")
    print("  - Cascade BLS-oncelikli mantik")
    print()
    print("Kararli surum aktif. Simdi test edin:")
    print("  python scripts/run_batch_test.py --quick --no-viz")

    return 0


if __name__ == "__main__":
    sys.exit(main())