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
import json
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger

from astrotransit.settings import Settings, get_settings
from astrotransit.pipelines.tess_pipeline import TESSPipeline, TESSTargetResult
from astrotransit.validation.benchmark_report import (
    BenchmarkPerformanceReport,
    VerifiedTarget,
    evaluate_benchmark_results,
    load_verified_targets,
    normalize_target_id,
)


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
    n_evaluation_errors: int = 0
    n_negative_not_evaluated: int = 0
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1_score: Optional[float] = None
    recovery_rate: Optional[float] = None
    false_alarm_rate: Optional[float] = None

    @staticmethod
    def _round_metric(value: Optional[float]) -> Optional[float]:
        return None if value is None else round(value, 4)

    def compute(self) -> None:
        """İstatistikleri hesaplar."""

        tp = self.true_positives
        fp = self.false_positives
        fn = self.false_negatives
        tn = self.true_negatives

        self.precision = tp / (tp + fp) if (tp + fp) > 0 else None
        self.recall = tp / (tp + fn) if (tp + fn) > 0 else None

        if self.precision is not None and self.recall is not None and self.precision + self.recall > 0:
            self.f1_score = (
                2 * self.precision * self.recall /
                (self.precision + self.recall)
            )
        else:
            self.f1_score = None

        total_confirmed = tp + fn
        self.recovery_rate = tp / total_confirmed if total_confirmed > 0 else None

        total_negative = fp + tn
        self.false_alarm_rate = fp / total_negative if total_negative > 0 else None

    def to_dict(self) -> dict:
        return {
            "n_confirmed_targets": self.n_confirmed_targets,
            "n_false_positive_targets": self.n_false_positive_targets,
            "n_quiet_targets": self.n_quiet_targets,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "true_negatives": self.true_negatives,
            "n_evaluation_errors": self.n_evaluation_errors,
            "n_negative_not_evaluated": self.n_negative_not_evaluated,
            "precision": self._round_metric(self.precision),
            "recall": self._round_metric(self.recall),
            "f1_score": self._round_metric(self.f1_score),
            "recovery_rate": self._round_metric(self.recovery_rate),
            "false_alarm_rate": self._round_metric(self.false_alarm_rate),
        }

    def report(self) -> str:
        """İnsan okunabilir performans raporu."""

        def fmt(value: Optional[float]) -> str:
            return "NA" if value is None else f"{value:.4f}"

        return (
            f"\n{'=' * 60}\n"
            f"  AstroTransit Benchmark Raporu (Mühendislik Özeti)\n"
            f"{'=' * 60}\n"
            f"  Hedef Sayıları:\n"
            f"    Confirmed (Bilinen Gezegen):     {self.n_confirmed_targets}\n"
            f"    False Positive (Sahte Sinyal):   {self.n_false_positive_targets}\n"
            f"    Quiet Star (Sakin Yıldız):       {self.n_quiet_targets}\n"
            f"\n"
            f"  Confusion Matrix (Tespit Düzeyi):\n"
            f"    True Positive (Sinyal Bulundu):  {self.true_positives}\n"
            f"    False Positive (Sahte Bulundu): {self.false_positives}\n"
            f"    False Negative (Kaçırıldı):     {self.false_negatives}\n"
            f"    True Negative (Sakin Geçti):     {self.true_negatives}\n"
            f"\n"
            f"  Performans (Tespit Düzeyi):\n"
            f"    Signal Detection Recall (Recall): {fmt(self.recall)}\n"
            f"    Signal Precision:                {fmt(self.precision)}\n"
            f"    Signal F1-Score:                 {fmt(self.f1_score)}\n"
            f"    False Alarm Rate:                {fmt(self.false_alarm_rate)}\n"
            f"{'=' * 60}"
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
    performance_report: Optional[BenchmarkPerformanceReport] = None

    def to_dict(self) -> dict:
        """Makine-okur benchmark özeti; ground-truth ve ölçüm ayrıdır."""

        return {
            "metrics": self.metrics.to_dict(),
            "performance_report": (
                self.performance_report.to_dict() if self.performance_report is not None else None
            ),
        }


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

        confirmed_source = confirmed_path or Path(benchmark_cfg.confirmed_targets_file)
        fp_source = fp_path
        if fp_source is None and benchmark_cfg.false_positives_file:
            fp_source = Path(benchmark_cfg.false_positives_file)
        quiet_source = quiet_path
        if quiet_source is None and benchmark_cfg.quiet_stars_file:
            quiet_source = Path(benchmark_cfg.quiet_stars_file)

        confirmed = self._load_target_list(confirmed_source)
        fp = self._load_target_list(fp_source) if fp_source is not None else []
        quiet = self._load_target_list(quiet_source) if quiet_source is not None else []

        logger.info(
            f"Benchmark hedefleri yüklendi — "
            f"confirmed: {len(confirmed)}, "
            f"FP: {len(fp)}, "
            f"quiet: {len(quiet)}"
        )

        return confirmed, fp, quiet

    def load_verified_target_specs(self, path: Optional[Path] = None) -> list[VerifiedTarget]:
        """Known-target ground truth kayıtlarını yükler."""

        source = path or Path(self.settings.benchmark.verified_targets_file)
        try:
            specs = load_verified_targets(source)
        except (OSError, ValueError, TypeError) as exc:
            logger.error(f"Verified target dosyası okunamadı ({source}): {exc}")
            return []
        logger.info(f"Verified target ground truth yüklendi: {len(specs)} hedef")
        return specs

    @staticmethod
    def _load_target_list(path: Optional[Path]) -> list[str]:
        """JSON, Parquet veya CSV dosyasından TIC ID listesi okur."""

        if path is None:
            return []
        if not path.exists():
            logger.warning(f"Benchmark dosyası bulunamadı: {path}")
            return []

        try:
            if path.suffix.lower() == ".json":
                payload = json.loads(path.read_text(encoding="utf-8"))
                rows = payload.get("targets", []) if isinstance(payload, dict) else payload
                if not isinstance(rows, list):
                    raise ValueError("JSON hedef listesi liste biçiminde olmalıdır")
                return [
                    normalize_target_id(row.get("tic_id", row.get("source_id", row)))
                    if isinstance(row, dict)
                    else normalize_target_id(row)
                    for row in rows
                ]
            if path.suffix.lower() == ".parquet":
                df = pd.read_parquet(path)
            elif path.suffix.lower() == ".csv":
                df = pd.read_csv(path)
            else:
                logger.warning(f"Desteklenmeyen format: {path}")
                return []

            # İlk sütundaki ID'leri kullan
            if "tic_id" in df.columns:
                return [normalize_target_id(tid) for tid in df["tic_id"].tolist()]
            if "source_id" in df.columns:
                return [normalize_target_id(value) for value in df["source_id"].tolist()]
            return [normalize_target_id(tid) for tid in df.iloc[:, 0].tolist()]

        except Exception as exc:
            logger.error(f"Benchmark dosyası okunamadı ({path}): {exc}")
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

        verified_specs = self.load_verified_target_specs()

        # Hedef listeleri yoksa dosyalardan yükle. Ground-truth JSON'u hem
        # hedef kimliklerini hem de beklenen fiziksel parametreleri taşır.
        if confirmed_targets is None and fp_targets is None and quiet_targets is None:
            confirmed_targets, fp_targets, quiet_targets = self.load_benchmark_targets()

        confirmed_targets = [normalize_target_id(target) for target in (confirmed_targets or [])]
        fp_targets = [normalize_target_id(target) for target in (fp_targets or [])]
        quiet_targets = [normalize_target_id(target) for target in (quiet_targets or [])]

        # Limit uygula
        if max_per_category is not None:
            if max_per_category < 0:
                raise ValueError("max_per_category negatif olamaz")
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
                metrics.n_evaluation_errors += 1
                metrics.n_negative_not_evaluated += 1

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
                metrics.n_evaluation_errors += 1
                metrics.n_negative_not_evaluated += 1

        metrics.n_quiet_targets = len(quiet_targets)

        # ═══════════════════════════════
        # Performans hesapla
        # ═══════════════════════════════
        metrics.compute()

        logger.info(metrics.report())

        selected_ids = {normalize_target_id(target) for target in confirmed_targets}
        selected_specs = [
            spec for spec in verified_specs if normalize_target_id(spec.target_id) in selected_ids
        ]
        if selected_specs:
            result.performance_report = evaluate_benchmark_results(
                selected_specs,
                result.confirmed_results,
                period_tolerance_fraction=self.settings.benchmark.period_tolerance_fraction,
                radius_tolerance_fraction=self.settings.benchmark.radius_tolerance_fraction,
            )
            logger.info(result.performance_report.summary())
        else:
            logger.warning(
                "Performance benchmark raporu üretilemedi: ground-truth hedefi yok."
            )

        # Pipeline'ı kapat
        self._pipeline.close()

        return result