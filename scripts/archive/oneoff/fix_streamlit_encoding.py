"""
Streamlit UTF-8 encoding sorununu duzeltir.
Turkce karakterler bozuk gorunuyorsa bu betik cozer.
"""

from pathlib import Path
import sys

project_root = Path(__file__).resolve().parent.parent


def main():
    print("=" * 60)
    print("  Streamlit UTF-8 Encoding Duzeltmesi")
    print("=" * 60)

    # 1. Streamlit config klasoru
    streamlit_dir = project_root / ".streamlit"
    streamlit_dir.mkdir(exist_ok=True)

    # 2. config.toml olustur
    config_file = streamlit_dir / "config.toml"
    config_content = """[server]
enableCORS = false
enableXsrfProtection = false

[browser]
gatherUsageStats = false

[theme]
base = "dark"
primaryColor = "#3fb950"
backgroundColor = "#0d1117"
secondaryBackgroundColor = "#161b22"
textColor = "#e6edf3"
font = "sans serif"

[logger]
level = "warning"
"""

    config_file.write_text(config_content, encoding="utf-8")
    print(f"OK Streamlit config yazildi: {config_file}")

    # 3. Dashboard app.py basina UTF-8 encoding declaration ekle
    dashboard_file = project_root / "dashboard" / "app.py"

    if not dashboard_file.exists():
        print("HATA: dashboard/app.py bulunamadi")
        return 1

    content = dashboard_file.read_text(encoding="utf-8")

    # Encoding decl kontrolu
    lines = content.split("\n")

    if not lines[0].startswith("# -*- coding: utf-8"):
        # UTF-8 declaration ekle
        new_lines = ["# -*- coding: utf-8 -*-"] + lines
        content = "\n".join(new_lines)
        dashboard_file.write_text(content, encoding="utf-8")
        print("OK UTF-8 declaration eklendi: dashboard/app.py")
    else:
        print("BILGI UTF-8 declaration zaten var")

    # 4. Kullanici icin ortam degisken bilgisi
    print()
    print("EK COZUM (opsiyonel):")
    print("  Streamlit'i baslatirken PYTHONIOENCODING ayarla:")
    print()
    print("  PowerShell:")
    print("    $env:PYTHONIOENCODING = 'utf-8'")
    print("    streamlit run dashboard/app.py")
    print()
    print("Simdi Streamlit'i tekrar baslatin:")
    print("    streamlit run dashboard/app.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())