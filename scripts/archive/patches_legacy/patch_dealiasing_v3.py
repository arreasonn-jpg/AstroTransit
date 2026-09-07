"""
Dealiasing v3: TLS icin manuel period_grid kullan.

TLS period_min/period_max parametrelerini bazi
durumlarda dikkate almiyor. Bunun yerine dogrudan
period_grid array'i veriyoruz.
"""

from pathlib import Path
import shutil

project_root = Path(__file__).resolve().parent.parent
tls_file = project_root / "astrotransit" / "detection" / "tls_search.py"


def main():
    if not tls_file.exists():
        print("HATA: tls_search.py bulunamadi")
        return 1

    shutil.copy(tls_file, tls_file.with_suffix(".py.dealias_v3_backup"))
    print("OK Yedek: tls_search.py.dealias_v3_backup")

    content = tls_file.read_text(encoding="utf-8")

    # Eski dealiasing TLS cagrisini bul
    old_parts = [
        '            tls_half = model.power(',
        '                period_min=p_min,',
        '                period_max=p_max,',
        '                oversampling_factor=self.oversampling_factor,',
        '                transit_template=self.transit_template,',
        '                use_threads=1,',
        '                R_star=r_star,',
        '                R_star_min=max(0.1, r_star * 0.5),',
        '                R_star_max=r_star * 1.5,',
        '                M_star=m_star,',
        '                M_star_min=max(0.1, m_star * 0.5),',
        '                M_star_max=m_star * 1.5,',
        '            )',
    ]
    old_block = "\n".join(old_parts)

    # Yeni: manuel period_grid ile
    new_parts = [
        '            # TLS period_min/max bazen yok sayiliyor.',
        '            # Bunun yerine manuel period_grid veriyoruz.',
        '            n_grid = 500  # dar araligi yogun tara',
        '            manual_grid = np.linspace(p_min, p_max, n_grid)',
        '',
        '            tls_half = model.power(',
        '                period_grid=manual_grid,',
        '                oversampling_factor=self.oversampling_factor,',
        '                transit_template=self.transit_template,',
        '                use_threads=1,',
        '                R_star=r_star,',
        '                R_star_min=max(0.1, r_star * 0.5),',
        '                R_star_max=r_star * 1.5,',
        '                M_star=m_star,',
        '                M_star_min=max(0.1, m_star * 0.5),',
        '                M_star_max=m_star * 1.5,',
        '            )',
    ]
    new_block = "\n".join(new_parts)

    if old_block in content:
        content = content.replace(old_block, new_block)
        print("OK Dealiasing manuel period_grid kullaniyor")
    else:
        print("UYARI Eski TLS cagrisi bulunamadi")

    # Ayrica karar mantigini iyilestir
    # Su anda: half_sde >= current_sde * 0.5
    # Bu cok gevsek. Daha katı olsun ve farklı yönde olduğunu doğrulasın.
    old_decision_parts = [
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
    old_decision = "\n".join(old_decision_parts)

    new_decision_parts = [
        '            # KARAR: P/2 gercekten farkli ve iyi mi?',
        '            # 1. P/2 gercekten P/2 civarinda mi? (TLS bazen aynisini bulur)',
        '            # 2. P/2 dp_ratio fiziksel araliktla olmali',
        '            # 3. P/2 SDE yeterli olmali',
        '            expected_half = current_p / 2.0',
        '            half_diff_pct = abs(half_period - expected_half) / expected_half * 100',
        '            actually_half = half_diff_pct < 5.0  # gercekten P/2 mi?',
        '',
        '            half_ratio_ok = 0.01 <= half_dp_ratio <= 0.20',
        '            sde_ok = half_sde >= current_result.sde * 0.50',
        '',
        '            logger.debug(',
        '                f"Karar: actually_half={actually_half} "',
        '                f"(bulunan {half_period:.4f} vs beklenen {expected_half:.4f}, "',
        '                f"fark %{half_diff_pct:.1f}), "',
        '                f"half_ratio_ok={half_ratio_ok}, sde_ok={sde_ok}"',
        '            )',
        '',
        '            if actually_half and half_ratio_ok and sde_ok:',
    ]
    new_decision = "\n".join(new_decision_parts)

    if old_decision in content:
        content = content.replace(old_decision, new_decision)
        print("OK Karar mantigi P/2 dogrulama ekledi")
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