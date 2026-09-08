"""
AstroTransit proje sağlık kontrolü.

Dosya konumlarını, çift kopyaları, yanlış yerleşimleri
ve proje yapısı bütünlüğünü kontrol eder.

Çalıştırma: python scripts/maintenance/check_project.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Tuple

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))


# ──────────────────────────────────────
# ANSI renk kodları
# ──────────────────────────────────────
class Color:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def ok(msg: str) -> str:
    return f"{Color.GREEN}✓{Color.RESET} {msg}"


def fail(msg: str) -> str:
    return f"{Color.RED}✗{Color.RESET} {msg}"


def warn(msg: str) -> str:
    return f"{Color.YELLOW}⚠{Color.RESET} {msg}"


def info(msg: str) -> str:
    return f"{Color.BLUE}i{Color.RESET} {msg}"


# ──────────────────────────────────────
# Proje yapı kuralları
# ──────────────────────────────────────

# Bu dosyalar SADECE astrotransit/ altında olmalı
EXPECTED_IN_PACKAGE = [
    # Kök paket dosyaları
    ("astrotransit/__init__.py",              True),
    ("astrotransit/version.py",               True),
    ("astrotransit/settings.py",              True),
    ("astrotransit/logging_config.py",        True),

    # utils
    ("astrotransit/utils/__init__.py",        True),
    ("astrotransit/utils/paths.py",           True),
    ("astrotransit/utils/identifiers.py",     True),
    ("astrotransit/utils/time.py",            True),

    # data
    ("astrotransit/data/__init__.py",         True),
    ("astrotransit/data/temp_cache.py",       True),
    ("astrotransit/data/mast_client.py",      True),
    ("astrotransit/data/tess_client.py",      True),
    ("astrotransit/data/catalog_client.py",   True),

    # preprocessing
    ("astrotransit/preprocessing/__init__.py",     True),
    ("astrotransit/preprocessing/normalization.py", True),
    ("astrotransit/preprocessing/cleaning.py",      True),
    ("astrotransit/preprocessing/tess_detrend.py",  True),
    ("astrotransit/preprocessing/jwst_detrend.py",  True),
    ("astrotransit/preprocessing/pipeline.py",      True),

    # detection
    ("astrotransit/detection/__init__.py",    True),
    ("astrotransit/detection/thresholds.py",  True),
    ("astrotransit/detection/bls_search.py",  True),
    ("astrotransit/detection/tls_search.py",  True),
    ("astrotransit/detection/cascade.py",     True),

    # modeling
    ("astrotransit/modeling/__init__.py",     True),
    ("astrotransit/modeling/parameters.py",   True),
    ("astrotransit/modeling/transit_model.py", True),
    ("astrotransit/modeling/map_fit.py",      True),
    ("astrotransit/modeling/pymc_fit.py",     False),  # Opsiyonel
    ("astrotransit/modeling/fitter.py",       True),

    # quality
    ("astrotransit/quality/__init__.py",      True),
    ("astrotransit/quality/metrics.py",       True),
    ("astrotransit/quality/snr.py",           True),
    ("astrotransit/quality/vetting.py",       True),
    ("astrotransit/quality/scorer.py",        True),
    ("astrotransit/quality/pipeline.py",      True),

    # outputs
    ("astrotransit/outputs/__init__.py",      True),
    ("astrotransit/outputs/schemas.py",       True),
    ("astrotransit/outputs/parquet_writer.py", True),
    ("astrotransit/outputs/json_writer.py",   True),
    ("astrotransit/outputs/csv_export.py",    True),
    ("astrotransit/outputs/writers.py",       True),

    # visualization
    ("astrotransit/visualization/__init__.py",       True),
    ("astrotransit/visualization/base.py",           True),
    ("astrotransit/visualization/lightcurve_plot.py", False),
    ("astrotransit/visualization/periodogram_plot.py", False),
    ("astrotransit/visualization/folded_plot.py",    False),
    ("astrotransit/visualization/diagnostic_plots.py", False),
    ("astrotransit/visualization/summary_panel.py",  False),
    ("astrotransit/visualization/report_generator.py", False),

    # pipelines
    ("astrotransit/pipelines/__init__.py",    True),
    ("astrotransit/pipelines/tess_pipeline.py", True),
    ("astrotransit/pipelines/jwst_pipeline.py", False),
    ("astrotransit/pipelines/benchmark_pipeline.py", False),
    ("astrotransit/pipelines/orchestrator.py", True),

    # CLI
    ("cli/__init__.py",                       True),
    ("cli/main.py",                           True),

    # Dashboard
    ("dashboard/__init__.py",                 True),
    ("dashboard/app.py",                      True),

    # Config
    ("configs/default.toml",                  True),

    # Proje kök
    ("pyproject.toml",                        True),
]

# Bu klasör veya dosyalar KÖK dizinde OLMAMALI
# (Muhtemelen astrotransit/ altında olmalıydılar)
FORBIDDEN_IN_ROOT = [
    "data",
    "detection",
    "modeling",
    "outputs_module",  # outputs klasörü var ama modül olarak DEĞİL
    "pipelines",
    "preprocessing",
    "quality",
    "utils",
    "validation",
    "visualization",
    "settings.py",
    "logging_config.py",
    "__init__.py",  # kök dizinde __init__.py olmamalı
]

# outputs/ kök klasörü SADECE çıktı için olmalı (parquet, json, csv, figures, reports)
OUTPUTS_ALLOWED_SUBDIRS = {"parquet", "json", "csv", "figures", "reports", "targets"}


# ──────────────────────────────────────
# Kontroller
# ──────────────────────────────────────

def check_required_files() -> Tuple[int, int]:
    """Beklenen dosyaları kontrol eder."""

    print(f"\n{Color.BOLD}── Gerekli Dosyalar ──{Color.RESET}\n")

    n_ok = 0
    n_fail = 0

    for rel_path, is_required in EXPECTED_IN_PACKAGE:
        full_path = project_root / rel_path
        exists = full_path.exists()

        # Dosya boyutu (boş dosya kontrolü)
        size = full_path.stat().st_size if exists else 0
        is_empty = exists and size < 10

        if exists and not is_empty:
            n_ok += 1
            # print(ok(f"{rel_path} ({size} B)"))
        elif exists and is_empty:
            print(warn(f"{rel_path}  BOŞ DOSYA ({size} B)"))
            n_fail += 1
        elif is_required:
            print(fail(f"{rel_path}  EKSİK"))
            n_fail += 1
        else:
            print(warn(f"{rel_path}  eksik (opsiyonel)"))

    total = len(EXPECTED_IN_PACKAGE)
    print()
    print(f"  Toplam: {total} | Sağlam: {Color.GREEN}{n_ok}{Color.RESET} | "
          f"Sorunlu: {Color.RED}{n_fail}{Color.RESET}")

    return n_ok, n_fail


def check_forbidden_in_root() -> int:
    """Kökte olmaması gereken dosya/klasörleri kontrol eder."""

    print(f"\n{Color.BOLD}── Kökte Olmaması Gerekenler ──{Color.RESET}\n")

    n_issues = 0

    for name in FORBIDDEN_IN_ROOT:
        path = project_root / name

        # Özel durum: outputs/ klasörü var ama sadece çıktı için
        if name == "outputs" and path.is_dir():
            continue

        if path.exists():
            kind = "klasör" if path.is_dir() else "dosya"
            print(fail(f"{name}  ({kind}) — KÖK'te olmamalı, astrotransit/ altında olmalı!"))
            n_issues += 1

    # outputs klasörünü kontrol et — sadece çıktı dizinleri olmalı
    outputs_dir = project_root / "outputs"
    if outputs_dir.is_dir():
        subdirs = [d.name for d in outputs_dir.iterdir() if d.is_dir()]
        py_files = [f.name for f in outputs_dir.iterdir() if f.suffix == ".py"]

        if py_files:
            print(fail(f"outputs/ içinde .py dosyaları var: {py_files}"))
            print(info("  outputs/ SADECE çıktı için olmalı (parquet, json, csv, figures)"))
            n_issues += 1

        unexpected = set(subdirs) - OUTPUTS_ALLOWED_SUBDIRS
        if unexpected:
            print(warn(f"outputs/ içinde beklenmeyen klasörler: {unexpected}"))

    if n_issues == 0:
        print(ok("Kökte yanlış yerleştirilmiş dosya/klasör yok."))

    return n_issues


def check_duplicate_locations() -> int:
    """Aynı dosyanın iki farklı yerde bulunması durumunu kontrol eder."""

    print(f"\n{Color.BOLD}── Çift Kopya Kontrolü ──{Color.RESET}\n")

    n_dupes = 0

    critical_modules = [
        "data", "detection", "modeling", "outputs",
        "pipelines", "preprocessing", "quality",
        "utils", "validation", "visualization",
        "settings.py", "logging_config.py",
    ]

    for name in critical_modules:
        root_path = project_root / name
        pkg_path = project_root / "astrotransit" / name

        root_exists = root_path.exists()
        pkg_exists = pkg_path.exists()

        # outputs özel durumu: hem kök hem paket olmalı (farklı amaçlarla)
        if name == "outputs":
            if pkg_exists:
                # astrotransit/outputs/ modül olmalı
                has_py = any(p.suffix == ".py" for p in pkg_path.iterdir())
                if not has_py:
                    print(warn("astrotransit/outputs/ var ama .py dosyası yok"))
                    n_dupes += 1
            continue

        if root_exists and pkg_exists:
            print(fail(f"'{name}' HEM kökte HEM astrotransit/ altında var!"))
            print(info(f"  Kök: {root_path}"))
            print(info(f"  Paket: {pkg_path}"))
            print(info("  → Kökteki silinmeli"))
            n_dupes += 1

    if n_dupes == 0:
        print(ok("Çift kopya yok."))

    return n_dupes


def check_imports() -> int:
    """Modüllerin gerçekten import edilebildiğini kontrol eder."""

    print(f"\n{Color.BOLD}── Import Testleri ──{Color.RESET}\n")

    critical_imports = [
        "astrotransit",
        "astrotransit.settings",
        "astrotransit.detection.bls_search",
        "astrotransit.detection.tls_search",
        "astrotransit.detection.cascade",
        "astrotransit.modeling.fitter",
        "astrotransit.pipelines.tess_pipeline",
        "astrotransit.pipelines.orchestrator",
    ]

    n_fail = 0

    for mod_name in critical_imports:
        try:
            __import__(mod_name)
            # print(ok(f"{mod_name}"))
        except Exception as e:
            msg = str(e)[:80]
            print(fail(f"{mod_name}"))
            print(info(f"  Hata: {msg}"))
            n_fail += 1

    if n_fail == 0:
        print(ok(f"Tüm {len(critical_imports)} kritik modül import edildi."))

    return n_fail


def check_class_definitions() -> int:
    """Kritik sınıfların dosyalarda tanımlı olduğunu kontrol eder."""

    print(f"\n{Color.BOLD}── Sınıf Tanım Kontrolü ──{Color.RESET}\n")

    class_checks = [
        ("astrotransit/detection/bls_search.py",  ["BLSPeak", "BLSResult", "BLSSearch"]),
        ("astrotransit/detection/tls_search.py",  ["TLSResult", "TLSSearch"]),
        ("astrotransit/detection/cascade.py",     ["CascadeStatus", "CascadeCandidate", "CascadeDetector"]),
        ("astrotransit/modeling/map_fit.py",      ["MAPFitResult", "MAPFitter"]),
        ("astrotransit/modeling/fitter.py",       ["ModelingOrchestrator"]),
        ("astrotransit/quality/scorer.py",        ["CandidateClass", "CandidateScorer", "QualityScore"]),
        ("astrotransit/quality/pipeline.py",      ["QualityEvaluationPipeline"]),
        ("astrotransit/outputs/writers.py",       ["OutputManager"]),
        ("astrotransit/pipelines/tess_pipeline.py", ["TESSPipeline", "TESSTargetResult"]),
        ("astrotransit/pipelines/orchestrator.py", ["AstroTransitOrchestrator"]),
    ]

    n_missing = 0

    for file_rel, required_classes in class_checks:
        file_path = project_root / file_rel

        if not file_path.exists():
            print(fail(f"{file_rel}  DOSYA YOK"))
            n_missing += len(required_classes)
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            print(fail(f"{file_rel}  OKUNAMADI: {e}"))
            continue

        missing = []
        for cls in required_classes:
            if f"class {cls}" not in content:
                missing.append(cls)

        if missing:
            print(fail(f"{file_rel}"))
            for cls in missing:
                print(info(f"  Eksik sınıf: class {cls}"))
                n_missing += 1

    if n_missing == 0:
        print(ok("Tüm kritik sınıflar tanımlı."))

    return n_missing


def check_has_candidate_property() -> int:
    """cascade.py'de has_candidate property'si var mı?"""

    print(f"\n{Color.BOLD}── has_candidate Property Kontrolü ──{Color.RESET}\n")

    cascade_file = project_root / "astrotransit" / "detection" / "cascade.py"

    if not cascade_file.exists():
        print(fail("cascade.py yok"))
        return 1

    content = cascade_file.read_text(encoding="utf-8")

    # Property tanımını ara
    if "@property" in content and "def has_candidate" in content:
        print(ok("has_candidate property tanımlı."))
        return 0
    else:
        print(fail("has_candidate property EKSIK!"))
        print(info("  CascadeCandidate sınıfına eklenmeli:"))
        print(info("    @property"))
        print(info("    def has_candidate(self) -> bool:"))
        print(info("        return self.status != CascadeStatus.BLS_FAILED"))
        return 1


def check_tls_stellar_params() -> int:
    """tls_search.py'de M_star_min/max ayarı var mı?"""

    print(f"\n{Color.BOLD}── TLS Stellar Params Kontrolü ──{Color.RESET}\n")

    tls_file = project_root / "astrotransit" / "detection" / "tls_search.py"

    if not tls_file.exists():
        print(fail("tls_search.py yok"))
        return 1

    content = tls_file.read_text(encoding="utf-8")

    if "M_star_min" in content and "M_star_max" in content:
        print(ok("TLS M_star_min/max parametreleri ayarlanmış."))
        return 0
    else:
        print(fail("TLS M_star_min/max EKSIK!"))
        print(info("  validate() metodunda şu değiştirilmeli:"))
        print(info('    tls_kwargs["M_star_min"] = m_star * 0.5'))
        print(info('    tls_kwargs["M_star_max"] = m_star * 1.5'))
        return 1


