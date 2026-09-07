"""
Dealiasing'i her durumda calistir.

Onceki versiyonda dp_ratio > 0.03 ise atlaniyordu.
Bu WASP-19b gibi vakalarda hatali. TLS 1.56d bulunca
dp_ratio 0.06 ciktigi icin dealiasing atlandi.

Yeni mantik: Her durumda P/2 test et, kararla sec.
"""

from pathlib import Path
import shutil

project_root = Path(__file__).resolve().parent.parent
tls_file = project_root / "astrotransit" / "detection" / "tls_search.py"


def main():
    if not tls_file.exists():
        print("HATA: tls_search.py bulunamadi")
        return 1

    shutil.copy(tls_file, tls_file.with_suffix(".py.dealias_v2_backup"))
    print("OK Yedek: tls_search.py.dealias_v2_backup")

    content = tls_file.read_text(encoding="utf-8")

    # Eski dp_ratio kontrol blogunu bul ve degistir
    old_parts = [
        '        # Duration/Period orani',
        '        dp_ratio = current_dur / current_p if current_p > 0 else 0',
        '',
        '        # Zaten normal ise dealiasing gereksiz',
        '        # Sicak Jupiter: 0.04-0.10 arasi normaldir',
        '        if dp_ratio > 0.03:',
        '            return None',
        '',
        '        # dp_ratio cok kucuk - 2P harmonigi supheli',
    ]
    old_block = "\n".join(old_parts)

    new_parts = [
        '        # Duration/Period orani (bilgi amacli)',
        '        dp_ratio = current_dur / current_p if current_p > 0 else 0',
        '',
        '        # HER DURUMDA P/2 test et - karar sonrasi kalite ile verilir',
        '        # WASP-19b gibi vakalarda dp_ratio normal gorunse bile',
        '        # gercek periyot yarisidir. Test etmeden anlayamayiz.',
    ]
    new_block = "\n".join(new_parts)

    if old_block in content:
        content = content.replace(old_block, new_block)
        print("OK Dealiasing kosulsuz hale getirildi")
    else:
        print("UYARI Eski dp_ratio blogu bulunamadi")

    # Ayrica karar mantigini gelistir:
    # SDE en az %60 yerine daha esnek karar
    old_decision_parts = [
        '            # KARAR: P/2 daha iyi mi?',
        '            # 1. P/2 dp_ratio normal aralikta olmali (0.03-0.15)',
        '            # 2. P/2 SDE mevcut SDE nin en az %60 i olmali',
        '            half_ratio_ok = 0.03 <= half_dp_ratio <= 0.15',
        '            sde_ok = half_sde >= current_result.sde * 0.60',
        '',
        '            if half_ratio_ok and sde_ok:',
    ]
    old_decision = "\n".join(old_decision_parts)

    new_decision_parts = [
        '            # KARAR: P/2 daha iyi mi?',
        '            # 1. P/2 dp_ratio fiziksel araliktla olmali (0.01-0.20)',
        '            # 2. P/2 SDE mevcut SDE nin en az %50 si olmali',
        '            # 3. current dp_ratio cok kucukse (< 0.02) - siddetli 2P supheli',
        '            #    Bu durumda P/2 sadece SDE %40 olmali',
        '            half_ratio_ok = 0.01 <= half_dp_ratio <= 0.20',
        '',
        '            if dp_ratio < 0.02:',
        '                # Siddetli 2P supheli - dusuk esik',
        '                sde_threshold = current_result.sde * 0.40',
        '            else:',
        '                # Normal esik',
        '                sde_threshold = current_result.sde * 0.50',
        '',
        '            sde_ok = half_sde >= sde_threshold',
        '',
        '            logger.debug(',
        '                f"Karar: half_ratio_ok={half_ratio_ok}, "',
        '                f"sde_ok={sde_ok} ({half_sde:.2f} >= {sde_threshold:.2f}?)"',
        '            )',
        '',
        '            if half_ratio_ok and sde_ok:',
    ]
    new_decision = "\n".join(new_decision_parts)

    if old_decision in content:
        content = content.replace(old_decision, new_decision)
        print("OK Karar mantigi iyilestirildi")
    else:
        print("UYARI Karar blogu bulunamadi")

    tls_file.write_text(content, encoding="utf-8")

    # Sozdizim kontrol
    try:
        import ast
        ast.parse(tls_file.read_text(encoding="utf-8"))
        print("OK Python sozdizimi gecerli")
        return 0
    except SyntaxError as e:
        print(f"FAIL Sozdizim hatasi: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())