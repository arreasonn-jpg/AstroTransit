"""
Dashboard app.py dosyasindan BOM karakterini kaldirir.
UTF-8 BOM (U+FEFF) karakteri Python tarafindan syntax hatasi verir.
"""

from pathlib import Path
import sys

project_root = Path(__file__).resolve().parent.parent


def main():
    print("=" * 60)
    print("  BOM Karakter Temizleme")
    print("=" * 60)

    dashboard_file = project_root / "dashboard" / "app.py"

    if not dashboard_file.exists():
        print("HATA: dashboard/app.py bulunamadi")
        return 1

    # Ham byte okuma
    with open(dashboard_file, "rb") as f:
        raw = f.read()

    # BOM kontrolu
    bom = b'\xef\xbb\xbf'

    if raw.startswith(bom):
        print("OK BOM bulundu, temizleniyor...")
        clean = raw[len(bom):]

        # Ayrica basindaki UTF-8 declaration'i da temizle (bozuk olabilir)
        text = clean.decode("utf-8", errors="replace")
        lines = text.split("\n")

        # Bozuk declaration satirini kaldir
        if lines[0].strip().startswith("# -*- coding"):
            lines = lines[1:]
            print("OK Bozuk encoding declaration temizlendi")

        clean_text = "\n".join(lines)

        # BOM'suz UTF-8 olarak yaz
        with open(dashboard_file, "w", encoding="utf-8") as f:
            f.write(clean_text)

        print(f"OK Temiz UTF-8 olarak kaydedildi: {dashboard_file}")
    else:
        print("BILGI BOM bulunamadi, dosya temiz")

    # Kontrol
    print("\n-- Sozdizim kontrolu --")
    try:
        import ast
        content = dashboard_file.read_text(encoding="utf-8")
        ast.parse(content)
        print("OK Python sozdizimi gecerli")
    except SyntaxError as e:
        print(f"FAIL Sozdizim hatasi: {e}")
        return 1

    print()
    print("Simdi tekrar dene:")
    print("  streamlit run dashboard/app.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())