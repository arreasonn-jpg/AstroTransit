"""
mast_client.py'ye retry mekanizmasi ekler.

MAST sunucusu bazen 'Connection aborted' hatasi veriyor.
Otomatik 3 kez tekrar deneme + exponential backoff.
"""

from pathlib import Path
import shutil

project_root = Path(__file__).resolve().parent.parent
mast_file = project_root / "astrotransit" / "data" / "mast_client.py"


def main():
    if not mast_file.exists():
        print("HATA: mast_client.py bulunamadi")
        return 1

    shutil.copy(mast_file, mast_file.with_suffix(".py.retry_backup"))
    print("OK Yedek: mast_client.py.retry_backup")

    content = mast_file.read_text(encoding="utf-8")

    if "def _retry_mast_call" in content:
        print("BILGI Retry mekanizmasi zaten var")
        return 0

    # query_tic_catalog metodunu bul ve degistir
    # Icindeki try/except blogunu retry ile sarmalayalim
    old_block_parts = [
        '        try:',
        '            if tic_id is not None:',
        '                results = Catalogs.query_object(',
        '                    f"TIC {tic_id}",',
        '                    catalog="TIC",',
        '                    radius=radius,',
        '                )',
        '            elif coordinates is not None:',
        '                results = Catalogs.query_region(',
        '                    coordinates,',
        '                    catalog="TIC",',
        '                    radius=radius,',
        '                )',
        '            else:',
        '                raise ValueError("tic_id veya coordinates parametrelerinden biri gereklidir.")',
        '',
        '            logger.info(f"TIC kataloğu sorgulandı: {len(results)} sonuç.")',
        '            return results',
        '',
        '        except Exception as e:',
        '            raise MASTQueryError(f"TIC katalog sorgusu başarısız: {e}") from e',
    ]
    old_block = "\n".join(old_block_parts)

    new_block_parts = [
        '        import time as _time',
        '',
        '        last_error = None',
        '        for attempt in range(3):',
        '            try:',
        '                if tic_id is not None:',
        '                    results = Catalogs.query_object(',
        '                        f"TIC {tic_id}",',
        '                        catalog="TIC",',
        '                        radius=radius,',
        '                    )',
        '                elif coordinates is not None:',
        '                    results = Catalogs.query_region(',
        '                        coordinates,',
        '                        catalog="TIC",',
        '                        radius=radius,',
        '                    )',
        '                else:',
        '                    raise ValueError("tic_id veya coordinates parametrelerinden biri gereklidir.")',
        '',
        '                logger.info(f"TIC kataloğu sorgulandı: {len(results)} sonuç.")',
        '                return results',
        '',
        '            except Exception as e:',
        '                last_error = e',
        '                wait = 2 ** attempt  # 1, 2, 4 saniye',
        '                if attempt < 2:',
        '                    logger.warning(',
        '                        f"TIC katalog denemesi {attempt+1}/3 basarisiz: {e}. "',
        '                        f"{wait}s bekleyip tekrar denenecek..."',
        '                    )',
        '                    _time.sleep(wait)',
        '                else:',
        '                    logger.error(f"TIC katalog 3 deneme sonrasi basarisiz: {e}")',
        '',
        '        raise MASTQueryError(f"TIC katalog sorgusu başarısız: {last_error}") from last_error',
    ]
    new_block = "\n".join(new_block_parts)

    if old_block in content:
        content = content.replace(old_block, new_block)
        mast_file.write_text(content, encoding="utf-8")
        print("OK Retry mekanizmasi query_tic_catalog'a eklendi")

        # Sozdizim kontrol
        try:
            import ast
            ast.parse(mast_file.read_text(encoding="utf-8"))
            print("OK Python sozdizimi gecerli")
            return 0
        except SyntaxError as e:
            print(f"FAIL Sozdizim hatasi: {e}")
            return 1
    else:
        print("UYARI Marker bulunamadi, mast_client.py yapisi degismis olabilir")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())