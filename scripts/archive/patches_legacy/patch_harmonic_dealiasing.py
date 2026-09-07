"""
Faz 2: Harmonik ayristirma (dealiasing).

WASP-19b gibi vakalarda TLS aliasing nedeniyle 2P bulur.
Cozum: Bulunan periyodun yarisini da dene, hangisi
fiziksel olarak daha tutarli ise onu sec.

Yontem: "Duration/Period" oranini kontrol et.
Kucuk periyot + kucuk oran = fiziksel gecerli.
Yanlis harmonik ise duration/period orani sismis olur.
"""

from pathlib import Path
import shutil

project_root = Path(__file__).resolve().parent.parent
tls_file = project_root / "astrotransit" / "detection" / "tls_search.py"


def main():
    if not tls_file.exists():
        print("HATA: tls_search.py bulunamadi")
        return 1

    shutil.copy(tls_file, tls_file.with_suffix(".py.dealiasing_backup"))
    print("OK Yedek: tls_search.py.dealiasing_backup")

    content = tls_file.read_text(encoding="utf-8")

    if "def _dealias_period" in content:
        print("BILGI Dealiasing zaten uygulanmis")
        return 0

    # ─────────────────────────────────────────────────
    # Eklenecek Python kodu (triple-quote yerine
    # docstring'ler tek satirlik string olarak yaziliyor
    # cunku bu dosyanin kendisi triple-quote iceriyor)
    # ─────────────────────────────────────────────────

    new_code_parts = []

    new_code_parts.append('        logger.info(')
    new_code_parts.append('            f"[BEST] {target_id} S{sector}: {best_mode} secildi - "')
    new_code_parts.append('            f"P={best_result.period:.4f}d, SDE={best_result.sde:.2f}"')
    new_code_parts.append('        )')
    new_code_parts.append('')
    new_code_parts.append('        # HARMONIK AYRISTIRMA (Dealiasing)')
    new_code_parts.append('        # Bulunan periyot 2P harmonigi olabilir. Yarisini test et.')
    new_code_parts.append('        dealiased = self._dealias_period(')
    new_code_parts.append('            best_result, detrended, stellar_radius, stellar_mass')
    new_code_parts.append('        )')
    new_code_parts.append('        if dealiased is not None:')
    new_code_parts.append('            logger.info(')
    new_code_parts.append('                f"[DEALIAS] {target_id} S{sector}: "')
    new_code_parts.append('                f"P={best_result.period:.4f}d -> P={dealiased.period:.4f}d "')
    new_code_parts.append('                f"(fiziksel olarak daha tutarli)"')
    new_code_parts.append('            )')
    new_code_parts.append('            best_result = dealiased')
    new_code_parts.append('            from dataclasses import replace')
    new_code_parts.append('            best_peak = replace(best_peak, period=dealiased.period)')
    new_code_parts.append('')
    new_code_parts.append('        return best_result, best_peak')
    new_code_parts.append('')
    new_code_parts.append('    def _dealias_period(')
    new_code_parts.append('        self,')
    new_code_parts.append('        current_result,')
    new_code_parts.append('        detrended,')
    new_code_parts.append('        stellar_radius: float,')
    new_code_parts.append('        stellar_mass: float,')
    new_code_parts.append('    ):')
    new_code_parts.append('        # Bulunan periyodun 2P harmonigi olup olmadigini kontrol et.')
    new_code_parts.append('        # Duration/Period orani fiziksel olarak makul mu bak.')
    new_code_parts.append('        # Eger cok kucukse, P/2 dogru periyot olabilir.')
    new_code_parts.append('        import numpy as np')
    new_code_parts.append('        from dataclasses import replace')
    new_code_parts.append('')
    new_code_parts.append('        current_p = current_result.period')
    new_code_parts.append('        current_dur = current_result.duration')
    new_code_parts.append('')
    new_code_parts.append('        # Cok kisa periyotlarda dealiasing yapma')
    new_code_parts.append('        if current_p < 0.6:')
    new_code_parts.append('            return None')
    new_code_parts.append('')
    new_code_parts.append('        # Duration/Period orani')
    new_code_parts.append('        dp_ratio = current_dur / current_p if current_p > 0 else 0')
    new_code_parts.append('')
    new_code_parts.append('        # Zaten normal ise dealiasing gereksiz')
    new_code_parts.append('        # Sicak Jupiter: 0.04-0.10 arasi normaldir')
    new_code_parts.append('        if dp_ratio > 0.03:')
    new_code_parts.append('            return None')
    new_code_parts.append('')
    new_code_parts.append('        # dp_ratio cok kucuk - 2P harmonigi supheli')
    new_code_parts.append('        half_p = current_p / 2.0')
    new_code_parts.append('')
    new_code_parts.append('        # Fiziksel makul araligi kontrol et')
    new_code_parts.append('        if half_p < 0.3:')
    new_code_parts.append('            return None')
    new_code_parts.append('')
    new_code_parts.append('        logger.debug(')
    new_code_parts.append('            f"Dealiasing test: current P={current_p:.4f}d "')
    new_code_parts.append('            f"(dp_ratio={dp_ratio:.4f}), testing P/2={half_p:.4f}d"')
    new_code_parts.append('        )')
    new_code_parts.append('')
    new_code_parts.append('        # P/2 icin TLS dar pencere ile calistir')
    new_code_parts.append('        try:')
    new_code_parts.append('            from transitleastsquares import transitleastsquares as _tls')
    new_code_parts.append('')
    new_code_parts.append('            time_arr = detrended.time')
    new_code_parts.append('            flux_arr = detrended.flux')
    new_code_parts.append('            err_arr = detrended.flux_err')
    new_code_parts.append('')
    new_code_parts.append('            r_star = float(stellar_radius)')
    new_code_parts.append('            m_star = float(stellar_mass)')
    new_code_parts.append('')
    new_code_parts.append('            model = _tls(time_arr, flux_arr, err_arr)')
    new_code_parts.append('')
    new_code_parts.append('            # P/2 civarinda %5 pencere')
    new_code_parts.append('            p_min = half_p * 0.95')
    new_code_parts.append('            p_max = half_p * 1.05')
    new_code_parts.append('')
    new_code_parts.append('            tls_half = model.power(')
    new_code_parts.append('                period_min=p_min,')
    new_code_parts.append('                period_max=p_max,')
    new_code_parts.append('                oversampling_factor=self.oversampling_factor,')
    new_code_parts.append('                transit_template=self.transit_template,')
    new_code_parts.append('                use_threads=1,')
    new_code_parts.append('                R_star=r_star,')
    new_code_parts.append('                R_star_min=max(0.1, r_star * 0.5),')
    new_code_parts.append('                R_star_max=r_star * 1.5,')
    new_code_parts.append('                M_star=m_star,')
    new_code_parts.append('                M_star_min=max(0.1, m_star * 0.5),')
    new_code_parts.append('                M_star_max=m_star * 1.5,')
    new_code_parts.append('            )')
    new_code_parts.append('')
    new_code_parts.append('            half_sde = float(tls_half.SDE)')
    new_code_parts.append('            half_period = float(tls_half.period)')
    new_code_parts.append('            half_duration = float(tls_half.duration)')
    new_code_parts.append('            half_dp_ratio = half_duration / half_period if half_period > 0 else 0')
    new_code_parts.append('')
    new_code_parts.append('            logger.debug(')
    new_code_parts.append('                f"P/2 sonuc: P={half_period:.4f}d, "')
    new_code_parts.append('                f"SDE={half_sde:.2f}, dp_ratio={half_dp_ratio:.4f}"')
    new_code_parts.append('            )')
    new_code_parts.append('')
    new_code_parts.append('            # KARAR: P/2 daha iyi mi?')
    new_code_parts.append('            # 1. P/2 dp_ratio normal aralikta olmali (0.03-0.15)')
    new_code_parts.append('            # 2. P/2 SDE mevcut SDE nin en az %60 i olmali')
    new_code_parts.append('            half_ratio_ok = 0.03 <= half_dp_ratio <= 0.15')
    new_code_parts.append('            sde_ok = half_sde >= current_result.sde * 0.60')
    new_code_parts.append('')
    new_code_parts.append('            if half_ratio_ok and sde_ok:')
    new_code_parts.append('                from astrotransit.detection.tls_search import TLSResult')
    new_code_parts.append('')
    new_code_parts.append('                depth_val = float(1.0 - tls_half.depth)')
    new_code_parts.append('                rp_rs_val = (')
    new_code_parts.append('                    float(tls_half.rp_rs) if hasattr(tls_half, "rp_rs")')
    new_code_parts.append('                    else float(np.sqrt(max(0, depth_val)))')
    new_code_parts.append('                )')
    new_code_parts.append('')
    new_code_parts.append('                new_result = TLSResult(')
    new_code_parts.append('                    target_id=current_result.target_id,')
    new_code_parts.append('                    sector=current_result.sector,')
    new_code_parts.append('                    period=half_period,')
    new_code_parts.append('                    period_err=float(tls_half.period_uncertainty),')
    new_code_parts.append('                    t0=float(tls_half.T0),')
    new_code_parts.append('                    duration=half_duration,')
    new_code_parts.append('                    depth=depth_val,')
    new_code_parts.append('                    rp_rs=rp_rs_val,')
    new_code_parts.append('                    sde=half_sde,')
    new_code_parts.append('                    snr=float(tls_half.snr) if hasattr(tls_half, "snr") else 0.0,')
    new_code_parts.append('                    odd_even_mismatch=float(tls_half.odd_even_mismatch),')
    new_code_parts.append('                    transit_count=int(tls_half.transit_count),')
    new_code_parts.append('                    transit_times=np.array(tls_half.transit_times) if hasattr(tls_half, "transit_times") else np.array([]),')
    new_code_parts.append('                    transit_depths=np.array(tls_half.transit_depths) if hasattr(tls_half, "transit_depths") else np.array([]),')
    new_code_parts.append('                    folded_phase=np.array(tls_half.folded_phase) if hasattr(tls_half, "folded_phase") else np.array([]),')
    new_code_parts.append('                    folded_flux=np.array(tls_half.folded_y) if hasattr(tls_half, "folded_y") else np.array([]),')
    new_code_parts.append('                    model_phase=np.array(tls_half.model_folded_phase) if hasattr(tls_half, "model_folded_phase") else np.array([]),')
    new_code_parts.append('                    model_flux=np.array(tls_half.model_folded_model) if hasattr(tls_half, "model_folded_model") else np.array([]),')
    new_code_parts.append('                    false_alarm_probability=float(tls_half.FAP) if hasattr(tls_half, "FAP") else 1.0,')
    new_code_parts.append('                    raw_stats={},')
    new_code_parts.append('                )')
    new_code_parts.append('')
    new_code_parts.append('                new_result = self._evaluate_threshold(new_result)')
    new_code_parts.append('                return new_result')
    new_code_parts.append('')
    new_code_parts.append('        except Exception as e:')
    new_code_parts.append('            logger.debug(f"Dealiasing hatasi: {e}")')
    new_code_parts.append('')
    new_code_parts.append('        return None')
    new_code_parts.append('')
    new_code_parts.append('    def _failed_result(')

    new_code = "\n".join(new_code_parts)

    # Marker: mevcut kod bu bloktan onceydi
    old_marker_parts = [
        '        logger.info(',
        '            f"[BEST] {target_id} S{sector}: {best_mode} secildi - "',
        '            f"P={best_result.period:.4f}d, SDE={best_result.sde:.2f}"',
        '        )',
        '',
        '        return best_result, best_peak',
        '',
        '    def _failed_result(',
    ]
    old_marker = "\n".join(old_marker_parts)

    if old_marker not in content:
        print("HATA: marker bulunamadi")
        print("tls_search.py yapisi degismis olabilir")
        return 1

    content = content.replace(old_marker, new_code)
    tls_file.write_text(content, encoding="utf-8")
    print("OK Dealiasing metodu eklendi")

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