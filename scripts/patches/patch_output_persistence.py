"""
Paylasilan OutputManager'in her run_single sonunda kapanmasini engeller.

Sorun:
- Orchestrator tek bir OutputManager olusturuyor
- TESSPipeline with-context sonunda close() cagiriyor
- close() ortak OutputManager'i kapatiyor
- sonraki hedefte parquet tekrar aciliyor ve onceki veriler kayboluyor

Cozum:
- TESSPipeline kendi OutputManager'ini olusturduysa kapatsin
- Disaridan verildiyse kapatmasin
"""

from pathlib import Path
import shutil
import ast

project_root = Path(__file__).resolve().parent.parent
tess_pipeline_file = project_root / "astrotransit" / "pipelines" / "tess_pipeline.py"


def main():
    if not tess_pipeline_file.exists():
        print("HATA: tess_pipeline.py bulunamadi")
        return 1

    backup = tess_pipeline_file.with_suffix(".py.persistence_backup")
    shutil.copy(tess_pipeline_file, backup)
    print(f"OK Yedek: {backup.name}")

    content = tess_pipeline_file.read_text(encoding="utf-8")
    changed = False

    # -----------------------------------------------------------------
    # 1. __init__ icinde ownership flag ekle
    # -----------------------------------------------------------------
    old_line = "        self._output = output_manager or OutputManager(settings=settings)"
    new_line = """        self._owns_output_manager = output_manager is None
        self._output = output_manager or OutputManager(settings=settings)"""

    if old_line in content:
        content = content.replace(old_line, new_line)
        print("OK _owns_output_manager eklendi")
        changed = True
    elif "_owns_output_manager" in content:
        print("BILGI _owns_output_manager zaten var")
    else:
        print("UYARI OutputManager satiri bulunamadi")

    # -----------------------------------------------------------------
    # 2. close() metodunu degistir
    # -----------------------------------------------------------------
    old_close = """    def close(self) -> None:
        \"\"\"Pipeline'ı kapatır ve çıktıları finalize eder.\"\"\"

        self._output.close()
        logger.info("TESSPipeline kapatıldı.")"""

    new_close = """    def close(self) -> None:
        \"\"\"Pipeline'ı kapatır ve çıktıları finalize eder.\"\"\"

        if getattr(self, "_owns_output_manager", False):
            self._output.close()
            logger.info("TESSPipeline kapatildi (own output manager kapatildi).")
        else:
            logger.info("TESSPipeline kapatildi (shared output manager korunuyor).")"""

    if old_close in content:
        content = content.replace(old_close, new_close)
        print("OK close() paylasilan output manager'i koruyacak sekilde guncellendi")
        changed = True
    elif "shared output manager korunuyor" in content:
        print("BILGI close() zaten patchlenmis")
    else:
        print("UYARI close() blogu birebir bulunamadi")

    if changed:
        tess_pipeline_file.write_text(content, encoding="utf-8")
        print("OK Dosya kaydedildi")
    else:
        print("BILGI Degisiklik gerekmedi")

    # syntax check
    try:
        ast.parse(tess_pipeline_file.read_text(encoding="utf-8"))
        print("OK Python sozdizimi gecerli")
        return 0
    except SyntaxError as e:
        print(f"FAIL Sozdizim hatasi: {e}")
        print(f"Geri yukleme: copy {backup} {tess_pipeline_file}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())