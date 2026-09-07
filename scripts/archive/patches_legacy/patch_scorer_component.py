"""
scorer.py score() metoduna eksik physical_consistency
components.append cagrisini ekler.
"""

from pathlib import Path
import shutil

project_root = Path(__file__).resolve().parent.parent
scorer_file = project_root / "astrotransit" / "quality" / "scorer.py"


def main():
    if not scorer_file.exists():
        print("HATA: scorer.py bulunamadi")
        return 1

    shutil.copy(scorer_file, scorer_file.with_suffix(".py.component_backup"))
    print(f"OK Yedek: scorer.py.component_backup")

    content = scorer_file.read_text(encoding="utf-8")

    # Kontrol: zaten var mi?
    if 'name="physical_consistency"' in content:
        print("BILGI physical_consistency zaten score() icinde")
        return 0

    # period_consistency ScoreComponent'inden sonra ekle
    marker = """components.append(ScoreComponent(
            name="period_consistency",
            raw_value=self._compute_period_relative_diff(candidate),
            score=period_consistency_score,
            weight=self.WEIGHTS["period_consistency"],
            contribution=period_consistency_score * self.WEIGHTS["period_consistency"],
        ))"""

    new_addition = marker + """

        # -- Bilesen 7: Fiziksel Tutarlilik --
        physical_score, physical_flags = self._compute_physical_consistency_score(
            candidate, fit_result
        )
        components.append(ScoreComponent(
            name="physical_consistency",
            raw_value=float(len(physical_flags)),
            score=physical_score,
            weight=self.WEIGHTS["physical_consistency"],
            contribution=physical_score * self.WEIGHTS["physical_consistency"],
        ))"""

    if marker in content:
        content = content.replace(marker, new_addition)
        scorer_file.write_text(content, encoding="utf-8")
        print("OK physical_consistency components.append eklendi")

        # Doğrula
        final = scorer_file.read_text(encoding="utf-8")
        if 'name="physical_consistency"' in final:
            print("OK Dogrulama basarili")
            return 0
        else:
            print("FAIL Dogrulama basarisiz")
            return 1
    else:
        print("HATA: period_consistency ScoreComponent bulunamadi")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())