"""tls_search.py period_min/max sanity check duzeltmesi."""

from pathlib import Path
import shutil

project_root = Path(__file__).resolve().parent.parent
tls_file = project_root / "astrotransit" / "detection" / "tls_search.py"


def main():
    if not tls_file.exists():
        print("HATA: tls_search.py bulunamadi")
        return 1

    shutil.copy(tls_file, tls_file.with_suffix(".py.backup"))
    print(f"OK Yedek: {tls_file.name}.backup")

    content = tls_file.read_text(encoding="utf-8")

    old_block = """        # ── Periyot arama penceresi ──
        period_min = bls_peak.period * (1.0 - self.period_search_window)
        period_max = bls_peak.period * (1.0 + self.period_search_window)

        # Sınırları makul aralıkta tut
        period_min = max(period_min, 0.1)
        period_max = min(period_max, (time[-1] - time[0]) / 2.0)"""

    new_block = """        # ── Periyot arama penceresi (güvenli) ──
        bls_p = bls_peak.period
        if bls_p <= 0:
            logger.error(f"BLS periyodu gecersiz: {bls_p}")
            return self._failed_result(target_id, sector, "invalid BLS period")

        period_min = bls_p * (1.0 - self.period_search_window)
        period_max = bls_p * (1.0 + self.period_search_window)

        # Sinirlari makul aralikta tut
        period_min = max(period_min, 0.1)

        # Gozlem penceresine gore period_max ust siniri
        obs_duration = float(time[-1] - time[0])
        max_by_obs = obs_duration / 2.0 if obs_duration > 0 else 100.0
        period_max = min(period_max, max_by_obs)

        # period_min >= period_max ise pencereyi geniş tut
        if period_min >= period_max:
            logger.warning(
                f"period_min ({period_min:.4f}) >= period_max ({period_max:.4f}). "
                f"BLS P={bls_p:.4f}, obs={obs_duration:.2f}d. Genis pencere kullanilacak."
            )
            period_min = max(0.1, bls_p * 0.5)
            period_max = min(max_by_obs, bls_p * 1.5)

            if period_min >= period_max:
                logger.error("Duzeltme sonrasi hala gecersiz. TLS atlanacak.")
                return self._failed_result(target_id, sector, "period range invalid")"""

    if old_block in content:
        content = content.replace(old_block, new_block)
        print("OK period_min/max sanity check eklendi")
        tls_file.write_text(content, encoding="utf-8")
        return 0
    else:
        print("UYARI Eski blok bulunamadi")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())