"""
Merkezi yol yönetimi.

Proje genelinde kullanılan tüm dizin yollarını oluşturur ve döndürür.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger


def get_project_root() -> Path:
    """Proje kök dizinini döndürür."""

    # Bu dosya: astrotransit/utils/paths.py
    # Kök: ../../
    return Path(__file__).resolve().parent.parent.parent


def ensure_dir(path: Path) -> Path:
    """Dizin yoksa oluşturur ve yolunu döndürür."""

    path.mkdir(parents=True, exist_ok=True)
    return path


class ProjectPaths:
    """
    Proje genelinde kullanılan tüm yolları yönetir.

    Attributes
    ----------
    root : Path
        Proje kök dizini.
    configs : Path
        Konfigürasyon dosyaları dizini.
    outputs : Path
        Çıktı dizini.
    temp : Path
        Geçici dosyalar dizini.
    benchmarks : Path
        Benchmark veri setleri dizini.
    """

    def __init__(self, output_dir: str = "outputs", temp_dir: str = ".cache/astrotransit"):
        self.root = get_project_root()
        self.configs = self.root / "configs"

        # Çıktı dizinleri
        self.outputs = ensure_dir(self.root / output_dir)
        self.parquet = ensure_dir(self.outputs / "parquet")
        self.json = ensure_dir(self.outputs / "json")
        self.csv = ensure_dir(self.outputs / "csv")
        self.figures = ensure_dir(self.outputs / "figures")
        self.reports = ensure_dir(self.outputs / "reports")

        # Geçici dizin
        self.temp = ensure_dir(self.root / temp_dir)

        # Benchmark dizinleri
        self.benchmarks = self.root / "benchmarks"
        self.benchmarks_tess = self.benchmarks / "tess"
        self.benchmarks_jwst = self.benchmarks / "jwst"

        logger.debug(f"Proje kök dizini: {self.root}")
        logger.debug(f"Çıktı dizini: {self.outputs}")
        logger.debug(f"Geçici dizin: {self.temp}")

    def target_dir(self, target_id: str) -> Path:
        """Belirli bir hedef için çıktı alt dizini oluşturur."""

        safe_name = target_id.replace(" ", "_").replace("/", "_")
        return ensure_dir(self.outputs / "targets" / safe_name)

    def target_figure_dir(self, target_id: str) -> Path:
        """Belirli bir hedef için görsel alt dizini oluşturur."""

        return ensure_dir(self.target_dir(target_id) / "figures")

    def target_json(self, target_id: str) -> Path:
        """Belirli bir hedef için JSON dosya yolunu döndürür."""

        return self.target_dir(target_id) / "result.json"