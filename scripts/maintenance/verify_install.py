"""
AstroTransit kurulum doğrulama scripti.
Çalıştırma: python scripts/maintenance/verify_install.py
"""

from __future__ import annotations

import sys
import importlib
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))


def check_package(name: str, import_name: str = None) -> tuple[bool, str]:
    import_name = import_name or name
    try:
        mod = importlib.import_module(import_name)
        version = getattr(mod, "__version__", "?")
        return True, version
    except ImportError:
        return False, "KURULU DEĞİL"


def check_module(name: str) -> tuple[bool, str]:
    try:
        importlib.import_module(name)
        return True, "OK"
    except Exception as e:
        return False, str(e)[:100]


def main():
    print("=" * 65)
    print("  AstroTransit Kurulum Doğrulama")
    print("=" * 65)
    print(f"  Python : {sys.version.split()[0]}")
    print(f"  Kök    : {project_root}")
    print()

    # ── Temel paketler ──
    print("── Temel Paketler ──")
    packages = [
        ("astropy",             "astropy"),
        ("astroquery",          "astroquery"),
        ("lightkurve",          "lightkurve"),
        ("numpy",               "numpy"),
        ("scipy",               "scipy"),
        ("pandas",              "pandas"),
        ("pyarrow",             "pyarrow"),
        ("matplotlib",          "matplotlib"),
        ("plotly",              "plotly"),
        ("pydantic",            "pydantic"),
        ("loguru",              "loguru"),
        ("typer",               "typer"),
        ("rich",                "rich"),
        ("streamlit",           "streamlit"),
        ("wotan",               "wotan"),
        ("transitleastsquares", "transitleastsquares"),
        ("batman-package",      "batman"),
        ("boto3",               "boto3"),
        ("tqdm",                "tqdm"),
    ]

    core_ok = True
    for name, imp in packages:
        ok, ver = check_package(name, imp)
        mark = "✓" if ok else "✗"
        if not ok:
            core_ok = False
        print(f"  {mark} {name:30s} {ver}")

    # ── Opsiyonel paketler ──
    print()
    print("── Opsiyonel Paketler ──")
    optional = [
        ("celerite2", "celerite2"),
        ("pymc",      "pymc"),
        ("exoplanet", "exoplanet"),
        ("arviz",     "arviz"),
    ]
    for name, imp in optional:
        ok, ver = check_package(name, imp)
        mark = "✓" if ok else "⚠"
        print(f"  {mark} {name:30s} {ver if ok else 'EKSİK (opsiyonel)'}")

    # ── AstroTransit modülleri ──
    print()
    print("── AstroTransit Modülleri ──")
    modules = [
        "astrotransit",
        "astrotransit.settings",
        "astrotransit.logging_config",
        "astrotransit.utils.paths",
        "astrotransit.utils.identifiers",
        "astrotransit.utils.time",
        "astrotransit.data.temp_cache",
        "astrotransit.data.mast_client",
        "astrotransit.data.tess_client",
        "astrotransit.data.catalog_client",
        "astrotransit.preprocessing.normalization",
        "astrotransit.preprocessing.cleaning",
        "astrotransit.preprocessing.tess_detrend",
        "astrotransit.preprocessing.pipeline",
        "astrotransit.detection.thresholds",
        "astrotransit.detection.bls_search",
        "astrotransit.detection.tls_search",
        "astrotransit.detection.cascade",
        "astrotransit.modeling.parameters",
        "astrotransit.modeling.transit_model",
        "astrotransit.modeling.map_fit",
        "astrotransit.modeling.fitter",
        "astrotransit.quality.metrics",
        "astrotransit.quality.snr",
        "astrotransit.quality.vetting",
        "astrotransit.quality.scorer",
        "astrotransit.quality.pipeline",
        "astrotransit.outputs.schemas",
        "astrotransit.outputs.parquet_writer",
        "astrotransit.outputs.json_writer",
        "astrotransit.outputs.csv_export",
        "astrotransit.outputs.writers",
        "astrotransit.visualization.base",
        "astrotransit.pipelines.tess_pipeline",
        "astrotransit.pipelines.orchestrator",
    ]

    module_ok = True
    for mod_name in modules:
        ok, msg = check_module(mod_name)
        mark = "✓" if ok else "✗"
        if not ok:
            module_ok = False
        short = mod_name.replace("astrotransit.", "at.")
        print(f"  {mark} {short:45s} {'' if ok else msg}")

    # ── Konfigürasyon ──
    print()
    print("── Konfigürasyon ──")
    config_path = project_root / "configs" / "default.toml"
    if config_path.exists():
        print(f"  ✓ default.toml bulundu")
        try:
            from astrotransit.settings import load_settings
            s = load_settings(config_path)
            print(f"  ✓ Pydantic doğrulama başarılı")
            print(f"    log_level          : {s.general.log_level}")
            print(f"    tess.author        : {s.tess.author}")
            print(f"    tess.exptime       : {s.tess.exptime}s")
            print(f"    detection.min_p    : {s.detection.min_period}d")
            print(f"    detection.max_p    : {s.detection.max_period}d")
            print(f"    fit_method         : {s.modeling.fit_method}")
            print(f"    mcmc_snr_threshold : {s.modeling.mcmc.mcmc_snr_threshold}")
        except Exception as e:
            print(f"  ✗ Pydantic hatası: {e}")
            module_ok = False
    else:
        print(f"  ✗ default.toml bulunamadı: {config_path}")
        module_ok = False

    # ── Sonuç ──
    print()
    print("=" * 65)
    if core_ok and module_ok:
        print("  ✓ TÜM KONTROLLER BAŞARILI — Proje çalışmaya hazır!")
        print()
        print("  Sonraki adım:")
        print("    python scripts/discovery/download_toi_catalog.py")
        print("    python scripts/discovery/run_discovery_pilot_v2.py --limit 5 --no-viz")
    elif core_ok:
        print("  ⚠ TEMEL PAKETLER TAMAM — Bazı modüller hatalı.")
        print("  Yukarıdaki ✗ satırlarını inceleyin.")
    else:
        print("  ✗ EKSİK PAKETLER VAR")
        print("  Çözüm: .venv\\Scripts\\python.exe -m pip install -e \".[dev]\"")
    print("=" * 65)


if __name__ == "__main__":
    main()