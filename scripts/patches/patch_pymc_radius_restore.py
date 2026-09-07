from pathlib import Path
import shutil
import ast

project_root = Path(__file__).resolve().parent.parent
pymc_file = project_root / "astrotransit" / "modeling" / "pymc_fit.py"

def main():
    if not pymc_file.exists():
        print("HATA: pymc_fit.py bulunamadi")
        return 1

    backup = pymc_file.with_suffix(".py.radius_restore_backup")
    shutil.copy(pymc_file, backup)
    print(f"OK Yedek: {backup.name}")

    content = pymc_file.read_text(encoding="utf-8")
    changed = False

    old = "                    r=rp_rs,"
    new = "                    r=rp_rs * stellar_radius,"

    if old in content:
        content = content.replace(old, new)
        changed = True
        print("OK exoplanet radius kullanimi geri duzeltildi")
    elif new in content:
        print("BILGI radius satiri zaten dogru")
    else:
        print("UYARI radius satiri bulunamadi")

    if changed:
        pymc_file.write_text(content, encoding="utf-8")
        print("OK Dosya kaydedildi")

    try:
        ast.parse(pymc_file.read_text(encoding="utf-8"))
        print("OK Python sozdizimi gecerli")
        return 0
    except SyntaxError as e:
        print(f"FAIL Sozdizim hatasi: {e}")
        print(f"Geri yukleme: cp {backup} {pymc_file}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