def check_output_directories() -> int:
    """Çıktı dizinlerinin varlığını kontrol eder."""

    print(f"\n{Color.BOLD}── Çıktı Dizinleri ──{Color.RESET}\n")

    required_dirs = [
        "outputs/parquet",
        "outputs/json",
        "outputs/csv",
        "outputs/figures",
        "outputs/reports",
    ]

    n_missing = 0

    for d in required_dirs:
        path = project_root / d
        if path.is_dir():
            n_files = len(list(path.iterdir()))
            note = f"({n_files} dosya)" if n_files > 0 else "(boş)"
            print(ok(f"{d}  {note}"))
        else:
            print(warn(f"{d}  yok — oluşturulacak"))
            path.mkdir(parents=True, exist_ok=True)
            n_missing += 1

    return 0  # Otomatik oluşturuldu


# ──────────────────────────────────────
# Ana rapor
# ──────────────────────────────────────

def main():
    print(f"\n{Color.BOLD}{'=' * 68}{Color.RESET}")
    print(f"  {Color.BOLD}AstroTransit — Proje Sağlık Kontrolü{Color.RESET}")
    print(f"{Color.BOLD}{'=' * 68}{Color.RESET}")
    print(f"  Kök: {project_root}")

    results = {}

    # 1. Gerekli dosyalar
    n_ok, n_fail = check_required_files()
    results["Gerekli dosyalar"] = n_fail

    # 2. Kökte olmaması gerekenler
    results["Kökteki yanlış dosyalar"] = check_forbidden_in_root()

    # 3. Çift kopyalar
    results["Çift kopyalar"] = check_duplicate_locations()

    # 4. Sınıf tanımları
    results["Sınıf tanımları"] = check_class_definitions()

    # 5. has_candidate property
    results["has_candidate property"] = check_has_candidate_property()

    # 6. TLS stellar params
    results["TLS stellar params"] = check_tls_stellar_params()

    # 7. Çıktı dizinleri
    check_output_directories()

    # 8. Import testleri (en son, diğer sorunlar düzeltildikten sonra)
    results["Import testleri"] = check_imports()

    # ── Özet ──
    print(f"\n{Color.BOLD}{'=' * 68}{Color.RESET}")
    print(f"  {Color.BOLD}ÖZET{Color.RESET}")
    print(f"{Color.BOLD}{'=' * 68}{Color.RESET}\n")

    total_issues = sum(results.values())

    for name, issues in results.items():
        if issues == 0:
            print(ok(f"{name}: sorun yok"))
        else:
            print(fail(f"{name}: {issues} sorun"))

    print()

    if total_issues == 0:
        print(f"{Color.GREEN}{Color.BOLD}  ✓ PROJE SAĞLIKLI — Test için hazır!{Color.RESET}")
        print()
        print("  Sonraki adım:")
        print("    python scripts/discovery/download_toi_catalog.py")
        print("    python scripts/discovery/run_discovery_pilot_v2.py --limit 5 --no-viz")
    else:
        print(f"{Color.RED}{Color.BOLD}  ✗ TOPLAM {total_issues} SORUN TESPİT EDİLDİ{Color.RESET}")
        print()
        print("  Yukarıdaki hataları çözdükten sonra tekrar çalıştırın.")

    print(f"\n{Color.BOLD}{'=' * 68}{Color.RESET}\n")

    return 0 if total_issues == 0 else 1


if __name__ == "__main__":
    sys.exit(main())