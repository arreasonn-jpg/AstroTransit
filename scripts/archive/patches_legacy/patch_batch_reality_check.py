"""
run_batch_test.py'ye "reality check" katmani ekler.

Pipeline "Sinif A" dese bile:
- Periyot hatasi > %5 -> BASARISIZ
- Rp hatasi > %30 -> BASARISIZ
- Cascade onaylanamamis -> BASARISIZ

Boylece hedefin gercekten dogru bulunup bulunmadigi net gorulur.
"""

from pathlib import Path
import shutil

project_root = Path(__file__).resolve().parent.parent
batch_file = project_root / "scripts" / "run_batch_test.py"


def main():
    if not batch_file.exists():
        print("HATA: run_batch_test.py bulunamadi")
        return 1

    shutil.copy(batch_file, batch_file.with_suffix(".py.reality_backup"))
    print("OK Yedek: run_batch_test.py.reality_backup")

    content = batch_file.read_text(encoding="utf-8")

    # is_scientifically_correct alanini TargetTestResult'e ekle
    old_field = """    # Meta
    elapsed_sec: float = 0.0
    error: str = \"\"
"""

    new_field = """    # Bilimsel dogrulama (batch test tarafindan yapilir)
    is_scientifically_correct: bool = False
    reality_check_reasons: list = None

    # Meta
    elapsed_sec: float = 0.0
    error: str = \"\"

    def __post_init__(self):
        if self.reality_check_reasons is None:
            self.reality_check_reasons = []
"""

    if "is_scientifically_correct" not in content and old_field in content:
        content = content.replace(old_field, new_field)
        print("OK is_scientifically_correct alani eklendi")

    # test_single_target sonuna reality check ekle
    marker = """    result.elapsed_sec = time.time() - t_start

    # Özet çıktı
    if verbose:"""

    new_block = """    result.elapsed_sec = time.time() - t_start

    # === REALITY CHECK - Bilimsel Dogrulama ===
    # Pipeline "basarili" dese bile beklenen degerlerle uyumlu mu?
    reasons = []

    if not result.confirmed:
        reasons.append("cascade onaylanmadi")

    if result.period_error_pct > 5.0:
        reasons.append(f"P hatasi %{result.period_error_pct:.1f} > %5")
    elif result.period_error_pct < 0:
        reasons.append("P hatasi olculemedi")

    if result.radius_error_pct > 30.0 and result.radius_error_pct >= 0:
        reasons.append(f"Rp hatasi %{result.radius_error_pct:.1f} > %30")

    result.reality_check_reasons = reasons
    result.is_scientifically_correct = len(reasons) == 0

    # Özet çıktı
    if verbose:"""

    if "REALITY CHECK" not in content and marker in content:
        content = content.replace(marker, new_block)
        print("OK reality check logic eklendi")

    # Özet çıktıya bilimsel doğruluğu ekle
    old_summary = """        if result.confirmed:
            print(f\"  ✓ ONAYLANDI  |  Sınıf {result.found_class}  |  \"
                  f\"Skor {result.found_score:.0f}/100\")"""

    new_summary = """        # Bilimsel dogruluk
        if result.is_scientifically_correct:
            sci_status = "BILIMSEL: DOGRU"
        else:
            sci_reasons = ", ".join(result.reality_check_reasons)
            sci_status = f"BILIMSEL: HATALI ({sci_reasons})"

        if result.confirmed:
            print(f\"  ✓ ONAYLANDI  |  Sınıf {result.found_class}  |  \"
                  f\"Skor {result.found_score:.0f}/100\")
            print(f\"    {sci_status}\")"""

    if "BILIMSEL:" not in content and old_summary in content:
        content = content.replace(old_summary, new_summary)
        print("OK Ozet ciktiya BILIMSEL etiketi eklendi")

    # Ozet raporda bilimsel dogruluk istatistigi
    old_stats = """    n_success = 0
    n_confirmed = 0
    n_class_a = 0
    n_class_b = 0"""

    new_stats = """    n_success = 0
    n_confirmed = 0
    n_class_a = 0
    n_class_b = 0
    n_scientifically_correct = 0"""

    if "n_scientifically_correct" not in content and old_stats in content:
        content = content.replace(old_stats, new_stats)
        print("OK n_scientifically_correct sayaci eklendi")

    # Sayac artirma
    old_confirmed_count = """        if r.found_class == "A":
            n_class_a += 1
        elif r.found_class == "B":
            n_class_b += 1"""

    new_confirmed_count = """        if r.found_class == "A":
            n_class_a += 1
        elif r.found_class == "B":
            n_class_b += 1

        if r.is_scientifically_correct:
            n_scientifically_correct += 1"""

    if "n_scientifically_correct += 1" not in content and old_confirmed_count in content:
        content = content.replace(old_confirmed_count, new_confirmed_count)
        print("OK Bilimsel dogru sayimi eklendi")

    # Rapor ciktisina ekle
    old_report = """    print(f\"  {'Sınıf A':<30} : {n_class_a}\")
    print(f\"  {'Sınıf B':<30} : {n_class_b}\")"""

    new_report = """    print(f\"  {'Sınıf A':<30} : {n_class_a}\")
    print(f\"  {'Sınıf B':<30} : {n_class_b}\")
    print(f\"  {'BILIMSEL DOGRU':<30} : {n_scientifically_correct}/{total} \"
          f\"({100 * n_scientifically_correct / total:.0f}%)\")"""

    if "BILIMSEL DOGRU" not in content and old_report in content:
        content = content.replace(old_report, new_report)
        print("OK Rapora BILIMSEL DOGRU satiri eklendi")

    # Kaydet
    batch_file.write_text(content, encoding="utf-8")
    print(f"\nOK Guncellendi: {batch_file.name}")

    # Sozdizim kontrol
    try:
        import ast
        ast.parse(batch_file.read_text(encoding="utf-8"))
        print("OK Python sozdizimi gecerli")
        return 0
    except SyntaxError as e:
        print(f"FAIL Sozdizim hatasi: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())