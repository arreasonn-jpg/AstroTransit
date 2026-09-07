from pathlib import Path
import shutil
import ast

project_root = Path(__file__).resolve().parent.parent
orch_file = project_root / "astrotransit" / "pipelines" / "orchestrator.py"


def main():
    if not orch_file.exists():
        print("HATA: orchestrator.py bulunamadi")
        return 1

    backup = orch_file.with_suffix(".py.finalize_backup")
    shutil.copy(orch_file, backup)
    print(f"OK Yedek: {backup.name}")

    content = orch_file.read_text(encoding="utf-8")
    changed = False

    # ------------------------------------------------------------
    # 1. _finalize metodunu sadece flush/no-op yap
    # ------------------------------------------------------------
    old_finalize = """    def _finalize(self) -> None:
        \"\"\"Çıktıları finalize eder.\"\"\"

        try:
            self._output.export_csv()
        except Exception as e:
            logger.warning(f"CSV export hatası: {e}")"""

    new_finalize = """    def _finalize(self) -> None:
        \"\"\"Ara finalize.

        Shared parquet writer acikken CSV export denenmez.
        CSV export sadece close() sirasinda yapilir.
        \"\"\"

        try:
            self._output.flush()
        except Exception as e:
            logger.warning(f"Ara flush hatasi: {e}")"""

    if old_finalize in content:
        content = content.replace(old_finalize, new_finalize)
        print("OK _finalize artik sadece flush yapiyor")
        changed = True
    elif 'CSV export sadece close() sirasinda yapilir' in content:
        print("BILGI _finalize zaten patchli")
    else:
        print("UYARI _finalize blogu birebir bulunamadi")

    # ------------------------------------------------------------
    # 2. close() icinde export_csv'yi close'dan once cagir
    # ------------------------------------------------------------
    old_close = """    def close(self) -> None:
        \"\"\"Orkestratörü kapatır.\"\"\"

        self._output.close()
        logger.info("AstroTransit Orkestratör kapatıldı.")"""

    new_close = """    def close(self) -> None:
        \"\"\"Orkestratörü kapatır.\"\"\"

        try:
            # once parquet writer'i kapat
            self._output.close()
        finally:
            try:
                # sonra parquet artik tamamlanmis oldugu icin CSV export dene
                self._output.export_csv()
            except Exception as e:
                logger.warning(f"CSV export hatasi: {e}")

        logger.info("AstroTransit Orkestratör kapatıldı.")"""

    if old_close in content:
        content = content.replace(old_close, new_close)
        print("OK close() CSV export icin guncellendi")
        changed = True
    elif "CSV export hatasi" in content and "AstroTransit Orkestratör kapatıldı" in content:
        print("BILGI close() zaten patchli")
    else:
        print("UYARI close() blogu birebir bulunamadi")

    if changed:
        orch_file.write_text(content, encoding="utf-8")
        print("OK Dosya kaydedildi")
    else:
        print("BILGI Degisiklik gerekmedi")

    try:
        ast.parse(orch_file.read_text(encoding="utf-8"))
        print("OK Python sozdizimi gecerli")
        return 0
    except SyntaxError as e:
        print(f"FAIL Sozdizim hatasi: {e}")
        print(f"Geri yukleme: copy {backup} {orch_file}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())