"""
Işık eğrisi normalize etme modülü.

Ham flux değerlerini ortak bir ölçeğe getirir.
Birden fazla sektörü birleştirirken sektörler arası
sistematik farkları gidermek için kullanılır.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np
from loguru import logger

from astrotransit.data.tess_client import TESSLightCurveData, TESSMultiSectorData


# ──────────────────────────────────────
# Normalize yöntemi seçenekleri
# ──────────────────────────────────────
class NormalizationMethod(str, Enum):
    """Desteklenen normalize yöntemleri."""

    MEDIAN = "median"           # flux / median(flux)
    MEAN = "mean"               # flux / mean(flux)
    PERCENTILE = "percentile"   # flux / percentile(flux, q)
    ROBUST_MEAN = "robust_mean" # sigma kırpmalı ortalamaya böl


# ──────────────────────────────────────
# Sonuç veri modeli
# ──────────────────────────────────────
@dataclass
class NormalizedLightCurve:
    """
    Normalize edilmiş light curve.

    Attributes
    ----------
    target_id : str
        Hedef TIC ID.
    sector : int
        Sektör numarası.
    time : np.ndarray
        Zaman dizisi (BTJD).
    flux : np.ndarray
        Normalize edilmiş akı değerleri (ortalama ~1.0 civarı).
    flux_err : np.ndarray
        Normalize edilmiş akı hataları.
    norm_factor : float
        Normalizasyon için bölünen değer.
    method : str
        Kullanılan normalizasyon yöntemi.
    meta : dict
        Kaynak metadata.
    """

    target_id: str
    sector: int
    time: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray
    norm_factor: float
    method: str
    meta: dict

    @property
    def median_flux(self) -> float:
        """Normalize edilmiş flux'un medyanı (~1.0 olmalı)."""
        return float(np.nanmedian(self.flux))

    @property
    def flux_rms(self) -> float:
        """Flux RMS değeri."""
        return float(np.nanstd(self.flux))

    @property
    def n_points(self) -> int:
        """Veri noktası sayısı."""
        return len(self.time)

    def summary(self) -> dict:
        """Özet bilgileri sözlük olarak döndürür."""
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "method": self.method,
            "norm_factor": round(self.norm_factor, 6),
            "n_points": self.n_points,
            "median_flux": round(self.median_flux, 6),
            "flux_rms_ppm": round(self.flux_rms * 1e6, 2),
        }


@dataclass
class NormalizedMultiSector:
    """
    Birden fazla sektörden normalize edilmiş light curve koleksiyonu.

    Attributes
    ----------
    target_id : str
        Hedef TIC ID.
    sectors : list[NormalizedLightCurve]
        Sektör bazlı normalize veriler.
    """

    target_id: str
    sectors: list[NormalizedLightCurve]

    @property
    def n_sectors(self) -> int:
        return len(self.sectors)

    @property
    def combined_time(self) -> np.ndarray:
        """Tüm sektörlerin zaman dizilerini birleştirir (sıralı)."""
        if not self.sectors:
            return np.array([])
        combined = np.concatenate([s.time for s in self.sectors])
        return combined[np.argsort(combined)]

    @property
    def combined_flux(self) -> np.ndarray:
        """Tüm sektörlerin flux dizilerini zaman sırasıyla birleştirir."""
        if not self.sectors:
            return np.array([])
        times = [s.time for s in self.sectors]
        fluxes = [s.flux for s in self.sectors]
        all_time = np.concatenate(times)
        all_flux = np.concatenate(fluxes)
        sort_idx = np.argsort(all_time)
        return all_flux[sort_idx]

    @property
    def combined_flux_err(self) -> np.ndarray:
        """Tüm sektörlerin hata dizilerini zaman sırasıyla birleştirir."""
        if not self.sectors:
            return np.array([])
        times = [s.time for s in self.sectors]
        errs = [s.flux_err for s in self.sectors]
        all_time = np.concatenate(times)
        all_err = np.concatenate(errs)
        sort_idx = np.argsort(all_time)
        return all_err[sort_idx]


