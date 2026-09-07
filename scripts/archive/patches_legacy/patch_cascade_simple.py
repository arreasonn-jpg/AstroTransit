"""
Cascade'de TLS periyodunu asla kabul etme.
BLS'in bulduguna guven, TLS sadece parametre rafinasyonu.

Bu WASP-19b gibi TLS'in yanildigi durumları cozer.
"""

from pathlib import Path
import shutil

project_root = Path(__file__).resolve().parent.parent
cascade_file = project_root / "astrotransit" / "detection" / "cascade.py"


def main():
    if not cascade_file.exists():
        print("HATA: cascade.py bulunamadi")
        return 1

    shutil.copy(cascade_file, cascade_file.with_suffix(".py.simple_backup"))
    print("OK Yedek: cascade.py.simple_backup")

    content = cascade_file.read_text(encoding="utf-8")

    # ADIM 4: Aday Onayi bloğunu bul
    # Su anda TLS periyodunu aliyor - degistir
    old_parts = [
        '        candidate = CascadeCandidate(',
        '            target_id=target_id,',
        '            sector=sector,',
        '            status=CascadeStatus.CONFIRMED,',
        '            confirmed=True,',
        '            bls_result=bls_result,',
        '            tls_result=tls_result,',
        '            period=tls_result.period,',
        '            period_err=tls_result.period_err,',
        '            t0=tls_result.t0,',
        '            duration=tls_result.duration,',
        '            depth=tls_result.depth,',
        '            rp_rs=tls_result.rp_rs,',
        '            snr=tls_result.snr,',
        '            sde=tls_result.sde,',
        '            transit_times=tls_result.transit_times,',
        '            decision_log=log,',
        '        )',
    ]
    old_block = "\n".join(old_parts)

    new_parts = [
        '        # BLS periyoduna oncelik ver (TLS yaniltabilir)',
        '        # TLS sadece derinlik, sure, rp_rs, sde icin kullanilir',
        '        final_period = bls_peak.period',
        '        final_period_err = bls_peak.period_err',
        '        final_t0 = bls_peak.t0  # BLS T0',
        '',
        '        # Ancak TLS BLS periyoduna yakin bulmussa TLS parametrelerini kullan',
        '        rel_diff_p = abs(tls_result.period - bls_peak.period) / bls_peak.period if bls_peak.period > 0 else 1.0',
        '        if rel_diff_p < 0.05:  # %5 icinde ise TLS refine',
        '            final_period = tls_result.period',
        '            final_period_err = tls_result.period_err',
        '            final_t0 = tls_result.t0',
        '            log.append(f"TLS periyodu kabul edildi (fark %{rel_diff_p*100:.2f})")',
        '        else:',
        '            log.append(',
        '                f"TLS periyodu {tls_result.period:.4f}d, BLS {bls_peak.period:.4f}d "',
        '                f"(fark %{rel_diff_p*100:.1f}) - BLS korundu"',
        '            )',
        '',
        '        candidate = CascadeCandidate(',
        '            target_id=target_id,',
        '            sector=sector,',
        '            status=CascadeStatus.CONFIRMED,',
        '            confirmed=True,',
        '            bls_result=bls_result,',
        '            tls_result=tls_result,',
        '            period=final_period,',
        '            period_err=final_period_err,',
        '            t0=final_t0,',
        '            duration=tls_result.duration,',
        '            depth=tls_result.depth,',
        '            rp_rs=tls_result.rp_rs,',
        '            snr=tls_result.snr,',
        '            sde=tls_result.sde,',
        '            transit_times=tls_result.transit_times if rel_diff_p < 0.05 else bls_peak.transit_times,',
        '            decision_log=log,',
        '        )',
    ]
    new_block = "\n".join(new_parts)

    if old_block in content:
        content = content.replace(old_block, new_block)
        print("OK Cascade CONFIRMED blogu BLS'e oncelik veriyor")
    else:
        print("UYARI CONFIRMED blogu bulunamadi")
        return 1

    # Ayni sekilde _check_period_agreement daha esnek olsun
    # Su anda %2 tolerans, %10 yapalim
    old_tolerance_parts = [
        '        if best_rel_diff < self.thresholds.period_tolerance:',
    ]
    old_tolerance = "\n".join(old_tolerance_parts)

    new_tolerance_parts = [
        '        # Periyot toleransi arttirildi cunku TLS yaniltabilir',
        '        # Bu asamada sadece "periyot yakin mi" kontrol edilir',
        '        effective_tolerance = max(self.thresholds.period_tolerance, 0.10)',
        '        if best_rel_diff < effective_tolerance:',
    ]
    new_tolerance = "\n".join(new_tolerance_parts)

    if old_tolerance in content:
        content = content.replace(old_tolerance, new_tolerance)
        print("OK Periyot toleransi %10 e cikarildi")

    cascade_file.write_text(content, encoding="utf-8")

    try:
        import ast
        ast.parse(cascade_file.read_text(encoding="utf-8"))
        print("OK Python sozdizimi gecerli")
        return 0
    except SyntaxError as e:
        print(f"FAIL Sozdizim hatasi: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())