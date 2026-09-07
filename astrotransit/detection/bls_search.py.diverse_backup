"""
BLS (Box Least Squares) transit arama modülü.

Kovacs, Zucker & Mazeh (2002) metodolojisini temel alır.
astropy.timeseries.BoxLeastSquares implementasyonu kullanılır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from astropy.timeseries import BoxLeastSquares
import astropy.units as u
from loguru import logger

from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve
from astrotransit.detection.thresholds import BLSThresholds


# ──────────────────────────────────────
# Sonuç veri modelleri
# ──────────────────────────────────────
@dataclass
class BLSPeak:
    """Tek bir BLS periyodogram tepe noktası."""

    period: float
    period_err: float
    duration: float
    depth: float
    t0: float
    power: float
    snr: float
    depth_err: float
    n_transits: int
    transit_times: np.ndarray
    passed_threshold: bool = True
    reject_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "period": round(self.period, 6),
            "period_err": round(self.period_err, 6),
            "duration_hours": round(self.duration * 24, 4),
            "depth_ppm": round(self.depth * 1e6, 2),
            "depth_err_ppm": round(self.depth_err * 1e6, 2),
            "t0": round(self.t0, 6),
            "power": round(self.power, 4),
            "snr": round(self.snr, 4),
            "n_transits": self.n_transits,
            "passed_threshold": self.passed_threshold,
            "reject_reason": self.reject_reason,
        }


@dataclass
class BLSResult:
    """BLS arama sonuçları."""

    target_id: str
    sector: int
    best: Optional[BLSPeak]
    all_peaks: list[BLSPeak]
    periods_searched: np.ndarray
    power_array: np.ndarray
    n_periods_searched: int
    has_candidate: bool
    search_params: dict = field(default_factory=dict)

    def summary(self) -> dict:
        base = {
            "target_id": self.target_id,
            "sector": self.sector,
            "has_candidate": self.has_candidate,
            "n_periods_searched": self.n_periods_searched,
            "n_peaks_found": len(self.all_peaks),
        }
        if self.best is not None:
            base["best_peak"] = self.best.to_dict()
        return base


# ──────────────────────────────────────
# BLS arama sınıfı
# ──────────────────────────────────────
class BLSSearch:
    """BLS transit arama motoru."""

    def __init__(
        self,
        thresholds: Optional[BLSThresholds] = None,
        n_durations: int = 20,
        frequency_factor: float = 2.0,
        n_peaks: int = 5,
    ):
        self.thresholds = thresholds or BLSThresholds()
        self.n_durations = n_durations
        self.frequency_factor = frequency_factor
        self.n_peaks = n_peaks

        self.thresholds.validate()

        logger.debug(
            f"BLSSearch — "
            f"periyot: [{self.thresholds.min_period_days}, "
            f"{self.thresholds.max_period_days}]d, "
            f"min_power: {self.thresholds.min_power}, "
            f"n_durations: {n_durations}"
        )

    def _build_duration_grid(self) -> np.ndarray:
        return np.linspace(
            self.thresholds.min_duration_days,
            self.thresholds.max_duration_days,
            self.n_durations,
        )

    def _compute_n_transits(
        self,
        period: float,
        t0: float,
        time_start: float,
        time_end: float,
    ) -> int:
        if period <= 0:
            return 0
        duration_days = time_end - time_start
        n = int(duration_days / period) + 1
        return max(0, n)

    def _compute_transit_times(
        self,
        t0: float,
        period: float,
        time_start: float,
        time_end: float,
    ) -> np.ndarray:
        if period <= 0:
            return np.array([t0])
        n_max = int((time_end - time_start) / period) + 2
        times = t0 + np.arange(-n_max, n_max + 1) * period
        mask = (times >= time_start) & (times <= time_end)
        return times[mask]

    def _estimate_snr(
        self,
        depth: float,
        depth_err: float,
        n_transits: int,
    ) -> float:
        if depth_err <= 0 or n_transits <= 0:
            return 0.0
        return float(depth / depth_err * np.sqrt(n_transits))

    def _evaluate_threshold(self, peak: BLSPeak) -> BLSPeak:
        reasons = []

        if peak.power < self.thresholds.min_power:
            reasons.append(
                f"power={peak.power:.2f} < min={self.thresholds.min_power}"
            )
        if peak.depth < self.thresholds.min_depth:
            reasons.append(
                f"depth={peak.depth:.2e} < min={self.thresholds.min_depth:.2e}"
            )
        if peak.depth > self.thresholds.max_depth:
            reasons.append(
                f"depth={peak.depth:.4f} > max={self.thresholds.max_depth} (EB şüphesi)"
            )
        if peak.duration < self.thresholds.min_duration_days:
            reasons.append(
                f"duration={peak.duration * 24:.2f}h < "
                f"min={self.thresholds.min_duration_days * 24:.2f}h"
            )
        if peak.duration > self.thresholds.max_duration_days:
            reasons.append(
                f"duration={peak.duration * 24:.2f}h > "
                f"max={self.thresholds.max_duration_days * 24:.2f}h"
            )
        if peak.n_transits < self.thresholds.min_transits:
            reasons.append(
                f"n_transits={peak.n_transits} < min={self.thresholds.min_transits}"
            )

        if reasons:
            peak.passed_threshold = False
            peak.reject_reason = " | ".join(reasons)
        else:
            peak.passed_threshold = True
            peak.reject_reason = ""

        return peak

    def search(self, detrended: DetrendedLightCurve) -> BLSResult:
        """Trend giderilmiş light curve üzerinde BLS taraması yapar."""

        target_id = detrended.target_id
        sector = detrended.sector

        logger.info(
            f"BLS taraması başlıyor — "
            f"{target_id} sektör {sector}: "
            f"{detrended.n_points} nokta"
        )

        time = detrended.time
        flux = detrended.flux
        flux_err = detrended.flux_err

        if len(time) < 100:
            logger.warning(
                f"{target_id} sektör {sector}: "
                f"BLS için yetersiz nokta ({len(time)})"
            )
            return self._empty_result(target_id, sector)

        durations = self._build_duration_grid()

        bls_model = BoxLeastSquares(
            time * u.day,
            flux,
            dy=flux_err,
        )

        period_grid = bls_model.autoperiod(
            durations * u.day,
            minimum_period=self.thresholds.min_period_days * u.day,
            maximum_period=self.thresholds.max_period_days * u.day,
            frequency_factor=self.frequency_factor,
        )

        n_periods = len(period_grid)

        logger.debug(
            f"BLS periyot ızgarası: {n_periods} periyot, "
            f"[{period_grid[0].value:.3f}, {period_grid[-1].value:.3f}] gün"
        )

        try:
            result = bls_model.power(
                period_grid,
                durations * u.day,
                objective="snr",
            )
        except Exception as e:
            logger.error(f"BLS güç hesaplama başarısız: {e}")
            return self._empty_result(target_id, sector)

        periods_arr = np.array(result.period.value)
        power_arr = np.array(result.power)

        sorted_idx = np.argsort(power_arr)[::-1]
        top_indices = sorted_idx[: self.n_peaks]

        all_peaks = []

        for idx in top_indices:
            try:
                stats = bls_model.compute_stats(
                    result.period[idx],
                    result.duration[idx],
                    result.transit_time[idx],
                )
            except Exception as e:
                logger.debug(f"BLS istatistik hesaplama başarısız indeks {idx}: {e}")
                continue

            period_val = float(result.period[idx].value)
            duration_val = float(result.duration[idx].value)
            t0_val = float(result.transit_time[idx].value)
            depth_val = float(stats["depth"][0]) if "depth" in stats else 0.0
            depth_err_val = float(stats["depth"][1]) if "depth" in stats else 0.0
            power_val = float(power_arr[idx])

            if idx > 0 and idx < len(periods_arr) - 1:
                period_err = abs(periods_arr[idx + 1] - periods_arr[idx - 1]) / 2.0
            else:
                period_err = period_val * 0.001

            n_transits = self._compute_n_transits(
                period_val, t0_val,
                float(time[0]), float(time[-1])
            )

            transit_times = self._compute_transit_times(
                t0_val, period_val,
                float(time[0]), float(time[-1])
            )

            snr = self._estimate_snr(depth_val, depth_err_val, n_transits)

            peak = BLSPeak(
                period=period_val,
                period_err=period_err,
                duration=duration_val,
                depth=max(0.0, depth_val),
                t0=t0_val,
                power=power_val,
                snr=snr,
                depth_err=depth_err_val,
                n_transits=n_transits,
                transit_times=transit_times,
            )

            peak = self._evaluate_threshold(peak)
            all_peaks.append(peak)

        passed_peaks = [p for p in all_peaks if p.passed_threshold]
        best_peak = passed_peaks[0] if passed_peaks else None
        has_candidate = best_peak is not None

        if has_candidate:
            logger.info(
                f"BLS aday tespit edildi — "
                f"{target_id} sektör {sector}: "
                f"P={best_peak.period:.4f}d, "
                f"derinlik={best_peak.depth * 1e6:.0f}ppm, "
                f"güç={best_peak.power:.2f}, "
                f"SNR={best_peak.snr:.2f}"
            )
        else:
            reject_info = all_peaks[0].reject_reason if all_peaks else "sinyal yok"
            logger.info(
                f"BLS: aday bulunamadı — "
                f"{target_id} sektör {sector} "
                f"({reject_info})"
            )

        return BLSResult(
            target_id=target_id,
            sector=sector,
            best=best_peak,
            all_peaks=all_peaks,
            periods_searched=periods_arr,
            power_array=power_arr,
            n_periods_searched=n_periods,
            has_candidate=has_candidate,
            search_params={
                "min_period": self.thresholds.min_period_days,
                "max_period": self.thresholds.max_period_days,
                "n_durations": self.n_durations,
                "min_power": self.thresholds.min_power,
                "frequency_factor": self.frequency_factor,
            },
        )

    def _empty_result(self, target_id: str, sector: int) -> BLSResult:
        return BLSResult(
            target_id=target_id,
            sector=sector,
            best=None,
            all_peaks=[],
            periods_searched=np.array([]),
            power_array=np.array([]),
            n_periods_searched=0,
            has_candidate=False,
        )