"""Çok sektörlü detrended light curve stitching yardımcıları.

Sektörleri tek bir zaman ekseninde birleştirmek, uzun periyotlu ve tek
transitli adayların yalnızca tek sektör bazında kaybolmasını önler. Bu modül
sektörler arasındaki fotometrik offset'i her sektörü robust medyanına bölerek
giderir; bunun bir transit veya atmosfer doğrulaması olmadığını metadata'da
korur.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve


@dataclass
class StitchedDetrendedLightCurve:
    """Birden fazla sektörün stitched ve provenance bilgili light curve'ü."""

    target_id: str
    time: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray
    sector_labels: np.ndarray
    source_sectors: tuple[int, ...]
    sector_normalization: dict[int, float]
    sector_spans: dict[int, tuple[float, float]]
    gap_indices: np.ndarray = field(default_factory=lambda: np.array([], dtype=int))
    gap_threshold_days: float = 0.5
    meta: dict = field(default_factory=dict)

    @property
    def sector(self) -> int:
        """Stitched kayıt için sentinel sektör numarası."""

        return -1

    @property
    def n_points(self) -> int:
        return int(self.time.size)

    @property
    def n_sectors(self) -> int:
        return len(self.source_sectors)

    @property
    def coverage_baseline_days(self) -> float:
        if self.time.size < 2:
            return 0.0
        return float(self.time[-1] - self.time[0])

    @property
    def observed_days(self) -> float:
        return float(
            sum(end - start for start, end in self.sector_spans.values() if end >= start)
        )

    @property
    def n_gaps(self) -> int:
        return int(self.gap_indices.size)

    def summary(self) -> dict:
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "source_sectors": list(self.source_sectors),
            "n_sectors": self.n_sectors,
            "n_points": self.n_points,
            "coverage_baseline_days": round(self.coverage_baseline_days, 5),
            "observed_days": round(self.observed_days, 5),
            "n_gaps": self.n_gaps,
            "gap_threshold_days": self.gap_threshold_days,
        }

    def as_detrended(self) -> DetrendedLightCurve:
        """Long-period detector ile uyumlu standart veri nesnesi döndürür."""

        return DetrendedLightCurve(
            target_id=self.target_id,
            sector=self.sector,
            time=self.time.copy(),
            flux=self.flux.copy(),
            flux_err=self.flux_err.copy(),
            trend=np.ones_like(self.flux),
            raw_flux=self.flux.copy(),
            method="stitched_median",
            window_length=0.0,
            break_tolerance=self.gap_threshold_days,
            meta={
                **self.meta,
                "source_sectors": list(self.source_sectors),
                "sector_labels": self.sector_labels.copy(),
                "sector_spans": dict(self.sector_spans),
                "coverage_baseline_days": self.coverage_baseline_days,
                "observed_days": self.observed_days,
            },
        )


