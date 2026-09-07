"""
Benchmark doğrulama pipeline'ı.

Bilinen hedefler üzerinde pipeline'ın performansını
ölçer ve raporlar.

Kullanılan veri setleri:
    - Confirmed exoplanets (bilinen gezegenler)
    - Known false positives (bilinen FP'ler)
    - Quiet stars (sakin, transitsiz yıldızlar)

Performans metrikleri:
    - Precision: TP / (TP + FP)
    - Recall: TP / (TP + FN)
    - F1-score: 2 × (P × R) / (P + R)
    - Recovery rate: bilinen transit bulma oranı
    - False alarm rate: transitsiz yıldızda alarm oranı
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from astrotransit.settings import Settings, get_settings
from astrotransit.pipelines.tess_pipeline import TESSPipeline, TESSTargetResult


# ──────────────────────────────────────
# Benchmark sonuç modeli
# ──────────────────────────────────────
@dataclass
class BenchmarkMetrics:
    """
    Benchmark performans metrikleri.

    Attributes
    ----------
    n_confirmed_targets : int
        Test edilen confirmed hedef sayısı.
    n_false_positive_targets : int
        Test edilen FP hedef sayısı.
    n_quiet_targets : int
        Test edilen sakin yıldız sayısı.
    true_positives : int
        Doğru tespit (confirmed + bulundu).
    false_positives : int
        Yanlış tespit (FP veya sakin + bulundu).
    false_negatives : int
        Kaçırılan (confirmed + bulunamadı).
    true_negatives : int
        Doğru red (sakin + bulunamadı).
    precision : float
        TP / (TP + FP).
    recall : float
        TP / (TP + FN).
    f1_score : float
        2 × (P × R) / (P + R).
    recovery_rate : float
        Bilinen transit bulma oranı.
    false_alarm_rate : float
        Transitsiz yıldızda alarm oranı.
    """

    n_confirmed_targets: int = 0
    n_false_positive_targets: int = 0
    n_quiet_targets: int = 0
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    true_negatives: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    recovery_rate: float = 0.0
    false_alarm_rate: float = 0.0

    def compute(self) -> None:
        """İstatistikleri hesaplar."""

        tp = self.true_positives
        fp = self.false_positives
        fn = self.false_negatives
        tn = self.true_negatives

        self.precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        self.recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

        if self.precision + self.recall > 0:
            self.f1_score = (
                2 * self.precision * self.recall /
                (self.precision + self.recall)
            )
        else:
            self.f1_score = 0.0

        total_confirmed = tp + fn
        self.recovery_rate = tp / total_confirmed if total_confirmed > 0 else 0.0

        total_negative = fp + tn
        self.false_alarm_rate = fp / total_negative if total_negative > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "n_confirmed_targets": self.n_confirmed_targets,
            "n_false_positive_targets": self.n_false_positive_targets,
            "n_quiet_targets": self.n_quiet_targets,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "true_negatives": self.true_negatives,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "recovery_rate": round(self.recovery_rate, 4),
            "false_alarm_rate": round(self.false_alarm_rate, 4),
        }

    def report(self) -> str:
        """İnsan okunabilir performans raporu."""

        return (
            f"\n{'=' * 50}\n"
            f"  AstroTransit Benchmark Raporu\n"
            f"{'=' * 50}\n"
            f"  Hedef Sayıları:\n"
            f"    Confirmed:      {self.n_confirmed_targets}\n"
            f"    False Positive:  {self.n_false_positive_targets}\n"
            f"    Quiet Star:      {self.n_quiet_targets}\n"
            f"\n"
            f"  Confusion Matrix:\n"
            f"    True Positive:   {self.true_positives}\n"
            f"    False Positive:  {self.false_positives}\n"
            f"    False Negative:  {self.false_negatives}\n"
            f"    True Negative:   {self.true_negatives}\n"
            f"\n"
            f"  Performans:\n"
            f"    Precision:       {self.precision:.4f}\n"
            f"    Recall:          {self.recall:.4f}\n"
            f"    F1-Score:        {self.f1_score:.4f}\n"
            f"    Recovery Rate:   {self.recovery_rate:.4f}\n"
            f"    False Alarm:     {self.false_alarm_rate:.4f}\n"
            f"{'=' * 50}"
        )


@dataclass
class BenchmarkResult:
    """
    Benchmark pipeline tam sonucu.

    Attributes
    ----------
    metrics : BenchmarkMetrics
        Performans metrikleri.
    confirmed_results : list[TESSTargetResult]
        Confirmed hedef sonuçları.
    fp_results : list[TESSTargetResult]
        FP hedef sonuçları.
    quiet_results : list[TESSTargetResult]
        Sakin yıldız sonuçları.
    """

    metrics: BenchmarkMetrics = field(default_factory=BenchmarkMetrics)
    confirmed_results: list[TESSTargetResult] = field(default_factory=list)
    fp_results: list[TESSTargetResult] = field(default_factory=list)
    quiet_results: list[TESSTargetResult] = field(default_factory=list)


# ──────────────────────────────────────
# Benchmark Pipeline
# ──────────────────────────────────────
class BenchmarkPipeline:
    """
    Benchmark doğrulama pipeline'ı.

    Parameters
    ----------
    settings : Settings, opsiyonel
        Proje konfigürasyonu.
    """

    def __init__(self, settings: Optional[Settings] = None):
        if settings is None:
            settings = get_settings()

        self.settings = settings

        self._pipeline = TESSPipeline(
            settings=settings,
            skip_visualization=True,
            force_map=True,
        )

        logger.info("BenchmarkPipeline başlatıldı.")

    def load_benchmark_targets(
        self,
        confirmed_path: Optional[Path] = None,
        fp_path: Optional[Path] = None,
        quiet_path: Optional[Path] = None,
    ) -> tuple[list[str], list[str], list[str]]:
        """
        Benchmark hedef listelerini yükler.

        Parameters
        ----------
        confirmed_path : Path, opsiyonel
            Confirmed exoplanet Parquet dosyası.
        fp_path : Path, opsiyonel
            False positive Parquet dosyası.
        quiet_path : Path, opsiyonel
            Quiet star Parquet dosyası.

        Returns
        -------
        tuple[list, list, list]
            (confirmed, false_positive, quiet) TIC ID listeleri.
        """

        benchmark_cfg = self.settings.benchmark

        confirmed = self._load_target_list(
            confirmed_path or Path(benchmark_cfg.confirmed_targets_file)
        )
        fp = self._load_target_list(
            fp_path or Path(benchmark_cfg.false_positives_file)
        )
        quiet = self._load_target_list(
            quiet_path or Path(benchmark_cfg.quiet_stars_file)
        )

        logger.info(
            f"Benchmark hedefleri yüklendi — "
            f"confirmed: {len(confirmed)}, "
            f"FP: {len(fp)}, "
            f"quiet: {len(quiet)}"
        )

        return confirmed, fp, quiet

    @staticmethod
    def _load_target_list(path: Path) -> list[str]:
        """Parquet veya CSV dosyasından TIC ID listesi okur."""

        if not path.exists():
            logger.warning(f"Benchmark dosyası bulunamadı: {path}")
            return []

        try:
            if path.suffix == ".parquet":
                df = pd.read_parquet(path)
            elif path.suffix == ".csv":
                df = pd.read_csv(path)
            else:
                logger.warning(f"Desteklenmeyen format: {path}")
                return []

            # İlk sütundaki ID'leri kullan
            if "tic_id" in df.columns:
                return [f"TIC {tid}" for tid in df["tic_id"].tolist()]
            elif "source_id" in df.columns:
                return df["source_id"].tolist()
            else:
                return [f"TIC {tid}" for tid in df.iloc[:, 0].tolist()]

        except Exception as e:
            logger.error(f"Benchmark dosyası okunamadı ({path}): {e}")
            return []

    def run(
        self,
        confirmed_targets: Optional[list[str]] = None,
        fp_targets: Optional[list[str]] = None,
        quiet_targets: Optional[list[str]] = None,
        max_per_category: Optional[int] = None,
    ) -> BenchmarkResult:
        """
        Benchmark pipeline'ını çalıştırır.

        Parameters
        ----------
        confirmed_targets : list[str], opsiyonel
            Bilinen gezegen hedef listesi.
        fp_targets : list[str], opsiyonel
            Bilinen FP hedef listesi.
        quiet_targets : list[str], opsiyonel
            Sakin yıldız hedef listesi.
        max_per_category : int, opsiyonel
            Kategori başına maksimum hedef (test için).

        Returns
        -------
        BenchmarkResult
            Benchmark sonuçları.
        """

        # Hedef listeleri yoksa dosyalardan yükle
        if confirmed_targets is None and fp_targets is None and quiet_targets is None:
            confirmed_targets, fp_targets, quiet_targets = (
                self.load_benchmark_targets()
            )

        confirmed_targets = confirmed_targets or []
        fp_targets = fp_targets or []
        quiet_targets = quiet_targets or []

        # Limit uygula
        if max_per_category is not None:
            confirmed_targets = confirmed_targets[:max_per_category]
            fp_targets = fp_targets[:max_per_category]
            quiet_targets = quiet_targets[:max_per_category]

        logger.info(
            f"Benchmark başlıyor — "
            f"confirmed: {len(confirmed_targets)}, "
            f"FP: {len(fp_targets)}, "
            f"quiet: {len(quiet_targets)}"
        )

        result = BenchmarkResult()
        metrics = result.metrics

        # ═══════════════════════════════
        # Confirmed Targets
        # ═══════════════════════════════
        logger.info("── Confirmed hedefler işleniyor ──")

        for target in confirmed_targets:
            try:
                target_result = self._pipeline.run_target(target)
                result.confirmed_results.append(target_result)

                if target_result.candidates_confirmed > 0:
                    metrics.true_positives += 1
                else:
                    metrics.false_negatives += 1

            except Exception as e:
                logger.error(f"Confirmed {target}: {e}")
                metrics.false_negatives += 1

        metrics.n_confirmed_targets = len(confirmed_targets)

        # ═══════════════════════════════
        # False Positive Targets
        # ═══════════════════════════════
        logger.info("── False positive hedefler işleniyor ──")

        for target in fp_targets:
            try:
                target_result = self._pipeline.run_target(target)
                result.fp_results.append(target_result)

                if target_result.candidates_confirmed > 0:
                    metrics.false_positives += 1
                else:
                    metrics.true_negatives += 1

            except Exception as e:
                logger.error(f"FP {target}: {e}")
                metrics.true_negatives += 1

        metrics.n_false_positive_targets = len(fp_targets)

        # ═══════════════════════════════
        # Quiet Stars
        # ═══════════════════════════════
        logger.info("── Sakin yıldızlar işleniyor ──")

        for target in quiet_targets:
            try:
                target_result = self._pipeline.run_target(target)
                result.quiet_results.append(target_result)

                if target_result.candidates_confirmed > 0:
                    metrics.false_positives += 1
                else:
                    metrics.true_negatives += 1

            except Exception as e:
                logger.error(f"Quiet {target}: {e}")
                metrics.true_negatives += 1

        metrics.n_quiet_targets = len(quiet_targets)

        # ═══════════════════════════════
        # Performans hesapla
        # ═══════════════════════════════
        metrics.compute()

        logger.info(metrics.report())

        # Pipeline'ı kapat
        self._pipeline.close()

        return result