"""schemas.py — cascade_confirmed=False durumunda skor otomatik dusurulur."""

from pathlib import Path
import shutil

project_root = Path(__file__).resolve().parent.parent
schemas_file = project_root / "astrotransit" / "outputs" / "schemas.py"


def main():
    if not schemas_file.exists():
        print("HATA: schemas.py bulunamadi")
        return 1

    shutil.copy(schemas_file, schemas_file.with_suffix(".py.backup"))
    print(f"OK Yedek: {schemas_file.name}.backup")

    content = schemas_file.read_text(encoding="utf-8")

    # Kalite metrikleri bloğunun sonuna cascade tutarlilik kontrolü ekle
    old_end = """        rec.total_score = score.total_score
        rec.candidate_class = score.candidate_class.value
        rec.is_anomalous = score.is_anomalous
        rec.anomaly_flags = " | ".join(score.anomaly_flags)"""

    new_end = """        rec.total_score = score.total_score
        rec.candidate_class = score.candidate_class.value
        rec.is_anomalous = score.is_anomalous
        rec.anomaly_flags = " | ".join(score.anomaly_flags)

        # ── Cascade tutarlilik kontrolu ──
        # Cascade onaylamamissa skoru otomatik dusur, sinifi C/D yap
        if not candidate.confirmed:
            # Skoru en fazla 50/100 yap
            rec.total_score = min(rec.total_score, 50.0)

            # Sinifi durum bazli belirle
            from astrotransit.detection.cascade import CascadeStatus
            if candidate.status == CascadeStatus.PERIOD_MISMATCH:
                rec.candidate_class = "C"  # Şüpheli
            elif candidate.status == CascadeStatus.TLS_FAILED:
                rec.candidate_class = "C"
            elif candidate.status == CascadeStatus.BLS_ONLY:
                rec.candidate_class = "C"
            elif candidate.status == CascadeStatus.BLS_FAILED:
                rec.candidate_class = "D"
            elif candidate.status == CascadeStatus.ERROR:
                rec.candidate_class = "D"

        # ── Fiziksel tutarlilik kontrolu ──
        # Rp cok buyukse (> 30 R_earth = ~2.7 R_jup) supheli
        if rec.planet_radius_rearth > 30.0:
            rec.total_score = min(rec.total_score, 40.0)
            if rec.candidate_class in ("A", "B"):
                rec.candidate_class = "C"
            if rec.anomaly_flags:
                rec.anomaly_flags += " | "
            rec.anomaly_flags += f"Fiziksel disi yaricap: {rec.planet_radius_rearth:.1f} R_earth"

        # BLS bulundu ama fit yapilmadi (period=0) durumu
        if rec.period <= 0 and candidate.period > 0:
            rec.period = candidate.period
            rec.period_err = candidate.period_err"""

    if old_end in content:
        content = content.replace(old_end, new_end)
        print("OK Cascade tutarlilik kontrolu eklendi")
        schemas_file.write_text(content, encoding="utf-8")
        return 0
    else:
        print("UYARI Eski blok bulunamadi")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())