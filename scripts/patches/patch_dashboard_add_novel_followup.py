from pathlib import Path
import shutil
import ast

project_root = Path(__file__).resolve().parent.parent
dashboard_file = project_root / "dashboard" / "app.py"


def main():
    if not dashboard_file.exists():
        print("HATA: dashboard/app.py bulunamadi")
        return 1

    backup = dashboard_file.with_suffix(".py.novel_backup")
    shutil.copy(dashboard_file, backup)
    print(f"OK Yedek: {backup.name}")

    content = dashboard_file.read_text(encoding="utf-8")
    changed = False

    # JSON roots genişlet
    old = 'roots = [Path("outputs/json"), Path("outputs_top10/json"), Path("outputs_wsl_mcmc/json")]'
    new = 'roots = [Path("outputs/json"), Path("outputs_top10/json"), Path("outputs_wsl_mcmc/json"), Path("outputs_novel_followup/json"), Path("outputs_novel_mcmc/json")]'
    if old in content:
        content = content.replace(old, new)
        print("OK dashboard json roots novel klasorlerle genisletildi")
        changed = True
    elif "outputs_novel_followup/json" in content:
        print("BILGI json roots zaten patchli")

    # Figure roots genişlet
    old = """    roots = [
        Path("outputs/figures"),
        Path("outputs_top10/figures"),
        Path("outputs_wsl_mcmc/figures"),
    ]"""
    new = """    roots = [
        Path("outputs/figures"),
        Path("outputs_top10/figures"),
        Path("outputs_wsl_mcmc/figures"),
        Path("outputs_novel_followup/figures"),
        Path("outputs_novel_mcmc/figures"),
    ]"""
    if old in content:
        content = content.replace(old, new)
        print("OK dashboard figure roots novel klasorlerle genisletildi")
        changed = True
    elif "outputs_novel_followup/figures" in content:
        print("BILGI figure roots zaten patchli")

    if changed:
        dashboard_file.write_text(content, encoding="utf-8")
        print("OK dashboard kaydedildi")
    else:
        print("BILGI dashboard icin degisiklik gerekmedi")

    ast.parse(dashboard_file.read_text(encoding="utf-8"))
    print("OK Python sozdizimi gecerli")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())