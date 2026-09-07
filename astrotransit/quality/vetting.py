"""
False positive vetting modülü.

Gezegen olmayan transit benzeri sinyalleri (false positive)
tespit etmek için çeşitli test kriterlerini uygular.

Uygulanan testler:
    1. Odd-Even testi          — EB tespiti
    2. İkincil tutulma testi   — EB tespiti
    3. Derinlik değişkenliği   — kararsız sinyal
    4. Yıldız değişkenliği     — sistematik
    5. Boğuşma kontrolü        — transit çok derin mi?
    6. Süre-periyot ilişkisi   — fiziksel tutarlılık
    7. Centroid kayması        — arka plan EB (ileride)

Literatür:
    Morton (2012)              — VESPA
    Giacalone & Dressing (2020) — triceratops
    Mullally et al. (2016)     — Kepler Robovetter

ÖNEMLİ — Epistemik sınır:
    Bu modülün ürettiği `false_positive_probability` (FPP) değeri, yukarıdaki
    metodolojilerden **esinlenen heuristik bir risk proxy'sidir**: test
    sonuçlarının ağırlıklı bir toplamıdır. Popülasyon öncülleri (background
    EB oranları, occurrence priors), yıldız parametre koşullu beğenilik
    oranları veya kalibrasyon içermeyen bir değerdir; dolayısıyla
    "FPP = 0.01 ⇒ adayın %1 olasılıkla false positive olduğu" anlamına
    gelmez. Değer, aday sıralama ve tarama amaçlıdır. Kalibre edilmiş bir
    FPP üretimi için etiketli veri üzerinde
    `astrotransit.validation.fpp_benchmark` modülü kullanılmalıdır.
    Metod kimliği `FPP_METHOD` sabitiyle çıktıya işlenir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
from loguru import logger

from astrotransit.detection.cascade import CascadeCandidate
from astrotransit.quality.metrics import QualityMetrics

# Bu modülün FPP tahmin metodunun çıktıya işlenen kimliği.
# Heuristik vetting ağırlıklı oy; kalibre edilmiş Bayesyen FPP değildir.
FPP_METHOD = "heuristic_vetting_weighted_v1"


# ──────────────────────────────────────
# Test sonuç tipleri
# ──────────────────────────────────────
class VettingVerdict(str, Enum):
    """Vetting test kararı."""

    PASS = "pass"           # Test geçildi
    FAIL = "fail"           # Test başarısız (FP göstergesi)
    WARN = "warn"           # Uyarı (dikkat gerektirir)
    SKIP = "skip"           # Test atlandı (yetersiz veri)


@dataclass
class VettingTest:
    """
    Tek bir vetting testi sonucu.

    Attributes
    ----------
    name : str
        Test adı.
    verdict : VettingVerdict
        Test kararı.
    value : float
        Test değeri.
    threshold : float
        Karar eşiği.
    description : str
        Kısa açıklama.
    fp_weight : float
        Bu testin FPP hesabına katkı ağırlığı (0-1).
    """

    name: str
    verdict: VettingVerdict
    value: float
    threshold: float
    description: str = ""
    fp_weight: float = 0.1

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "verdict": self.verdict.value,
            "value": round(self.value, 4),
            "threshold": round(self.threshold, 4),
            "description": self.description,
            "fp_weight": self.fp_weight,
        }


@dataclass
class VettingReport:
    """
    Tüm vetting testlerinin özet raporu.

    Attributes
    ----------
    target_id : str
        Hedef TIC ID.
    sector : int
        Sektör numarası.
    tests : list[VettingTest]
        Uygulanan testler ve sonuçları.
    n_pass : int
        Geçen test sayısı.
    n_fail : int
        Başarısız test sayısı.
    n_warn : int
        Uyarı sayısı.
    false_positive_probability : Optional[float]
        Heuristik yanlış pozitif risk proxy'si (0-1). Kalibre edilmiş
        Bayesyen bir olasılık değildir (bkz. modül docstring'i). Hiçbir
        test ölçülebilir değilse ``None`` olur; bu sıfır risk değildir.
    fpp_method : str
        FPP tahmin metodunun kimliği (çıkıta işlenir).
    is_false_positive : bool
        Kesin FP kararı.
    fp_flags : list[str]
        Tetiklenen FP bayrakları.
    """

    target_id: str
    sector: int
    tests: list[VettingTest] = field(default_factory=list)
    n_pass: int = 0
    n_fail: int = 0
    n_warn: int = 0
    false_positive_probability: Optional[float] = None
    fpp_method: str = FPP_METHOD
    is_false_positive: bool = False
    fp_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "n_tests": len(self.tests),
            "n_pass": self.n_pass,
            "n_fail": self.n_fail,
            "n_warn": self.n_warn,
            "false_positive_probability": (
                None
                if self.false_positive_probability is None
                else round(self.false_positive_probability, 4)
            ),
            "fpp_method": self.fpp_method,
            "is_false_positive": self.is_false_positive,
            "fp_flags": self.fp_flags,
            "tests": [t.to_dict() for t in self.tests],
        }

    def summary(self) -> dict:
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "fpp": (
                None
                if self.false_positive_probability is None
                else round(self.false_positive_probability, 4)
            ),
            "fpp_method": self.fpp_method,
            "is_fp": self.is_false_positive,
            "flags": self.fp_flags,
            "pass/warn/fail": f"{self.n_pass}/{self.n_warn}/{self.n_fail}",
        }


# ──────────────────────────────────────
# Vetting motoru
# ──────────────────────────────────────
class FalsePositiveVetter:
    """
    False positive vetting motoru.

    Birden fazla bağımsız testi uygulayarak
    False Positive Probability (FPP) tahmini üretir.

    Parameters
    ----------
    odd_even_threshold : float
        Odd-even mismatch eşiği (sigma).
    secondary_eclipse_threshold : float
        İkincil tutulma derinliği eşiği (transit derinliğinin oranı).
    max_depth_ratio : float
        Maksimum transit derinliği / Rp_max = 0.5 kontrolü.
    variability_amplitude_threshold : float
        Yıldız değişkenliği genliği eşiği (ppm).
    depth_variance_threshold : float
        Bireysel transit derinlikleri varyans eşiği.
    min_duration_period_ratio : float
        Minimum duration/period oranı (fiziksel tutarlılık).
    max_duration_period_ratio : float
        Maksimum duration/period oranı.
    """

    def __init__(
        self,
        odd_even_threshold: float = 3.0,
        secondary_eclipse_threshold: float = 0.5,
        max_depth_ratio: float = 0.5,
        variability_amplitude_threshold: float = 5000.0,
        depth_variance_threshold: float = 0.5,
        min_duration_period_ratio: float = 0.001,
        max_duration_period_ratio: float = 0.25,
    ):
        self.odd_even_threshold = odd_even_threshold
        self.secondary_eclipse_threshold = secondary_eclipse_threshold
        self.max_depth_ratio = max_depth_ratio
        self.variability_amplitude_threshold = variability_amplitude_threshold
        self.depth_variance_threshold = depth_variance_threshold
        self.min_duration_period_ratio = min_duration_period_ratio
        self.max_duration_period_ratio = max_duration_period_ratio

        logger.debug("FalsePositiveVetter başlatıldı.")

    def vet(
        self,
        candidate: CascadeCandidate,
        metrics: QualityMetrics,
    ) -> VettingReport:
        """
        Tüm vetting testlerini uygular.

        Parameters
        ----------
        candidate : CascadeCandidate
            Cascade tespit sonucu.
        metrics : QualityMetrics
            Kalite metrikleri.

        Returns
        -------
        VettingReport
            Kapsamlı vetting raporu.
        """

        target_id = candidate.target_id
        sector = candidate.sector

        logger.info(
            f"Vetting başlıyor — "
            f"{target_id} sektör {sector}"
        )

        tests = []

        # ── Test 1: Odd-Even Mismatch ──
        tests.append(self._test_odd_even(candidate, metrics))

        # ── Test 2: İkincil Tutulma ──
        tests.append(self._test_secondary_eclipse(candidate, metrics))

        # ── Test 3: Transit Derinliği Sınırı ──
        tests.append(self._test_depth_limit(candidate))

        # ── Test 4: Yıldız Değişkenliği ──
        tests.append(self._test_stellar_variability(metrics))

        # ── Test 5: Derinlik Varyansı ──
        tests.append(self._test_depth_variance(candidate, metrics))

        # ── Test 6: Süre-Periyot Fiziksel Tutarlılık ──
        tests.append(self._test_duration_period_ratio(candidate))

        # ── Test 7: Transit Simetri ──
        tests.append(self._test_transit_symmetry(metrics))

        # ── Test 8: Veri Tamlığı ──
        tests.append(self._test_data_completeness(metrics))

        # ── Özet istatistikler ──
        n_pass = sum(1 for t in tests if t.verdict == VettingVerdict.PASS)
        n_fail = sum(1 for t in tests if t.verdict == VettingVerdict.FAIL)
        n_warn = sum(1 for t in tests if t.verdict == VettingVerdict.WARN)

        # ── FPP hesabı ──
        fpp = self._compute_fpp(tests)

        # ── Kesin FP kararı ──
        fp_flags = [
            t.name for t in tests
            if t.verdict == VettingVerdict.FAIL
        ]
        is_fp = n_fail >= 2 or (fpp is not None and fpp > 0.5)

        report = VettingReport(
            target_id=target_id,
            sector=sector,
            tests=tests,
            n_pass=n_pass,
            n_fail=n_fail,
            n_warn=n_warn,
            false_positive_probability=fpp,
            is_false_positive=is_fp,
            fp_flags=fp_flags,
        )

        logger.info(
            f"Vetting tamamlandı — "
            f"{target_id}: "
            f"pass={n_pass}, warn={n_warn}, fail={n_fail}, "
            f"FPP={'NA' if fpp is None else f'{fpp:.3f}'}, "
            f"is_FP={is_fp}"
        )

        return report

    # ──────────────────────────────────────
    # Bireysel testler
    # ──────────────────────────────────────

    def _test_odd_even(
        self,
        candidate: CascadeCandidate,
        metrics: QualityMetrics,
    ) -> VettingTest:
        """Tek-çift transit derinlik farkı testi."""

        value = metrics.transit.odd_even_mismatch
        threshold = self.odd_even_threshold

        if value == 0.0:
            return VettingTest(
                name="odd_even_mismatch",
                verdict=VettingVerdict.SKIP,
                value=value,
                threshold=threshold,
                description="TLS sonucu yok, test atlandı.",
                fp_weight=0.2,
            )

        if value > threshold:
            verdict = VettingVerdict.FAIL
            desc = f"Odd-even mismatch yüksek: {value:.2f}σ > {threshold}σ (EB şüphesi)"
        elif value > threshold * 0.7:
            verdict = VettingVerdict.WARN
            desc = f"Odd-even mismatch uyarı: {value:.2f}σ"
        else:
            verdict = VettingVerdict.PASS
            desc = f"Odd-even mismatch normal: {value:.2f}σ"

        return VettingTest(
            name="odd_even_mismatch",
            verdict=verdict,
            value=value,
            threshold=threshold,
            description=desc,
            fp_weight=0.25,
        )

    def _test_secondary_eclipse(
        self,
        candidate: CascadeCandidate,
        metrics: QualityMetrics,
    ) -> VettingTest:
        """İkincil tutulma testi."""

        secondary_depth = metrics.stellar.secondary_eclipse_depth
        primary_depth = candidate.depth
        threshold_depth = primary_depth * self.secondary_eclipse_threshold

        if secondary_depth > threshold_depth and primary_depth > 0:
            verdict = VettingVerdict.FAIL
            ratio = secondary_depth / primary_depth if primary_depth > 0 else 0
            desc = (
                f"İkincil tutulma tespit edildi: "
                f"derinlik={secondary_depth * 1e6:.0f}ppm, "
                f"oran={ratio:.2f} (EB şüphesi)"
            )
        elif secondary_depth > threshold_depth * 0.5:
            verdict = VettingVerdict.WARN
            desc = f"İkincil tutulma uyarısı: {secondary_depth * 1e6:.0f}ppm"
        else:
            verdict = VettingVerdict.PASS
            desc = "İkincil tutulma tespit edilmedi."

        return VettingTest(
            name="secondary_eclipse",
            verdict=verdict,
            value=float(secondary_depth),
            threshold=float(threshold_depth),
            description=desc,
            fp_weight=0.25,
        )

    def _test_depth_limit(
        self,
        candidate: CascadeCandidate,
    ) -> VettingTest:
        """Transit derinliği fiziksel üst sınır testi."""

        depth = candidate.depth
        threshold = self.max_depth_ratio

        if depth > threshold:
            verdict = VettingVerdict.FAIL
            desc = (
                f"Transit çok derin: {depth:.4f} > {threshold} "
                f"(gezegen değil EB olabilir)"
            )
        elif depth > threshold * 0.8:
            verdict = VettingVerdict.WARN
            desc = f"Transit derin uyarı: {depth:.4f}"
        else:
            verdict = VettingVerdict.PASS
            desc = f"Transit derinliği normal: {depth * 1e6:.0f}ppm"

        return VettingTest(
            name="depth_limit",
            verdict=verdict,
            value=float(depth),
            threshold=float(threshold),
            description=desc,
            fp_weight=0.15,
        )

    def _test_stellar_variability(
        self,
        metrics: QualityMetrics,
    ) -> VettingTest:
        """Yıldız değişkenliği testi."""

        amplitude = metrics.stellar.variability_amplitude
        threshold = self.variability_amplitude_threshold

        if metrics.stellar.is_variable_star:
            if amplitude > threshold:
                verdict = VettingVerdict.FAIL
                desc = (
                    f"Yıldız değişkeni tespit edildi: "
                    f"genlik={amplitude:.0f}ppm > {threshold:.0f}ppm"
                )
            else:
                verdict = VettingVerdict.WARN
                desc = f"Yıldız değişken uyarı: genlik={amplitude:.0f}ppm"
        else:
            verdict = VettingVerdict.PASS
            desc = f"Yıldız sabit: genlik={amplitude:.0f}ppm"

        return VettingTest(
            name="stellar_variability",
            verdict=verdict,
            value=float(amplitude),
            threshold=float(threshold),
            description=desc,
            fp_weight=0.1,
        )

    def _test_depth_variance(
        self,
        candidate: CascadeCandidate,
        metrics: QualityMetrics,
    ) -> VettingTest:
        """Bireysel transit derinlikleri varyans testi."""

        depth_var = metrics.transit.depth_variance
        depth = candidate.depth

        if depth <= 0 or metrics.transit.n_transits < 3:
            return VettingTest(
                name="depth_variance",
                verdict=VettingVerdict.SKIP,
                value=float(depth_var),
                threshold=self.depth_variance_threshold,
                description="Yetersiz transit (<3), test atlandı.",
                fp_weight=0.1,
            )

        # Normalize varyans (derinliğe göre)
        norm_std = np.sqrt(depth_var) / depth if depth > 0 else 0.0
        threshold = self.depth_variance_threshold

        if norm_std > threshold:
            verdict = VettingVerdict.WARN
            desc = f"Transit derinliği değişken: normalize std={norm_std:.2f}"
        else:
            verdict = VettingVerdict.PASS
            desc = f"Transit derinliği tutarlı: normalize std={norm_std:.2f}"

        return VettingTest(
            name="depth_variance",
            verdict=verdict,
            value=float(norm_std),
            threshold=float(threshold),
            description=desc,
            fp_weight=0.1,
        )

    def _test_duration_period_ratio(
        self,
        candidate: CascadeCandidate,
    ) -> VettingTest:
        """Süre-periyot fiziksel tutarlılık testi."""

        if candidate.period <= 0:
            return VettingTest(
                name="duration_period_ratio",
                verdict=VettingVerdict.SKIP,
                value=0.0,
                threshold=self.max_duration_period_ratio,
                description="Geçersiz periyot.",
                fp_weight=0.1,
            )

        ratio = candidate.duration / candidate.period
        lo = self.min_duration_period_ratio
        hi = self.max_duration_period_ratio

        if ratio < lo or ratio > hi:
            verdict = VettingVerdict.FAIL
            desc = (
                f"Fiziksel dışı süre-periyot oranı: "
                f"{ratio:.4f} (beklenen: {lo:.4f}–{hi:.4f})"
            )
        else:
            verdict = VettingVerdict.PASS
            desc = f"Süre-periyot oranı fiziksel: {ratio:.4f}"

        return VettingTest(
            name="duration_period_ratio",
            verdict=verdict,
            value=float(ratio),
            threshold=float(hi),
            description=desc,
            fp_weight=0.1,
        )

    def _test_transit_symmetry(
        self,
        metrics: QualityMetrics,
    ) -> VettingTest:
        """Transit şekli simetri testi."""

        symmetry = metrics.transit.transit_symmetry
        threshold = 0.3

        if symmetry == 0.0:
            return VettingTest(
                name="transit_symmetry",
                verdict=VettingVerdict.SKIP,
                value=0.0,
                threshold=threshold,
                description="Simetri hesaplanamadı.",
                fp_weight=0.05,
            )

        if symmetry < threshold:
            verdict = VettingVerdict.WARN
            desc = f"Transit asimetrik: simetri={symmetry:.3f} < {threshold}"
        else:
            verdict = VettingVerdict.PASS
            desc = f"Transit simetrik: simetri={symmetry:.3f}"

        return VettingTest(
            name="transit_symmetry",
            verdict=verdict,
            value=float(symmetry),
            threshold=float(threshold),
            description=desc,
            fp_weight=0.05,
        )

    def _test_data_completeness(
        self,
        metrics: QualityMetrics,
    ) -> VettingTest:
        """Veri tamlığı testi."""

        completeness = metrics.photometric.data_completeness
        threshold = 0.7

        if completeness < threshold:
            verdict = VettingVerdict.WARN
            desc = f"Veri tamlığı düşük: {completeness:.1%} < {threshold:.0%}"
        else:
            verdict = VettingVerdict.PASS
            desc = f"Veri tamlığı yeterli: {completeness:.1%}"

        return VettingTest(
            name="data_completeness",
            verdict=verdict,
            value=float(completeness),
            threshold=float(threshold),
            description=desc,
            fp_weight=0.05,
        )

    @staticmethod
    def _compute_fpp(tests: list[VettingTest]) -> Optional[float]:
        """
        Test sonuçlarından **heuristik FPP proxy'si** üretir.

        Ağırlıklı ortalama yöntemi:
            Her FAIL test kendi fp_weight kadar FPP katkısı yapar.
            Her WARN test fp_weight × 0.3 kadar katkı yapar.
            PASS testler katkı yapmaz.

        Epistemik uyarı: Bu, popülasyon modeli veya kalibrasyon içermeyen
        bir risk indeksi değeridir (bkz. modül docstring'i). Sonucu
        "P(false positive)" olasılığı olarak değil, sıralama/tarama
        metriği olarak yorumlayın.

        Returns
        -------
        Optional[float]
            FPP proxy değeri (0-1); ölçülebilir test yoksa ``None``.
        """

        total_weight = sum(t.fp_weight for t in tests if t.verdict != VettingVerdict.SKIP)

        if total_weight <= 0:
            return None

        fpp_contribution = 0.0

        for test in tests:
            if test.verdict == VettingVerdict.FAIL:
                fpp_contribution += test.fp_weight
            elif test.verdict == VettingVerdict.WARN:
                fpp_contribution += test.fp_weight * 0.3

        fpp = fpp_contribution / total_weight
        return float(np.clip(fpp, 0.0, 1.0))