# ──────────────────────────────────────
# Normalize edici sınıf
# ──────────────────────────────────────
class LightCurveNormalizer:
    """
    Işık eğrisi normalize edicisi.

    Ham flux değerlerini birimin ortalama ~1.0 olduğu
    birimsiz formata dönüştürür.

    Parameters
    ----------
    method : str veya NormalizationMethod
        Kullanılacak normalizasyon yöntemi.
    percentile : float
        PERCENTILE yöntemi için yüzdelik dilim (0-100).
    sigma_clip : float
        ROBUST_MEAN yöntemi için sigma kırpma eşiği.
    """

    def __init__(
        self,
        method: str | NormalizationMethod = NormalizationMethod.MEDIAN,
        percentile: float = 95.0,
        sigma_clip: float = 3.0,
    ):
        if isinstance(method, str):
            try:
                method = NormalizationMethod(method.lower())
            except ValueError:
                raise ValueError(
                    f"Geçersiz normalizasyon yöntemi: '{method}'. "
                    f"Desteklenenler: {[m.value for m in NormalizationMethod]}"
                )

        self.method = method
        self.percentile = percentile
        self.sigma_clip = sigma_clip

        logger.debug(f"LightCurveNormalizer — yöntem: {self.method.value}")

    def _compute_norm_factor(self, flux: np.ndarray) -> float:
        """
        Flux dizisinden normalizasyon faktörünü hesaplar.

        Parameters
        ----------
        flux : np.ndarray
            Ham flux dizisi.

        Returns
        -------
        float
            Normalizasyon faktörü.
        """

        clean = flux[np.isfinite(flux) & (flux > 0)]

        if len(clean) == 0:
            raise ValueError("Normalizasyon için geçerli flux değeri yok.")

        if self.method == NormalizationMethod.MEDIAN:
            return float(np.median(clean))

        elif self.method == NormalizationMethod.MEAN:
            return float(np.mean(clean))

        elif self.method == NormalizationMethod.PERCENTILE:
            return float(np.percentile(clean, self.percentile))

        elif self.method == NormalizationMethod.ROBUST_MEAN:
            # Sigma kırpmalı ortalama
            median = np.median(clean)
            std = np.std(clean)
            mask = np.abs(clean - median) < self.sigma_clip * std
            if mask.sum() < 10:
                return float(median)
            return float(np.mean(clean[mask]))

        else:
            raise ValueError(f"Bilinmeyen yöntem: {self.method}")

    def normalize(self, data: TESSLightCurveData) -> NormalizedLightCurve:
        """
        Tek sektör light curve'ü normalize eder.

        Parameters
        ----------
        data : TESSLightCurveData
            Ham TESS light curve verisi.

        Returns
        -------
        NormalizedLightCurve
            Normalize edilmiş light curve.
        """

        logger.info(
            f"Normalize ediliyor — {data.target_id} sektör {data.sector} "
            f"({self.method.value})"
        )

        norm_factor = self._compute_norm_factor(data.flux)

        if norm_factor <= 0:
            raise ValueError(
                f"Normalizasyon faktörü sıfır veya negatif: {norm_factor}"
            )

        norm_flux = data.flux / norm_factor
        norm_flux_err = data.flux_err / norm_factor

        result = NormalizedLightCurve(
            target_id=data.target_id,
            sector=data.sector,
            time=data.time.copy(),
            flux=norm_flux,
            flux_err=norm_flux_err,
            norm_factor=norm_factor,
            method=self.method.value,
            meta=data.meta.copy(),
        )

        logger.info(
            f"Normalizasyon tamamlandı — "
            f"faktör: {norm_factor:.4f}, "
            f"normalize medyan: {result.median_flux:.6f}, "
            f"RMS: {result.flux_rms * 1e6:.1f} ppm"
        )

        return result

    def normalize_multi(self, multi: TESSMultiSectorData) -> NormalizedMultiSector:
        """
        Çok sektörlü veriyi sektör bazında normalize eder.

        Her sektör kendi normalizasyon faktörüyle işlenir.
        Bu yaklaşım sektörler arası sistematik offset'leri giderir.

        Parameters
        ----------
        multi : TESSMultiSectorData
            Çok sektörlü ham veri.

        Returns
        -------
        NormalizedMultiSector
            Normalize edilmiş çok sektörlü veri.
        """

        logger.info(
            f"Çok sektör normalizasyonu — {multi.target_id}: "
            f"{multi.n_sectors} sektör"
        )

        normalized_sectors = []

        for sector_data in multi.sectors:
            try:
                norm = self.normalize(sector_data)
                normalized_sectors.append(norm)
            except Exception as e:
                logger.warning(
                    f"Sektör {sector_data.sector} normalize edilemedi: {e}"
                )
                continue

        if not normalized_sectors:
            raise ValueError(
                f"{multi.target_id} için hiçbir sektör normalize edilemedi."
            )

        logger.info(
            f"Çok sektör normalizasyonu tamamlandı — "
            f"{len(normalized_sectors)}/{multi.n_sectors} sektör başarılı"
        )

        return NormalizedMultiSector(
            target_id=multi.target_id,
            sectors=normalized_sectors,
        )