from pathlib import Path
import shutil
import ast

project_root = Path(__file__).resolve().parent.parent
tess_file = project_root / "astrotransit" / "data" / "tess_client.py"


def main():
    if not tess_file.exists():
        print("HATA: tess_client.py bulunamadi")
        return 1

    backup = tess_file.with_suffix(".py.search_retry_backup")
    shutil.copy(tess_file, backup)
    print(f"OK Yedek: {backup.name}")

    content = tess_file.read_text(encoding="utf-8")
    changed = False

    old_block = """        try:
            search_result = lk.search_lightcurve(
                target_str,
                mission="TESS",
                author=self.author,
                exptime=self.exptime,
                sector=sector,
            )
        except Exception as e:
            raise TESSDataError(f"TESS araması başarısız: {e}") from e"""

    new_block = """        import time as _time

        last_error = None
        search_result = None

        for attempt in range(3):
            try:
                search_result = lk.search_lightcurve(
                    target_str,
                    mission="TESS",
                    author=self.author,
                    exptime=self.exptime,
                    sector=sector,
                )
                break
            except Exception as e:
                last_error = e
                wait = 2 ** attempt  # 1, 2, 4 saniye
                if attempt < 2:
                    logger.warning(
                        f"TESS arama denemesi {attempt+1}/3 başarısız: {e}. "
                        f"{wait}s bekleyip tekrar denenecek..."
                    )
                    _time.sleep(wait)
                else:
                    raise TESSDataError(f"TESS araması başarısız: {e}") from e"""

    if old_block in content:
        content = content.replace(old_block, new_block)
        print("OK TESS search retry eklendi")
        changed = True
    else:
        print("UYARI Aranan blok bulunamadi (belki zaten patchli)")

    if changed:
        tess_file.write_text(content, encoding="utf-8")
        print("OK Dosya kaydedildi")

    try:
        ast.parse(tess_file.read_text(encoding="utf-8"))
        print("OK Python sozdizimi gecerli")
        return 0
    except SyntaxError as e:
        print(f"FAIL Sozdizim hatasi: {e}")
        print(f"Geri yukleme: copy {backup} {tess_file}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())