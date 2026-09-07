"""
Ana pipeline orkestratörü.

Tüm pipeline modlarını tek bir giriş noktasından
yönetir. CLI ve programmatik erişim için
ana arayüz sağlar.

Desteklenen modlar:
    - single   : tek hedef analizi
    - batch    : toplu hedef analizi
    - sector   : sektör bazlı tarama
    - followup : JWST follow-up
    - benchmark: performans doğrulama
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Union

from loguru import logger

from astrotransit.settings import Settings, get_settings
from astrotransit.logging_config import setup_logging
from astrotransit.pipelines.tess_pipeline import (
    TESSPipeline,
    TESSTargetResult,
)
from astrotransit.pipelines.jwst_pipeline import (
    JWSTFollowUpPipeline,
    JWSTFollowUpResult,
)
from astrotransit.pipelines.benchmark_pipeline import (
    BenchmarkPipeline,
    BenchmarkResult,
)
from astrotransit.outputs.writers import OutputManager


class PipelineMode(str, Enum):
    """Pipeline çalışma modları."""

    SINGLE = "single"
    BATCH = "batch"
    FOLLOWUP = "followup"
    BENCHMARK = "benchmark"


class AstroTransitOrchestrator:
    """
    AstroTransit ana orkestratörü.

    Tüm pipeline modlarını koordine eder.

    Parameters
    ----------
    config_path : str, opsiyonel
        Konfigürasyon dosyası yolu.
    force_mcmc : bool
        Tüm adaylarda MCMC zorla.
    force_map : bool
        Sadece MAP kullan.
    skip_visualization : bool
        Görselleştirme atla.
    skip_catalog : bool
        Katalog sorgusu atla.
    log_level : str
        Log seviyesi.
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        force_mcmc: bool = False,
        force_map: bool = False,
        skip_visualization: bool = False,
        skip_catalog: bool = False,
        log_level: str = "INFO",
    ):
        # Konfigürasyon
        self.settings = get_settings(config_path)

        # Loglama
        setup_logging(
            log_level=log_level or self.settings.general.log_level,
        )

        self._force_mcmc = force_mcmc
        self._force_map = force_map
        self._skip_viz = skip_visualization
        self._skip_catalog = skip_catalog

        # Output manager (paylaşımlı)
        self._output = OutputManager(settings=self.settings)

        logger.info(
            f"AstroTransit Orkestratör başlatıldı — "
            f"MCMC: {'zorla' if force_mcmc else 'oto'}, "
            f"görsel: {'kapalı' if skip_visualization else 'açık'}"
        )

    def run_single(
        self,
        target: str | int,
        sectors: Optional[list[int]] = None,
    ) -> TESSTargetResult:
        """
        Tek bir hedef analizi.

        Parameters
        ----------
        target : str veya int
            TIC ID.
        sectors : list[int], opsiyonel
            İşlenecek sektörler.

        Returns
        -------
        TESSTargetResult
        """

        logger.info(f"Mod: SINGLE — hedef: {target}")

        with self._create_tess_pipeline() as pipeline:
            result = pipeline.run_target(target, sectors=sectors)

        self._finalize()
        return result

    def run_batch(
        self,
        targets: list[str | int],
        sectors: Optional[list[int]] = None,
    ) -> list[TESSTargetResult]:
        """
        Toplu hedef analizi.

        Parameters
        ----------
        targets : list
            TIC ID listesi.
        sectors : list[int], opsiyonel
            İşlenecek sektörler.

        Returns
        -------
        list[TESSTargetResult]
        """

        logger.info(f"Mod: BATCH — {len(targets)} hedef")

        with self._create_tess_pipeline() as pipeline:
            results = pipeline.run_batch(targets, sectors=sectors)

        self._finalize()
        return results

    def run_followup(
        self,
        target_id: str,
        tess_period: float,
        tess_t0: float,
        tess_duration: float,
        tess_rp_rs: float,
        stellar_radius: float = 1.0,
        stellar_mass: float = 1.0,
        stellar_teff: float = 5778.0,
    ) -> JWSTFollowUpResult:
        """
        JWST follow-up analizi.

        Parameters
        ----------
        target_id : str
            Hedef ID.
        tess_period, tess_t0, tess_duration, tess_rp_rs : float
            TESS'ten gelen parametreler.
        stellar_radius, stellar_mass, stellar_teff : float
            Yıldız parametreleri.

        Returns
        -------
        JWSTFollowUpResult
        """

        logger.info(f"Mod: FOLLOWUP — hedef: {target_id}")

        try:
            pipeline = JWSTFollowUpPipeline(settings=self.settings)
        except ImportError as exc:
            logger.error(f"JWST follow-up bağımlılığı eksik: {exc}")
            return JWSTFollowUpResult(
                target_id=target_id,
                tess_period=tess_period,
                error=str(exc),
            )

        result = pipeline.run(
            target_id=target_id,
            tess_period=tess_period,
            tess_t0=tess_t0,
            tess_duration=tess_duration,
            tess_rp_rs=tess_rp_rs,
            stellar_radius=stellar_radius,
            stellar_mass=stellar_mass,
            stellar_teff=stellar_teff,
        )

        return result

    def run_benchmark(
        self,
        confirmed: Optional[list[str]] = None,
        false_positives: Optional[list[str]] = None,
        quiet_stars: Optional[list[str]] = None,
        max_per_category: Optional[int] = None,
    ) -> BenchmarkResult:
        """
        Benchmark doğrulama.

        Parameters
        ----------
        confirmed : list[str], opsiyonel
            Bilinen gezegen hedefleri.
        false_positives : list[str], opsiyonel
            Bilinen FP hedefleri.
        quiet_stars : list[str], opsiyonel
            Sakin yıldız hedefleri.
        max_per_category : int, opsiyonel
            Kategori başına limit (test).

        Returns
        -------
        BenchmarkResult
        """

        logger.info("Mod: BENCHMARK")

        benchmark = BenchmarkPipeline(settings=self.settings)

        result = benchmark.run(
            confirmed_targets=confirmed,
            fp_targets=false_positives,
            quiet_targets=quiet_stars,
            max_per_category=max_per_category,
        )

        return result

    def _create_tess_pipeline(self) -> TESSPipeline:
        """TESS pipeline nesnesi oluşturur."""

        return TESSPipeline(
            settings=self.settings,
            output_manager=self._output,
            force_mcmc=self._force_mcmc,
            force_map=self._force_map,
            skip_visualization=self._skip_viz,
            skip_catalog=self._skip_catalog,
        )

    def _finalize(self) -> None:
        """Çıktıları finalize eder."""

        try:
            self._output.export_csv()
        except Exception as e:
            logger.warning(f"CSV export hatası: {e}")

    def close(self) -> None:
        """Orkestratörü kapatır."""

        self._output.close()
        logger.info("AstroTransit Orkestratör kapatıldı.")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()