"""Uzun periyotlu ve tek-transitli aday araması.

Bu arama, klasik BLS/TLS cascade'inden ayrı bir keşif kanalıdır. Özellikle
20--500 gün periyot aralığında tek bir transit gözlendiğinde periyot ve
gezegen doğrulanmış sayılmaz; sonuçlar açıkça ``single_transit`` olarak
etiketlenir ve follow-up önceliklendirmesine bırakılır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import astropy.units as u
from astropy.timeseries import BoxLeastSquares
import numpy as np
from loguru import logger

from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve


@dataclass(frozen=True)
class LongPeriodSearchConfig:
    """Uzun periyot BLS aramasının eşikleri."""

    min_period_days: float = 20.0
    max_period_days: float = 500.0
    min_power: float = 7.0
    min_depth: float = 1e-4
    max_depth: float = 0.5
    min_points_per_transit: int = 3
    n_durations: int = 8
    n_peaks: int = 5
    frequency_factor: float = 2.0

    def validate(self) -> None:
        if self.min_period_days <= 0 or self.max_period_days <= self.min_period_days:
            raise ValueError("Uzun periyot aralığı pozitif ve min < max olmalıdır.")
        if self.min_power <= 0 or not 0 < self.min_depth < self.max_depth:
            raise ValueError("Uzun periyot güç/derinlik eşikleri geçersiz.")
        if self.min_points_per_transit < 1:
            raise ValueError("min_points_per_transit en az 1 olmalıdır.")
        if self.n_durations < 1 or self.n_peaks < 1:
            raise ValueError("n_durations ve n_peaks en az 1 olmalıdır.")

    @classmethod
    def from_settings(cls, settings) -> "LongPeriodSearchConfig":
        cfg = settings.detection.long_period
        return cls(
            min_period_days=cfg.min_period_days,
            max_period_days=cfg.max_period_days,
            min_power=cfg.min_power,
            min_depth=cfg.min_depth,
            max_depth=cfg.max_depth,
            min_points_per_transit=cfg.min_points_per_transit,
            n_durations=cfg.n_durations,
            n_peaks=cfg.n_peaks,
        )


@dataclass
class LongPeriodPeak:
    """Uzun periyot taramasındaki tek bir BLS tepe noktası."""

    period: float
    period_err: float
    duration: float
    depth: float
    depth_err: float
    t0: float
    power: float
    snr: float
    n_observed_transits: int
    n_expected_transits: int
    n_transit_points: int
    transit_times: np.ndarray
    identifiability: str
    passed_threshold: bool = True
    reject_reason: str = ""

    @property
    def is_single_transit(self) -> bool:
        return self.n_observed_transits == 1

    def to_dict(self) -> dict:
        return {
            "period_days": round(self.period, 6),
            "period_err_days": round(self.period_err, 6),
            "duration_hours": round(self.duration * 24.0, 4),
            "depth_ppm": round(self.depth * 1e6, 3),
            "depth_err_ppm": round(self.depth_err * 1e6, 3),
            "t0_btjd": round(self.t0, 6),
            "power": round(self.power, 4),
            "snr": round(self.snr, 4),
            "n_observed_transits": self.n_observed_transits,
            "n_expected_transits": self.n_expected_transits,
            "n_transit_points": self.n_transit_points,
            "transit_times": [round(float(value), 6) for value in self.transit_times],
            "identifiability": self.identifiability,
            "passed_threshold": self.passed_threshold,
            "reject_reason": self.reject_reason,
        }


@dataclass
class LongPeriodResult:
    """Bir stitched light curve için uzun periyot arama sonucu."""

    target_id: str
    source_sectors: tuple[int, ...]
    coverage_baseline_days: float
    observed_days: float
    best: Optional[LongPeriodPeak]
    all_peaks: list[LongPeriodPeak]
    periods_searched: np.ndarray
    power_array: np.ndarray
    has_candidate: bool
    search_params: dict = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    @property
    def n_observed_transits(self) -> int:
        if self.best is None:
            return 0
        return self.best.n_observed_transits

    @property
    def identifiability(self) -> str:
        if self.best is None:
            return "none"
        return self.best.identifiability

    def summary(self) -> dict:
        result = {
            "target_id": self.target_id,
            "source_sectors": list(self.source_sectors),
            "coverage_baseline_days": round(self.coverage_baseline_days, 5),
            "observed_days": round(self.observed_days, 5),
            "has_candidate": self.has_candidate,
            "n_periods_searched": int(self.periods_searched.size),
            "n_peaks_found": len(self.all_peaks),
            "n_observed_transits": self.n_observed_transits,
            "identifiability": self.identifiability,
            "notes": list(self.notes),
        }
        if self.best is not None:
            result["best_peak"] = self.best.to_dict()
        return result


class LongPeriodTransitSearch:
    """Stitched TESS verisinde 20--500 gün BLS ve single-transit araması."""

    def __init__(
        self,
        config: Optional[LongPeriodSearchConfig] = None,
        *,
        stellar_radius_rsun: float = 1.0,
        stellar_mass_msun: float = 1.0,
    ):
        self.config = config or LongPeriodSearchConfig()
        self.config.validate()
        self.stellar_radius_rsun = float(stellar_radius_rsun) if stellar_radius_rsun > 0 else 1.0
        self.stellar_mass_msun = float(stellar_mass_msun) if stellar_mass_msun > 0 else 1.0

    def search(self, light_curve: DetrendedLightCurve) -> LongPeriodResult:
        """Uzun periyot aramasını çalıştırır.

        ``light_curve.meta`` içinde stitching provenance varsa source sectors
        ve gerçek gözlem süresi korunur. Tek sektör girdisi de desteklenir.
        """

        time, flux, error = self._clean_arrays(light_curve)
        source_sectors = self._source_sectors(light_curve)
        baseline_days = float(time[-1] - time[0]) if time.size > 1 else 0.0
        observed_days = self._observed_days(light_curve, time)
        notes: list[str] = []

        empty = lambda: LongPeriodResult(
            target_id=light_curve.target_id,
            source_sectors=source_sectors,
            coverage_baseline_days=baseline_days,
            observed_days=observed_days,
            best=None,
            all_peaks=[],
            periods_searched=np.array([], dtype=float),
            power_array=np.array([], dtype=float),
            has_candidate=False,
            search_params=self._search_params(),
            notes=tuple(notes),
        )

        if time.size < max(20, self.config.min_points_per_transit * 3):
            notes.append("Uzun periyot araması için yetersiz temiz veri noktası.")
            return empty()
        if baseline_days <= 0:
            notes.append("Gözlem zaman tabanı sıfır veya geçersiz.")
            return empty()
        if baseline_days < self.config.min_period_days:
            notes.append(
                "Gözlem zaman tabanı minimum arama periyodundan kısa; "
                "sonuçlar özellikle tek-transit açısından belirsizdir."
            )

        durations = self._duration_grid()
        periods = self._period_grid(time, durations)
        try:
            model = BoxLeastSquares(time * u.day, flux, dy=error)
            power_result = model.power(periods * u.day, durations * u.day, objective="snr")
        except Exception as exc:
            logger.warning(f"Uzun periyot BLS başarısız — {light_curve.target_id}: {exc}")
            notes.append(f"BLS hesaplama hatası: {exc}")
            return empty()

        period_values = np.asarray(power_result.period.value, dtype=float)
        power_values = np.asarray(power_result.power, dtype=float)
        peaks = self._build_peaks(model, power_result, time, flux, error)
        passed = [peak for peak in peaks if peak.passed_threshold]
        best = self._select_best(passed)
        if best is not None and best.is_single_transit:
            notes.append(
                "Tek transit bulundu: periyot kesinleşmiş değildir; "
                "follow-up veya ek TESS sektörü gereklidir."
            )
        if best is None:
            notes.append("Eşikleri geçen uzun periyot adayı bulunamadı.")

        return LongPeriodResult(
            target_id=light_curve.target_id,
            source_sectors=source_sectors,
            coverage_baseline_days=baseline_days,
            observed_days=observed_days,
            best=best,
            all_peaks=peaks,
            periods_searched=period_values,
            power_array=power_values,
            has_candidate=best is not None,
            search_params=self._search_params(),
            notes=tuple(notes),
        )

    def _clean_arrays(self, light_curve: DetrendedLightCurve) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        time = np.asarray(light_curve.time, dtype=float).reshape(-1)
        flux = np.asarray(light_curve.flux, dtype=float).reshape(-1)
        error = np.asarray(light_curve.flux_err, dtype=float).reshape(-1)
        if not (time.size == flux.size == error.size):
            raise ValueError("Long-period time/flux/flux_err uzunlukları eşit değil.")
        valid = np.isfinite(time) & np.isfinite(flux) & np.isfinite(error) & (error > 0)
        if not np.any(valid):
            raise ValueError("Long-period araması için geçerli veri yok.")
        time, flux, error = time[valid], flux[valid], error[valid]
        order = np.argsort(time, kind="mergesort")
        return time[order], flux[order], error[order]

    def _duration_grid(self) -> np.ndarray:
        # Merkezi, dairesel transit için yaklaşık fiziksel süre:
        # T ≈ (P/pi) * R_star / a. Yıldız parametreleri hedefe özgü süre
        # gridini belirler; ancak impact parameter ve eksantriklik bilinmediği
        # için grid fiziksel değerin etrafında geniş tutulur.
        physical_min = self._central_duration_days(self.config.min_period_days)
        physical_max = self._central_duration_days(self.config.max_period_days)
        lower = max(0.03, physical_min * 0.5)
        upper = min(3.0, max(physical_max * 2.0, lower * 2.0))
        if upper <= lower:
            upper = lower * 2.0
        return np.geomspace(lower, upper, self.config.n_durations)

    def _central_duration_days(self, period_days: float) -> float:
        semi_major_axis_au = (
            self.stellar_mass_msun * (period_days / 365.25) ** 2
        ) ** (1.0 / 3.0)
        stellar_radius_au = self.stellar_radius_rsun * 0.00465047
        return float(period_days / np.pi * stellar_radius_au / semi_major_axis_au)

    def _period_grid(self, time: np.ndarray, durations: np.ndarray) -> np.ndarray:
        try:
            model = BoxLeastSquares(time * u.day, np.ones(time.size))
            periods = model.autoperiod(
                durations * u.day,
                minimum_period=self.config.min_period_days * u.day,
                maximum_period=self.config.max_period_days * u.day,
                frequency_factor=self.config.frequency_factor,
            )
            values = np.asarray(periods.value, dtype=float)
            if values.size > 0 and np.all(np.isfinite(values)):
                if values.size > 12000:
                    keep = np.linspace(0, values.size - 1, 12000, dtype=int)
                    values = values[keep]
                return values
        except Exception as exc:
            logger.debug(f"Autoperiod grid oluşturulamadı, fallback kullanılacak: {exc}")

        # Geri dönüşte frekans uzayında eşit örnekleme, uzun periyotlarda
        # transit fazını lineer periyot gridinden daha iyi kapsar.
        n_grid = min(12000, max(1000, int(self.config.max_period_days * 8)))
        frequencies = np.linspace(
            1.0 / self.config.max_period_days,
            1.0 / self.config.min_period_days,
            n_grid,
        )
        return 1.0 / frequencies[::-1]

    @staticmethod
    def _select_best(peaks: list[LongPeriodPeak]) -> Optional[LongPeriodPeak]:
        if not peaks:
            return None
        identifiability_rank = {
            "multi_transit": 3,
            "multi_transit_gapped_ambiguous": 2,
            "single_transit_ambiguous": 1,
        }
        return max(
            peaks,
            key=lambda peak: (identifiability_rank.get(peak.identifiability, 0), peak.power),
        )

    def _build_peaks(self, model, power_result, time, flux, error) -> list[LongPeriodPeak]:
        powers = np.asarray(power_result.power, dtype=float)
        order = np.argsort(powers)[::-1]
        peaks: list[LongPeriodPeak] = []
        for index in order:
            if len(peaks) >= self.config.n_peaks:
                break
            period = float(power_result.period[index].value)
            if any(abs(period - prior.period) / period < 0.01 for prior in peaks):
                continue
            duration = float(power_result.duration[index].value)
            t0 = float(power_result.transit_time[index].value)
            stats = model.compute_stats(
                power_result.period[index],
                power_result.duration[index],
                power_result.transit_time[index],
            )
            depth = max(0.0, float(stats.get("depth", [0.0])[0]))
            depth_err = max(0.0, float(stats.get("depth", [0.0, 0.0])[1]))
            transit_times, n_points, n_expected = self._observed_events(
                time, t0, period, duration
            )
            n_events = len(transit_times)
            if n_events >= 2 and n_expected == n_events:
                identifiability = "multi_transit"
            elif n_events >= 2:
                identifiability = "multi_transit_gapped_ambiguous"
            else:
                identifiability = "single_transit_ambiguous"
            period_err = period * (0.02 if identifiability == "multi_transit" else 0.5)
            peak = LongPeriodPeak(
                period=period,
                period_err=period_err,
                duration=duration,
                depth=depth,
                depth_err=depth_err,
                t0=t0,
                power=float(powers[index]),
                snr=float(powers[index]),
                n_observed_transits=n_events,
                n_expected_transits=n_expected,
                n_transit_points=n_points,
                transit_times=np.asarray(transit_times, dtype=float),
                identifiability=identifiability,
            )
            self._evaluate_threshold(peak)
            peaks.append(peak)
        return peaks

    def _observed_events(
        self,
        time: np.ndarray,
        t0: float,
        period: float,
        duration: float,
    ) -> tuple[list[float], int, int]:
        if period <= 0 or duration <= 0:
            return [], 0, 0
        min_index = int(np.ceil((time[0] - duration / 2.0 - t0) / period))
        max_index = int(np.floor((time[-1] + duration / 2.0 - t0) / period))
        centers: list[float] = []
        n_points = 0
        n_expected = max(0, max_index - min_index + 1)
        for k in range(min_index, max_index + 1):
            center = t0 + k * period
            count = int(np.count_nonzero(np.abs(time - center) <= duration / 2.0))
            if count >= self.config.min_points_per_transit:
                centers.append(float(center))
                n_points += count
        return centers, n_points, n_expected

    def _evaluate_threshold(self, peak: LongPeriodPeak) -> None:
        reasons = []
        if not np.isfinite(peak.power) or peak.power < self.config.min_power:
            reasons.append(f"power={peak.power:.2f} < min={self.config.min_power}")
        if peak.depth < self.config.min_depth:
            reasons.append(f"depth={peak.depth:.2e} < min={self.config.min_depth:.2e}")
        if peak.depth > self.config.max_depth:
            reasons.append(f"depth={peak.depth:.4f} > max={self.config.max_depth}")
        if peak.n_observed_transits < 1:
            reasons.append("gözlenen transit yok")
        if reasons:
            peak.passed_threshold = False
            peak.reject_reason = " | ".join(reasons)
        else:
            peak.passed_threshold = True
            peak.reject_reason = ""

    def _source_sectors(self, light_curve: DetrendedLightCurve) -> tuple[int, ...]:
        raw = light_curve.meta.get("source_sectors") if light_curve.meta else None
        if raw:
            return tuple(int(value) for value in raw)
        return (int(light_curve.sector),)

    def _observed_days(self, light_curve: DetrendedLightCurve, time: np.ndarray) -> float:
        spans = light_curve.meta.get("sector_spans") if light_curve.meta else None
        if isinstance(spans, dict) and spans:
            return float(sum(float(end) - float(start) for start, end in spans.values()))
        return float(time[-1] - time[0]) if time.size > 1 else 0.0

    def _search_params(self) -> dict:
        return {
            "min_period_days": self.config.min_period_days,
            "max_period_days": self.config.max_period_days,
            "min_power": self.config.min_power,
            "min_depth": self.config.min_depth,
            "min_points_per_transit": self.config.min_points_per_transit,
            "n_durations": self.config.n_durations,
            "stellar_radius_rsun": self.stellar_radius_rsun,
            "stellar_mass_msun": self.stellar_mass_msun,
        }


__all__ = [
    "LongPeriodPeak",
    "LongPeriodResult",
    "LongPeriodSearchConfig",
    "LongPeriodTransitSearch",
]
