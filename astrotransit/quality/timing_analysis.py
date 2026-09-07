# astrotransit/quality/timing_analysis.py
"""
Transit timing anomaly analiz modülü.

Amaç
----
Bireysel transit orta-zamanlarının (mid-transit times),
lineer efemeristen beklenen zamanlarla uyumunu test etmek.

Uygulanan testler
-----------------
1. O-C RMS testi                 — genel zamanlama saçılması
2. Max |O-C| testi               — tekil büyük sapma
3. Lineer trend testi            — efemeris/periyot kayması

Çıktı
-----
TimingReport
    flag: "STABLE" | "TTV_CANDIDATE" | "TIMING_UNSTABLE" | "UNKNOWN"
    score: 0.0 → 1.0 arası anomaly skoru

Notlar
------
- O-C = observed - calculated
- İç zaman birimi gün, raporlama çoğunlukla dakika cinsinden yapılır
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from loguru import logger
from scipy import stats

from astrotransit.quality.vetting import VettingVerdict


# ──────────────────────────────────────────────────────────────
# Sabitler / eşikler
# ──────────────────────────────────────────────────────────────

_MIN_TRANSITS_FOR_RMS = 2
_MIN_TRANSITS_FOR_TREND = 3

# Dakika cinsinden eşikler
_OC_RMS_WARN_MIN = 15.0
_OC_RMS_FAIL_MIN = 30.0

_MAX_OC_WARN_MIN = 20.0
_MAX_OC_FAIL_MIN = 40.0

# Gözlem baseline boyunca toplam drift (dakika)
_TREND_DRIFT_WARN_MIN = 10.0
_TREND_DRIFT_FAIL_MIN = 25.0

# Trend anlamlılık eşiği
_TREND_P_WARN = 0.10
_TREND_P_FAIL = 0.05


# ──────────────────────────────────────────────────────────────
# Yardımcılar
# ──────────────────────────────────────────────────────────────

def _days_to_minutes(x: float | np.ndarray) -> float | np.ndarray:
    return x * 24.0 * 60.0


def _minutes_to_days(x: float) -> float:
    return x / (24.0 * 60.0)


# ──────────────────────────────────────────────────────────────
# Tek test sonucu
# ──────────────────────────────────────────────────────────────

@dataclass
class TimingTest:
    """Tek bir timing testi sonucu."""

    name: str
    verdict: VettingVerdict
    value: float
    warn_threshold: float
    fail_threshold: float
    unit: str = ""
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "verdict": self.verdict.value,
            "value": round(float(self.value), 6),
            "warn_threshold": round(float(self.warn_threshold), 6),
            "fail_threshold": round(float(self.fail_threshold), 6),
            "unit": self.unit,
            "description": self.description,
        }


# ──────────────────────────────────────────────────────────────
# Rapor
# ──────────────────────────────────────────────────────────────

@dataclass
class TimingReport:
    """
    Transit timing analiz raporu.
    """

    target_id: str
    sector: int
    n_transits: int = 0
    tests: list[TimingTest] = field(default_factory=list)
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
            "n_transits": self.n_transits,
            "flag": self.flag,
            "score": round(float(self.score), 4),
            "n_pass": self.n_pass,
            "n_warn": self.n_warn,
            "n_fail": self.n_fail,
            "n_skip": self.n_skip,
            "details": self.details,
            "tests": [t.to_dict() for t in self.tests],
        }

    def summary(self) -> str:
        return (
            f"{self.target_id} S{self.sector} | "
            f"flag={self.flag} score={self.score:.3f} | "
            f"pass={self.n_pass} warn={self.n_warn} "
            f"fail={self.n_fail} skip={self.n_skip} | "
            f"n_transits={self.n_transits}"
        )


# ──────────────────────────────────────────────────────────────
# Analizör
# ──────────────────────────────────────────────────────────────

class TimingAnalyzer:
    """
    Transit timing anomaly analizörü.

    Kullanım yolları
    ----------------
    1) Doğrudan O-C dizisi verirsen:
        analyze(..., period=P, oc_values=oc_days)

    2) Gözlenen transit zamanları verirsen:
        analyze(..., period=P, observed_midtimes=t_obs, ...)

    Parameters
    ----------
    oc_rms_warn_min, oc_rms_fail_min : float
        O-C RMS eşikleri (dakika).
    max_oc_warn_min, max_oc_fail_min : float
        Max |O-C| eşikleri (dakika).
    trend_drift_warn_min, trend_drift_fail_min : float
        Gözlem baseline boyunca toplam O-C drift eşikleri (dakika).
    trend_p_warn, trend_p_fail : float
        Lineer trend anlamlılık p-value eşikleri.
    """

    def __init__(
        self,
        oc_rms_warn_min: float = _OC_RMS_WARN_MIN,
        oc_rms_fail_min: float = _OC_RMS_FAIL_MIN,
        max_oc_warn_min: float = _MAX_OC_WARN_MIN,
        max_oc_fail_min: float = _MAX_OC_FAIL_MIN,
        trend_drift_warn_min: float = _TREND_DRIFT_WARN_MIN,
        trend_drift_fail_min: float = _TREND_DRIFT_FAIL_MIN,
        trend_p_warn: float = _TREND_P_WARN,
        trend_p_fail: float = _TREND_P_FAIL,
    ):
        self.oc_rms_warn_min = oc_rms_warn_min
        self.oc_rms_fail_min = oc_rms_fail_min
        self.max_oc_warn_min = max_oc_warn_min
        self.max_oc_fail_min = max_oc_fail_min
        self.trend_drift_warn_min = trend_drift_warn_min
        self.trend_drift_fail_min = trend_drift_fail_min
        self.trend_p_warn = trend_p_warn
        self.trend_p_fail = trend_p_fail

        logger.debug("TimingAnalyzer başlatıldı.")

    def analyze(
        self,
        target_id: str,
        sector: int,
        period: float,
        observed_midtimes: Optional[np.ndarray] = None,
        transit_numbers: Optional[np.ndarray] = None,
        t0: Optional[float] = None,
        oc_values: Optional[np.ndarray] = None,
    ) -> TimingReport:
        """
        Transit timing analizini çalıştırır.

        Parameters
        ----------
        target_id : str
            TIC ID.
        sector : int
            Sektör numarası.
        period : float
            Transit periyodu (gün).
        observed_midtimes : np.ndarray, optional
            Gözlenen mid-transit zamanları (gün).
        transit_numbers : np.ndarray, optional
            Transit indeksleri / epoch numaraları.
            Verilmezse otomatik türetilir.
        t0 : float, optional
            Referans epoch (gün).
            Verilmezse robust şekilde tahmin edilir.
        oc_values : np.ndarray, optional
            Doğrudan O-C değerleri (gün). Verilirse observed_midtimes yerine kullanılır.

        Returns
        -------
        TimingReport
        """

        logger.info(f"Timing analizi başlıyor — {target_id} S{sector}")

        resolved = self._resolve_oc_series(
            period=period,
            observed_midtimes=observed_midtimes,
            transit_numbers=transit_numbers,
            t0=t0,
            oc_values=oc_values,
        )

        oc_days = resolved["oc_days"]
        epochs = resolved["epochs"]
        expected_midtimes = resolved["expected_midtimes"]
        observed_used = resolved["observed_midtimes"]
        t0_used = resolved["t0_used"]

        tests: list[TimingTest] = []
        tests.append(self._test_oc_rms(oc_days))
        tests.append(self._test_max_abs_oc(oc_days))
        tests.append(self._test_linear_trend(epochs, oc_days))

        n_pass = sum(1 for t in tests if t.verdict == VettingVerdict.PASS)
        n_warn = sum(1 for t in tests if t.verdict == VettingVerdict.WARN)
        n_fail = sum(1 for t in tests if t.verdict == VettingVerdict.FAIL)
        n_skip = sum(1 for t in tests if t.verdict == VettingVerdict.SKIP)

        details = self._compute_details(
            period=period,
            epochs=epochs,
            oc_days=oc_days,
            observed_midtimes=observed_used,
            expected_midtimes=expected_midtimes,
            t0_used=t0_used,
        )

        score = self._compute_score(tests)
        flag = self._compute_flag(
            tests=tests,
            score=score,
            n_fail=n_fail,
            n_warn=n_warn,
        )

        report = TimingReport(
            target_id=target_id,
            sector=sector,
            n_transits=len(oc_days),
            tests=tests,
            flag=flag,
            score=score,
            n_pass=n_pass,
            n_warn=n_warn,
            n_fail=n_fail,
            n_skip=n_skip,
            details=details,
        )

        logger.info(f"Timing analizi tamamlandı — {report.summary()}")
        return report

    # ──────────────────────────────────────
    # Bireysel testler
    # ──────────────────────────────────────

    def _test_oc_rms(
        self,
        oc_days: np.ndarray,
    ) -> TimingTest:
        """
        O-C RMS testi.

        Genel zamanlama saçılmasını ölçer.
        """

        name = "oc_rms"

        if len(oc_days) < _MIN_TRANSITS_FOR_RMS:
            return TimingTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.oc_rms_warn_min,
                fail_threshold=self.oc_rms_fail_min,
                unit="min",
                description="RMS testi için yetersiz transit sayısı (<2).",
            )

        rms_days = float(np.sqrt(np.mean(oc_days ** 2)))
        rms_min = float(_days_to_minutes(rms_days))

        if rms_min > self.oc_rms_fail_min:
            verdict = VettingVerdict.FAIL
            desc = f"O-C RMS yüksek: {rms_min:.2f} min > {self.oc_rms_fail_min:.2f} min"
        elif rms_min > self.oc_rms_warn_min:
            verdict = VettingVerdict.WARN
            desc = f"O-C RMS uyarısı: {rms_min:.2f} min"
        else:
            verdict = VettingVerdict.PASS
            desc = f"O-C RMS stabil: {rms_min:.2f} min"

        return TimingTest(
            name=name,
            verdict=verdict,
            value=rms_min,
            warn_threshold=self.oc_rms_warn_min,
            fail_threshold=self.oc_rms_fail_min,
            unit="min",
            description=desc,
        )

    def _test_max_abs_oc(
        self,
        oc_days: np.ndarray,
    ) -> TimingTest:
        """
        Maksimum mutlak O-C testi.

        Tek bir transitte aşırı kayma varsa yakalar.
        """

        name = "max_abs_oc"

        if len(oc_days) < 1:
            return TimingTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.max_oc_warn_min,
                fail_threshold=self.max_oc_fail_min,
                unit="min",
                description="O-C serisi boş.",
            )

        max_abs_days = float(np.max(np.abs(oc_days)))
        max_abs_min = float(_days_to_minutes(max_abs_days))

        if max_abs_min > self.max_oc_fail_min:
            verdict = VettingVerdict.FAIL
            desc = f"Max |O-C| yüksek: {max_abs_min:.2f} min > {self.max_oc_fail_min:.2f} min"
        elif max_abs_min > self.max_oc_warn_min:
            verdict = VettingVerdict.WARN
            desc = f"Max |O-C| uyarısı: {max_abs_min:.2f} min"
        else:
            verdict = VettingVerdict.PASS
            desc = f"Max |O-C| normal: {max_abs_min:.2f} min"

        return TimingTest(
            name=name,
            verdict=verdict,
            value=max_abs_min,
            warn_threshold=self.max_oc_warn_min,
            fail_threshold=self.max_oc_fail_min,
            unit="min",
            description=desc,
        )

    def _test_linear_trend(
        self,
        epochs: np.ndarray,
        oc_days: np.ndarray,
    ) -> TimingTest:
        """
        O-C serisinde lineer trend testi.

        slope birimi = gün / epoch
        drift = slope * epoch_span → toplam zamanlama kayması
        """

        name = "linear_ephemeris_trend"

        if len(oc_days) < _MIN_TRANSITS_FOR_TREND or len(epochs) < _MIN_TRANSITS_FOR_TREND:
            return TimingTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.trend_drift_warn_min,
                fail_threshold=self.trend_drift_fail_min,
                unit="min",
                description="Trend testi için yetersiz transit sayısı (<3).",
            )

        if np.allclose(epochs, epochs[0]):
            return TimingTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.trend_drift_warn_min,
                fail_threshold=self.trend_drift_fail_min,
                unit="min",
                description="Epoch span sıfır.",
            )

        try:
            fit = stats.linregress(epochs, oc_days)
        except Exception as exc:
            logger.warning(f"Timing linear trend hatası: {exc}")
            return TimingTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.trend_drift_warn_min,
                fail_threshold=self.trend_drift_fail_min,
                unit="min",
                description=f"Trend fit hesaplanamadı: {exc}",
            )

        epoch_span = float(np.max(epochs) - np.min(epochs))
        drift_days = abs(float(fit.slope)) * epoch_span
        drift_min = float(_days_to_minutes(drift_days))
        p_value = float(fit.pvalue)

        if drift_min > self.trend_drift_fail_min and p_value < self.trend_p_fail:
            verdict = VettingVerdict.FAIL
            desc = (
                f"Anlamlı lineer O-C trendi: drift={drift_min:.2f} min, "
                f"p={p_value:.4f}"
            )
        elif drift_min > self.trend_drift_warn_min and p_value < self.trend_p_warn:
            verdict = VettingVerdict.WARN
            desc = (
                f"O-C trend uyarısı: drift={drift_min:.2f} min, "
                f"p={p_value:.4f}"
            )
        elif drift_min > self.trend_drift_fail_min:
            verdict = VettingVerdict.WARN
            desc = (
                f"Büyük ama düşük anlamlı trend: drift={drift_min:.2f} min, "
                f"p={p_value:.4f}"
            )
        else:
            verdict = VettingVerdict.PASS
            desc = f"Lineer O-C trendi zayıf: drift={drift_min:.2f} min, p={p_value:.4f}"

        return TimingTest(
            name=name,
            verdict=verdict,
            value=drift_min,
            warn_threshold=self.trend_drift_warn_min,
            fail_threshold=self.trend_drift_fail_min,
            unit="min",
            description=desc,
        )

    # ──────────────────────────────────────
    # Seri çözümleme
    # ──────────────────────────────────────

    def _resolve_oc_series(
        self,
        period: float,
        observed_midtimes: Optional[np.ndarray],
        transit_numbers: Optional[np.ndarray],
        t0: Optional[float],
        oc_values: Optional[np.ndarray],
    ) -> dict:
        """
        O-C serisini farklı giriş türlerinden üretir.
        """

        if period <= 0:
            logger.warning("TimingAnalyzer: geçersiz period <= 0, boş seri döndürülüyor.")
            return {
                "oc_days": np.array([], dtype=float),
                "epochs": np.array([], dtype=float),
                "expected_midtimes": np.array([], dtype=float),
                "observed_midtimes": np.array([], dtype=float),
                "t0_used": None,
            }

        # Yol 1: O-C doğrudan verilmiş
        if oc_values is not None:
            oc_arr = np.asarray(oc_values, dtype=float)
            valid = np.isfinite(oc_arr)
            oc_arr = oc_arr[valid]

            if transit_numbers is not None:
                ep = np.asarray(transit_numbers, dtype=float)
                if len(ep) == len(valid):
                    ep = ep[valid]
                else:
                    logger.warning("transit_numbers uzunluğu oc_values ile eşleşmiyor; sıralı epoch atanıyor.")
                    ep = np.arange(len(oc_arr), dtype=float)
            else:
                ep = np.arange(len(oc_arr), dtype=float)

            return {
                "oc_days": oc_arr,
                "epochs": ep,
                "expected_midtimes": np.array([], dtype=float),
                "observed_midtimes": np.array([], dtype=float),
                "t0_used": t0,
            }

        # Yol 2: observed midtimes verilmiş
        if observed_midtimes is None:
            logger.warning("TimingAnalyzer: observed_midtimes veya oc_values sağlanmadı.")
            return {
                "oc_days": np.array([], dtype=float),
                "epochs": np.array([], dtype=float),
                "expected_midtimes": np.array([], dtype=float),
                "observed_midtimes": np.array([], dtype=float),
                "t0_used": t0,
            }

        obs = np.asarray(observed_midtimes, dtype=float)
        valid = np.isfinite(obs)
        obs = obs[valid]

        if len(obs) == 0:
            return {
                "oc_days": np.array([], dtype=float),
                "epochs": np.array([], dtype=float),
                "expected_midtimes": np.array([], dtype=float),
                "observed_midtimes": np.array([], dtype=float),
                "t0_used": t0,
            }

        if transit_numbers is not None:
            ep = np.asarray(transit_numbers, dtype=float)
            if len(ep) == len(valid):
                ep = ep[valid]
            elif len(ep) == len(obs):
                ep = ep.astype(float)
            else:
                logger.warning("transit_numbers uzunluğu observed_midtimes ile eşleşmiyor; otomatik türetilecek.")
                ep = None
        else:
            ep = None

        # epoch yoksa otomatik türet
        if ep is None:
            base_t0 = float(t0) if t0 is not None else float(obs[0])
            ep = np.rint((obs - base_t0) / period).astype(float)

        # t0 yoksa robust tahmin
        if t0 is None:
            t0_used = float(np.median(obs - ep * period))
        else:
            t0_used = float(t0)

        expected = t0_used + ep * period
        oc_days = obs - expected

        sorter = np.argsort(ep)
        ep = ep[sorter]
        obs = obs[sorter]
        expected = expected[sorter]
        oc_days = oc_days[sorter]

        return {
            "oc_days": oc_days,
            "epochs": ep,
            "expected_midtimes": expected,
            "observed_midtimes": obs,
            "t0_used": t0_used,
        }

    # ──────────────────────────────────────
    # Yardımcılar
    # ──────────────────────────────────────

    def _compute_details(
        self,
        period: float,
        epochs: np.ndarray,
        oc_days: np.ndarray,
        observed_midtimes: np.ndarray,
        expected_midtimes: np.ndarray,
        t0_used: Optional[float],
    ) -> dict:
        """
        Downstream kullanım için detay sözlüğü.
        """

        details: dict = {
            "period_days": float(period),
            "t0_used": None if t0_used is None else float(t0_used),
            "n_transits": int(len(oc_days)),
            "epochs": [float(x) for x in epochs.tolist()],
            "oc_days": [float(x) for x in oc_days.tolist()],
            "oc_minutes": [float(x) for x in _days_to_minutes(oc_days).tolist()],
        }

        if len(observed_midtimes) > 0:
            details["observed_midtimes"] = [float(x) for x in observed_midtimes.tolist()]
        if len(expected_midtimes) > 0:
            details["expected_midtimes"] = [float(x) for x in expected_midtimes.tolist()]

        if len(oc_days) >= 1:
            oc_min = _days_to_minutes(oc_days)
            details["max_abs_oc_min"] = float(np.max(np.abs(oc_min)))
            details["median_abs_oc_min"] = float(np.median(np.abs(oc_min)))

        if len(oc_days) >= 2:
            details["oc_rms_min"] = float(_days_to_minutes(np.sqrt(np.mean(oc_days ** 2))))
            details["oc_std_min"] = float(np.std(_days_to_minutes(oc_days)))

        if len(oc_days) >= 3 and len(epochs) >= 3 and not np.allclose(epochs, epochs[0]):
            fit = stats.linregress(epochs, oc_days)
            epoch_span = float(np.max(epochs) - np.min(epochs))
            drift_min = float(_days_to_minutes(abs(fit.slope) * epoch_span))
            details["linear_slope_days_per_epoch"] = float(fit.slope)
            details["linear_intercept_days"] = float(fit.intercept)
            details["linear_rvalue"] = float(fit.rvalue)
            details["linear_pvalue"] = float(fit.pvalue)
            details["linear_total_drift_min"] = drift_min

        return details

    @staticmethod
    def _compute_score(
        tests: list[TimingTest],
    ) -> float:
        """
        Ağırlıklı timing anomaly skoru.

        FAIL = 1.0
        WARN = 0.4
        PASS = 0.0
        SKIP = dahil edilmez
        """

        weights = {
            "oc_rms": 0.40,
            "max_abs_oc": 0.25,
            "linear_ephemeris_trend": 0.35,
        }

        active = [t for t in tests if t.verdict != VettingVerdict.SKIP]
        if not active:
            return 0.0

        score_map = {
            VettingVerdict.FAIL: 1.0,
            VettingVerdict.WARN: 0.4,
            VettingVerdict.PASS: 0.0,
        }

        total = 0.0
        denom = 0.0

        for test in active:
            w = weights.get(test.name, 0.25)
            denom += w
            total += w * score_map.get(test.verdict, 0.0)

        if denom <= 0:
            return 0.0

        return float(np.clip(total / denom, 0.0, 1.0))

    @staticmethod
    def _compute_flag(
        tests: list[TimingTest],
        score: float,
        n_fail: int,
        n_warn: int,
    ) -> str:
        """
        Genel timing bayrağı.

        STABLE
            Düşük scatter, trend yok.
        TTV_CANDIDATE
            Scatter / outlier problemi var ama güçlü lineer drift yok.
        TIMING_UNSTABLE
            Güçlü lineer trend veya çoklu ağır timing sorunu var.
        UNKNOWN
            Aktif test yok.
        """

        active = [t for t in tests if t.verdict != VettingVerdict.SKIP]
        if not active:
            return "UNKNOWN"

        verdict_map = {t.name: t.verdict for t in tests}
        trend_verdict = verdict_map.get("linear_ephemeris_trend", VettingVerdict.SKIP)
        rms_verdict = verdict_map.get("oc_rms", VettingVerdict.SKIP)
        max_verdict = verdict_map.get("max_abs_oc", VettingVerdict.SKIP)

        if trend_verdict == VettingVerdict.FAIL or n_fail >= 2 or score >= 0.60:
            return "TIMING_UNSTABLE"

        if (
            rms_verdict in {VettingVerdict.WARN, VettingVerdict.FAIL}
            or max_verdict in {VettingVerdict.WARN, VettingVerdict.FAIL}
            or n_warn >= 2
            or score >= 0.25
        ):
            return "TTV_CANDIDATE"

        return "STABLE"