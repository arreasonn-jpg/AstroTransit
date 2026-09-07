# astrotransit/quality/residual_analysis.py
"""
Transit içi residual analiz modülü.

Transit modeli çıkarıldıktan sonra kalan residual'ların
istatistiksel özelliklerini test eder.

Testler
-------
1. Shapiro-Wilk normallik testi          — residual dağılımı
2. In-transit / Out-of-transit RMS oranı — lokal gürültü artışı
3. Residual skewness                     — asimetrik hata yapısı
4. Residual kurtosis                     — kuyruk ağırlığı
5. Anderson-Darling testi                — dağılım uygunluğu

Çıktı
-----
ResidualReport dataclass — tüm metrikler + flag + özet
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from loguru import logger
from scipy import stats

from astrotransit.quality.vetting import VettingVerdict


# ──────────────────────────────────────────────────────────────
# Sabitler — eşikler
# ──────────────────────────────────────────────────────────────

# Shapiro-Wilk p-value altında → normallik şüphesi
_SW_WARN_THRESHOLD = 0.05
_SW_FAIL_THRESHOLD = 0.01

# In-transit RMS / Out-of-transit RMS oranı
_RMS_RATIO_WARN = 1.30
_RMS_RATIO_FAIL = 1.60

# Skewness mutlak değer
_SKEW_WARN = 0.75
_SKEW_FAIL = 1.25

# Kurtosis (excess) — normal dağılımda 0
_KURT_WARN = 1.50
_KURT_FAIL = 3.00

# Minimum transit noktası sayısı — test için gerekli
_MIN_INTRANSIT_POINTS = 5


# ──────────────────────────────────────────────────────────────
# Tek test sonucu
# ──────────────────────────────────────────────────────────────

@dataclass
class ResidualTest:
    """
    Tek bir residual testi sonucu.

    Attributes
    ----------
    name : str
        Test adı.
    verdict : VettingVerdict
        PASS / WARN / FAIL / SKIP
    value : float
        Ölçülen değer.
    warn_threshold : float
        Uyarı eşiği.
    fail_threshold : float
        Başarısızlık eşiği.
    description : str
        Kısa açıklama.
    """

    name: str
    verdict: VettingVerdict
    value: float
    warn_threshold: float
    fail_threshold: float
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "verdict": self.verdict.value,
            "value": round(float(self.value), 6),
            "warn_threshold": round(float(self.warn_threshold), 6),
            "fail_threshold": round(float(self.fail_threshold), 6),
            "description": self.description,
        }


# ──────────────────────────────────────────────────────────────
# Rapor
# ──────────────────────────────────────────────────────────────

@dataclass
class ResidualReport:
    """
    Tüm residual testlerinin özeti.

    Attributes
    ----------
    target_id : str
        TIC ID.
    sector : int
        Sektör numarası.
    n_intransit : int
        Transit içi nokta sayısı.
    n_outtransit : int
        Transit dışı nokta sayısı.
    tests : list[ResidualTest]
        Uygulanan testler.
    flag : str
        Genel residual kalite bayrağı.
        "CLEAN" | "SUSPECT" | "ANOMALOUS"
    score : float
        0 (temiz) → 1 (bozuk) arası özet skor.
    n_pass : int
    n_warn : int
    n_fail : int
    n_skip : int
    details : dict
        Ham metrik değerleri — downstream kullanım için.
    """

    target_id: str
    sector: int
    n_intransit: int = 0
    n_outtransit: int = 0
    tests: list[ResidualTest] = field(default_factory=list)
    flag: str = "UNKNOWN"
    score: float = 0.0
    n_pass: int = 0
    n_warn: int = 0
    n_fail: int = 0
    n_skip: int = 0
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "n_intransit": self.n_intransit,
            "n_outtransit": self.n_outtransit,
            "flag": self.flag,
            "score": round(float(self.score), 4),
            "n_pass": self.n_pass,
            "n_warn": self.n_warn,
            "n_fail": self.n_fail,
            "n_skip": self.n_skip,
            "details": {k: round(float(v), 6) if isinstance(v, float) else v
                        for k, v in self.details.items()},
            "tests": [t.to_dict() for t in self.tests],
        }

    def summary(self) -> str:
        return (
            f"{self.target_id} S{self.sector} | "
            f"flag={self.flag} score={self.score:.3f} | "
            f"pass={self.n_pass} warn={self.n_warn} "
            f"fail={self.n_fail} skip={self.n_skip}"
        )


# ──────────────────────────────────────────────────────────────
# Analizör
# ──────────────────────────────────────────────────────────────

class ResidualAnalyzer:
    """
    Transit residual analizörü.

    Kullanım
    --------
    >>> analyzer = ResidualAnalyzer()
    >>> report = analyzer.analyze(
    ...     target_id="TIC 347299560",
    ...     sector=24,
    ...     time=time_array,
    ...     residuals=residual_array,
    ...     in_transit_mask=mask,
    ... )
    >>> print(report.flag)
    'CLEAN'

    Parameters
    ----------
    sw_warn : float
        Shapiro-Wilk WARN p-value eşiği. Default 0.05.
    sw_fail : float
        Shapiro-Wilk FAIL p-value eşiği. Default 0.01.
    rms_ratio_warn : float
        In/Out RMS oranı WARN eşiği. Default 1.30.
    rms_ratio_fail : float
        In/Out RMS oranı FAIL eşiği. Default 1.60.
    skew_warn : float
        Skewness WARN eşiği (mutlak değer). Default 0.75.
    skew_fail : float
        Skewness FAIL eşiği (mutlak değer). Default 1.25.
    kurt_warn : float
        Excess kurtosis WARN eşiği. Default 1.50.
    kurt_fail : float
        Excess kurtosis FAIL eşiği. Default 3.00.
    """

    def __init__(
        self,
        sw_warn: float = _SW_WARN_THRESHOLD,
        sw_fail: float = _SW_FAIL_THRESHOLD,
        rms_ratio_warn: float = _RMS_RATIO_WARN,
        rms_ratio_fail: float = _RMS_RATIO_FAIL,
        skew_warn: float = _SKEW_WARN,
        skew_fail: float = _SKEW_FAIL,
        kurt_warn: float = _KURT_WARN,
        kurt_fail: float = _KURT_FAIL,
    ):
        self.sw_warn = sw_warn
        self.sw_fail = sw_fail
        self.rms_ratio_warn = rms_ratio_warn
        self.rms_ratio_fail = rms_ratio_fail
        self.skew_warn = skew_warn
        self.skew_fail = skew_fail
        self.kurt_warn = kurt_warn
        self.kurt_fail = kurt_fail

        logger.debug("ResidualAnalyzer başlatıldı.")

    # ──────────────────────────────────────
    # Ana metod
    # ──────────────────────────────────────

    def analyze(
        self,
        target_id: str,
        sector: int,
        time: np.ndarray,
        residuals: np.ndarray,
        in_transit_mask: np.ndarray,
    ) -> ResidualReport:
        """
        Transit residual analizini çalıştırır.

        Parameters
        ----------
        target_id : str
            TIC ID, loglama için.
        sector : int
            Sektör numarası.
        time : np.ndarray
            Zaman dizisi (BJD veya BTJD).
        residuals : np.ndarray
            Model çıkarılmış flux residual'ları.
            Transit modeli: observed - model_flux
        in_transit_mask : np.ndarray
            Boolean maske — True = transit içi nokta.

        Returns
        -------
        ResidualReport
            Tam residual analiz raporu.

        Notes
        -----
        in_transit_mask, time ile aynı boyutta olmalı.
        residuals içinde NaN varsa otomatik temizlenir.
        """

        logger.info(
            f"Residual analizi başlıyor — "
            f"{target_id} S{sector}"
        )

        # ── Temizlik ──
        valid = np.isfinite(residuals) & np.isfinite(time)
        time_clean = time[valid]
        res_clean = residuals[valid]
        mask_clean = in_transit_mask[valid]

        in_res = res_clean[mask_clean]
        out_res = res_clean[~mask_clean]

        n_in = len(in_res)
        n_out = len(out_res)

        logger.debug(
            f"{target_id}: "
            f"n_intransit={n_in}, n_outtransit={n_out}"
        )

        tests: list[ResidualTest] = []

        # ── Test 1: Shapiro-Wilk normallik ──
        tests.append(self._test_shapiro_wilk(in_res, n_in))

        # ── Test 2: In/Out RMS oranı ──
        tests.append(self._test_rms_ratio(in_res, out_res, n_in))

        # ── Test 3: Skewness ──
        tests.append(self._test_skewness(in_res, n_in))

        # ── Test 4: Kurtosis ──
        tests.append(self._test_kurtosis(in_res, n_in))

        # ── Test 5: Anderson-Darling ──
        tests.append(self._test_anderson_darling(in_res, n_in))

        # ── İstatistikler ──
        n_pass = sum(1 for t in tests if t.verdict == VettingVerdict.PASS)
        n_warn = sum(1 for t in tests if t.verdict == VettingVerdict.WARN)
        n_fail = sum(1 for t in tests if t.verdict == VettingVerdict.FAIL)
        n_skip = sum(1 for t in tests if t.verdict == VettingVerdict.SKIP)

        # ── Ham metrikler ──
        details = self._compute_details(in_res, out_res, n_in)

        # ── Birleşik skor ──
        score = self._compute_score(tests)

        # ── Flag ──
        flag = self._compute_flag(score, n_fail)

        report = ResidualReport(
            target_id=target_id,
            sector=sector,
            n_intransit=n_in,
            n_outtransit=n_out,
            tests=tests,
            flag=flag,
            score=score,
            n_pass=n_pass,
            n_warn=n_warn,
            n_fail=n_fail,
            n_skip=n_skip,
            details=details,
        )

        logger.info(
            f"Residual analizi tamamlandı — {report.summary()}"
        )

        return report

    # ──────────────────────────────────────
    # Bireysel testler
    # ──────────────────────────────────────

    def _test_shapiro_wilk(
        self,
        in_res: np.ndarray,
        n_in: int,
    ) -> ResidualTest:
        """
        Shapiro-Wilk normallik testi.

        Düşük p-value → residual normal dağılmıyor
        → sistematik hata / model uyuşmazlığı.

        Shapiro-Wilk 3–5000 nokta arasında güvenilir.
        N > 5000 için Lilliefors'a geçilebilir ama
        transit içi bu kadar nokta nadiren olur.
        """

        name = "shapiro_wilk_normality"

        if n_in < _MIN_INTRANSIT_POINTS:
            return ResidualTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.sw_warn,
                fail_threshold=self.sw_fail,
                description=f"Yetersiz transit içi nokta: {n_in} < {_MIN_INTRANSIT_POINTS}",
            )

        # Shapiro-Wilk 5000'den fazla noktada güvenilir değil
        # Transit içi bu kadar nokta pratikte olamaz ama savunmacı ol
        sample = in_res if n_in <= 5000 else in_res[:5000]

        try:
            stat, p_value = stats.shapiro(sample)
        except Exception as exc:
            logger.warning(f"Shapiro-Wilk hatası: {exc}")
            return ResidualTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.sw_warn,
                fail_threshold=self.sw_fail,
                description=f"Shapiro-Wilk hesaplanamadı: {exc}",
            )

        if p_value < self.sw_fail:
            verdict = VettingVerdict.FAIL
            desc = (
                f"Residual normal dağılmıyor: "
                f"p={p_value:.4f} < {self.sw_fail} "
                f"(sistematik hata şüphesi)"
            )
        elif p_value < self.sw_warn:
            verdict = VettingVerdict.WARN
            desc = f"Residual normallik uyarısı: p={p_value:.4f}"
        else:
            verdict = VettingVerdict.PASS
            desc = f"Residual normal dağılıyor: p={p_value:.4f}"

        return ResidualTest(
            name=name,
            verdict=verdict,
            value=float(p_value),
            warn_threshold=self.sw_warn,
            fail_threshold=self.sw_fail,
            description=desc,
        )

    def _test_rms_ratio(
        self,
        in_res: np.ndarray,
        out_res: np.ndarray,
        n_in: int,
    ) -> ResidualTest:
        """
        In-transit / Out-of-transit RMS oranı.

        Transit içindeki gürültü transit dışına göre
        anlamlı derecede yüksekse → model uyumsuzluğu
        veya transit event'in kendisi bozuk.

        Oran = 1.0 → mükemmel (gürültü eşit)
        Oran > 1.5 → şüpheli
        Oran > 1.6 → başarısız
        """

        name = "rms_ratio_in_out"

        if n_in < _MIN_INTRANSIT_POINTS:
            return ResidualTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.rms_ratio_warn,
                fail_threshold=self.rms_ratio_fail,
                description=f"Yetersiz transit içi nokta: {n_in}",
            )

        if len(out_res) < _MIN_INTRANSIT_POINTS:
            return ResidualTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.rms_ratio_warn,
                fail_threshold=self.rms_ratio_fail,
                description="Yetersiz transit dışı nokta.",
            )

        rms_in = float(np.sqrt(np.mean(in_res ** 2)))
        rms_out = float(np.sqrt(np.mean(out_res ** 2)))

        if rms_out < 1e-12:
            return ResidualTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.rms_ratio_warn,
                fail_threshold=self.rms_ratio_fail,
                description="Transit dışı RMS sıfıra çok yakın.",
            )

        ratio = rms_in / rms_out

        if ratio > self.rms_ratio_fail:
            verdict = VettingVerdict.FAIL
            desc = (
                f"In-transit gürültü anormal yüksek: "
                f"RMS oran={ratio:.3f} > {self.rms_ratio_fail}"
            )
        elif ratio > self.rms_ratio_warn:
            verdict = VettingVerdict.WARN
            desc = f"In-transit gürültü uyarısı: RMS oran={ratio:.3f}"
        else:
            verdict = VettingVerdict.PASS
            desc = f"In-transit gürültü normal: RMS oran={ratio:.3f}"

        return ResidualTest(
            name=name,
            verdict=verdict,
            value=ratio,
            warn_threshold=self.rms_ratio_warn,
            fail_threshold=self.rms_ratio_fail,
            description=desc,
        )

    def _test_skewness(
        self,
        in_res: np.ndarray,
        n_in: int,
    ) -> ResidualTest:
        """
        Residual skewness testi.

        Yüksek skewness → transit içi residual'lar asimetrik
        → transit şekli model tarafından tam yakalanmıyor
        veya sistematik flux kayması var.
        """

        name = "residual_skewness"

        if n_in < _MIN_INTRANSIT_POINTS:
            return ResidualTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.skew_warn,
                fail_threshold=self.skew_fail,
                description=f"Yetersiz nokta: {n_in}",
            )

        skew = float(stats.skew(in_res))
        abs_skew = abs(skew)

        if abs_skew > self.skew_fail:
            verdict = VettingVerdict.FAIL
            desc = (
                f"Residual ciddi asimetri: "
                f"skewness={skew:.3f} (|s|>{self.skew_fail})"
            )
        elif abs_skew > self.skew_warn:
            verdict = VettingVerdict.WARN
            desc = f"Residual asimetri uyarısı: skewness={skew:.3f}"
        else:
            verdict = VettingVerdict.PASS
            desc = f"Residual simetrik: skewness={skew:.3f}"

        return ResidualTest(
            name=name,
            verdict=verdict,
            value=skew,
            warn_threshold=self.skew_warn,
            fail_threshold=self.skew_fail,
            description=desc,
        )

    def _test_kurtosis(
        self,
        in_res: np.ndarray,
        n_in: int,
    ) -> ResidualTest:
        """
        Residual excess kurtosis testi.

        Normal dağılımda excess kurtosis = 0.
        Yüksek kurtosis → ağır kuyruklar → outlier event'ler var
        → transit içinde beklenmedik flux sapmaları.
        """

        name = "residual_kurtosis"

        if n_in < _MIN_INTRANSIT_POINTS:
            return ResidualTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.kurt_warn,
                fail_threshold=self.kurt_fail,
                description=f"Yetersiz nokta: {n_in}",
            )

        # scipy.stats.kurtosis → excess kurtosis (normal=0)
        kurt = float(stats.kurtosis(in_res))

        if kurt > self.kurt_fail:
            verdict = VettingVerdict.FAIL
            desc = (
                f"Residual ağır kuyruklu: "
                f"excess kurtosis={kurt:.3f} > {self.kurt_fail}"
            )
        elif kurt > self.kurt_warn:
            verdict = VettingVerdict.WARN
            desc = f"Residual kurtosis uyarısı: {kurt:.3f}"
        else:
            verdict = VettingVerdict.PASS
            desc = f"Residual kurtosis normal: {kurt:.3f}"

        return ResidualTest(
            name=name,
            verdict=verdict,
            value=kurt,
            warn_threshold=self.kurt_warn,
            fail_threshold=self.kurt_fail,
            description=desc,
        )

    def _test_anderson_darling(
        self,
        in_res: np.ndarray,
        n_in: int,
    ) -> ResidualTest:
        """
        Anderson-Darling normallik testi.

        Shapiro-Wilk'e tamamlayıcı — özellikle
        dağılım kuyruklarını daha hassas test eder.

        scipy `anderson` → kritik değerler %15, %10, %5, %2.5, %1
        için döner. %5 anlamlılık seviyesini (index 2) kullanıyoruz.
        """

        name = "anderson_darling_normality"

        if n_in < _MIN_INTRANSIT_POINTS:
            return ResidualTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=0.0,
                fail_threshold=0.0,
                description=f"Yetersiz nokta: {n_in}",
            )

        try:
            result = stats.anderson(in_res, dist="norm")
        except Exception as exc:
            logger.warning(f"Anderson-Darling hatası: {exc}")
            return ResidualTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=0.0,
                fail_threshold=0.0,
                description=f"Anderson-Darling hesaplanamadı: {exc}",
            )

        stat = float(result.statistic)

        # Kritik değerler: [%15, %10, %5, %2.5, %1]
        # idx=2 → %5, idx=4 → %1
        crit_5pct = float(result.critical_values[2])
        crit_1pct = float(result.critical_values[4])

        if stat > crit_1pct:
            verdict = VettingVerdict.FAIL
            desc = (
                f"Anderson-Darling: normal değil (stat={stat:.3f} > "
                f"crit_1%={crit_1pct:.3f})"
            )
        elif stat > crit_5pct:
            verdict = VettingVerdict.WARN
            desc = (
                f"Anderson-Darling uyarı: stat={stat:.3f} > "
                f"crit_5%={crit_5pct:.3f}"
            )
        else:
            verdict = VettingVerdict.PASS
            desc = f"Anderson-Darling normal: stat={stat:.3f}"

        return ResidualTest(
            name=name,
            verdict=verdict,
            value=stat,
            warn_threshold=crit_5pct,
            fail_threshold=crit_1pct,
            description=desc,
        )

    # ──────────────────────────────────────
    # Yardımcı metodlar
    # ──────────────────────────────────────

    @staticmethod
    def _compute_details(
        in_res: np.ndarray,
        out_res: np.ndarray,
        n_in: int,
    ) -> dict:
        """Ham metrik değerlerini toplar — downstream için."""

        details: dict = {
            "n_intransit": n_in,
            "n_outtransit": len(out_res),
        }

        if n_in >= _MIN_INTRANSIT_POINTS:
            details["intransit_rms"] = float(np.sqrt(np.mean(in_res ** 2)))
            details["intransit_mean"] = float(np.mean(in_res))
            details["intransit_std"] = float(np.std(in_res))
            details["intransit_skewness"] = float(stats.skew(in_res))
            details["intransit_kurtosis"] = float(stats.kurtosis(in_res))
            details["intransit_min"] = float(np.min(in_res))
            details["intransit_max"] = float(np.max(in_res))
            details["intransit_p5"] = float(np.percentile(in_res, 5))
            details["intransit_p95"] = float(np.percentile(in_res, 95))

        if len(out_res) >= _MIN_INTRANSIT_POINTS:
            details["outtransit_rms"] = float(np.sqrt(np.mean(out_res ** 2)))
            details["outtransit_std"] = float(np.std(out_res))

        if (n_in >= _MIN_INTRANSIT_POINTS
                and len(out_res) >= _MIN_INTRANSIT_POINTS
                and details.get("outtransit_rms", 0) > 1e-12):
            details["rms_ratio"] = (
                details["intransit_rms"] / details["outtransit_rms"]
            )

        return details

    @staticmethod
    def _compute_score(tests: list[ResidualTest]) -> float:
        """
        Ağırlıklı anomaly skoru — 0 (temiz) → 1 (bozuk).

        FAIL  → 1.0 katkı
        WARN  → 0.4 katkı
        PASS  → 0.0 katkı
        SKIP  → sayılmaz

        Test ağırlıkları eşit — 5 test, her biri 1/5.
        """

        active = [t for t in tests if t.verdict != VettingVerdict.SKIP]

        if not active:
            return 0.0

        score_map = {
            VettingVerdict.FAIL: 1.0,
            VettingVerdict.WARN: 0.4,
            VettingVerdict.PASS: 0.0,
        }

        total = sum(score_map.get(t.verdict, 0.0) for t in active)
        return float(np.clip(total / len(active), 0.0, 1.0))

    @staticmethod
    def _compute_flag(score: float, n_fail: int) -> str:
        """
        Genel residual kalite bayrağı.

        CLEAN     : score < 0.25 ve n_fail == 0
        SUSPECT   : 0.25 ≤ score < 0.60 veya n_fail == 1
        ANOMALOUS : score ≥ 0.60 veya n_fail ≥ 2
        """

        if n_fail >= 2 or score >= 0.60:
            return "ANOMALOUS"
        elif n_fail == 1 or score >= 0.25:
            return "SUSPECT"
        else:
            return "CLEAN"