def stitch_detrended_light_curves(
    curves: Sequence[DetrendedLightCurve] | Iterable[DetrendedLightCurve],
    *,
    gap_threshold_days: float = 0.5,
) -> StitchedDetrendedLightCurve:
    """Sektör bazlı detrended light curve'leri tek eksende birleştirir.

    Her sektör ayrı robust medyanına bölünür. Zamanlar sıralanır, aynı zaman
    damgaları inverse-variance ağırlığıyla tek noktaya indirilir ve sektör
    etiketleri kaybedilmez. Sektörlerin hedef kimliği aynı olmalıdır.
    """

    if gap_threshold_days <= 0:
        raise ValueError("gap_threshold_days pozitif olmalıdır.")

    curve_list = list(curves)
    if not curve_list:
        raise ValueError("Stitching için en az bir light curve gereklidir.")

    target_ids = {str(curve.target_id) for curve in curve_list}
    if len(target_ids) != 1:
        raise ValueError(f"Farklı hedefler aynı stitched light curve'e alınamaz: {sorted(target_ids)}")
    target_id = target_ids.pop()

    times: list[np.ndarray] = []
    fluxes: list[np.ndarray] = []
    errors: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    normalizations: dict[int, float] = {}
    spans: dict[int, tuple[float, float]] = {}
    source_sectors: list[int] = []

    for curve in curve_list:
        sector = int(curve.sector)
        time = np.asarray(curve.time, dtype=float).reshape(-1)
        flux = np.asarray(curve.flux, dtype=float).reshape(-1)
        error = np.asarray(curve.flux_err, dtype=float).reshape(-1)
        if not (time.size == flux.size == error.size):
            raise ValueError(f"Sektör {sector}: time/flux/flux_err uzunlukları eşit değil.")

        valid = np.isfinite(time) & np.isfinite(flux) & (flux > 0)
        if not np.any(valid):
            continue
        time = time[valid]
        flux = flux[valid]
        error = error[valid] if error.size else np.full(time.size, np.nan)

        order = np.argsort(time, kind="mergesort")
        time = time[order]
        flux = flux[order]
        error = error[order]
        baseline = float(np.nanmedian(flux))
        if not np.isfinite(baseline) or baseline <= 0:
            raise ValueError(f"Sektör {sector}: pozitif robust flux medyanı bulunamadı.")

        norm_flux = flux / baseline
        norm_error = np.abs(error / baseline)
        valid_error = np.isfinite(norm_error) & (norm_error > 0)
        fallback_error = float(np.nanmedian(norm_error[valid_error])) if np.any(valid_error) else 0.0
        if not np.isfinite(fallback_error) or fallback_error <= 0:
            fallback_error = max(float(np.nanstd(norm_flux - 1.0)), 1e-6)
        norm_error = np.where(valid_error, norm_error, fallback_error)

        source_sectors.append(sector)
        normalizations[sector] = baseline
        spans[sector] = (float(time[0]), float(time[-1]))
        times.append(time)
        fluxes.append(norm_flux)
        errors.append(norm_error)
        labels.append(np.full(time.size, sector, dtype=int))

    if not times:
        raise ValueError("Stitching sonrası kullanılabilir veri kalmadı.")

    all_time = np.concatenate(times)
    all_flux = np.concatenate(fluxes)
    all_error = np.concatenate(errors)
    all_labels = np.concatenate(labels)
    order = np.argsort(all_time, kind="mergesort")
    all_time = all_time[order]
    all_flux = all_flux[order]
    all_error = all_error[order]
    all_labels = all_labels[order]

    time, flux, error, sector_labels = _collapse_duplicate_times(
        all_time, all_flux, all_error, all_labels
    )
    gaps = np.flatnonzero(np.diff(time) > gap_threshold_days) + 1

    ordered_sectors = tuple(sorted(set(source_sectors), key=lambda value: spans[value][0]))
    return StitchedDetrendedLightCurve(
        target_id=target_id,
        time=time,
        flux=flux,
        flux_err=error,
        sector_labels=sector_labels,
        source_sectors=ordered_sectors,
        sector_normalization=normalizations,
        sector_spans=spans,
        gap_indices=gaps.astype(int),
        gap_threshold_days=gap_threshold_days,
        meta={"source_sector_count": len(ordered_sectors)},
    )


def _collapse_duplicate_times(
    time: np.ndarray,
    flux: np.ndarray,
    error: np.ndarray,
    labels: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Aynı zaman damgalarını inverse-variance ağırlığıyla birleştirir."""

    if time.size == 0:
        return time, flux, error, labels
    unique, first, counts = np.unique(time, return_index=True, return_counts=True)
    if np.all(counts == 1):
        return time, flux, error, labels

    combined_flux = np.empty(unique.size, dtype=float)
    combined_error = np.empty(unique.size, dtype=float)
    combined_labels = np.empty(unique.size, dtype=int)
    for index, (start, count) in enumerate(zip(first, counts)):
        stop = start + count
        weights = 1.0 / np.maximum(error[start:stop], 1e-12) ** 2
        combined_flux[index] = float(np.average(flux[start:stop], weights=weights))
        combined_error[index] = float(np.sqrt(1.0 / np.sum(weights)))
        combined_labels[index] = int(labels[start])
    return unique, combined_flux, combined_error, combined_labels


__all__ = ["StitchedDetrendedLightCurve", "stitch_detrended_light_curves"]
