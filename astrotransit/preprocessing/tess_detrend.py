"""
TESS light curve detrending modülü.

Uzun dönem yıldız değişimlerini, enstrüman sistematiğini ve
diğer uzun periyotlu trendleri light curve'den ayırır.

Kullanılan kütüphane: wotan
Desteklenen yöntemler: biweight, cosine, spline, median
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
from loguru import logger

try:
    from wotan import flatten
    _WOTAN_AVAILABLE = True
except ImportError:
    _WOTAN_AVAILABLE = False
    logger.warning("wotan kütüphanesi bulunamadı. Detrending devre dışı.")

from astrotransit.preprocessing.cleaning import CleanedLightCurve


# ──────────────────────────────────────
# Detrending yöntemi seçenekleri
# ──────────────────────────────────────
class DetrendMethod(str, Enum):
    """Wotan ile desteklenen detrending yöntemleri."""

    BIWEIGHT = "biweight"       # Gürbüz, transit koruyucu
    COSINE = "cosine"           # Sinüs bazlı
    SPLINE = "spline"           # Spline fit
    MEDIAN = "median"           # Kayan medyan
    LOWESS = "lowess"           # Lokal ağırlıklı regresyon


# ──────────────────────────────────────
# Sonuç veri modeli
# ──────────────────────────────────────
@dataclass
class DetrendedLightCurve:
    """
    Trend giderilmiş light curve.

    Attributes
    ----------
    target_id : str
        Hedef TIC ID.
    sector : int
        Sektör numarası.
    time : np.ndarray
        Zaman dizisi (BTJD).
    flux : np.ndarray
        Trend giderilmiş (flatten) flux dizisi.
    flux_err : np.ndarray
        Hata dizisi (trend faktörüne göre ölçeklenmiş).
    trend : np.ndarray
        Fit edilmiş trend bileşeni.
    raw_flux : np.ndarray
        Trend giderilmeden önceki flux (referans için).
    method : str
        Kullanılan detrending yöntemi.
    window_length : float
        Kullanılan pencere genişliği (gün).
    break_tolerance : float
        Veri boşluk toleransı.
    meta : dict
        Ek metadata.
    """

    target_id: str
    sector: int
    time: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray
    trend: np.ndarray
    raw_flux: np.ndarray
    method: str
    window_length: float
    break_tolerance: float
    meta: dict = field(default_factory=dict)

    @property
    def n_points(self) -> int:
        return len(self.time)

    @property
    def residual_std(self) -> float:
        """Residual standart sapması (scatter göstergesi)."""
        residual = self.flux - 1.0
        return float(np.nanstd(residual))

    @property
    def residual_rms(self) -> float:
        """Residual RMS değeri."""
        residual = self.flux - 1.0
        return float(np.sqrt(np.nanmean(residual ** 2)))

    @property
    def noise_ppm(self) -> float:
        """Gürültü seviyesi (ppm cinsinden)."""
        return self.residual_std * 1e6

    def summary(self) -> dict:
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "method": self.method,
            "window_length_days": self.window_length,
            "n_points": self.n_points,
            "residual_std": round(self.residual_std, 8),
            "residual_rms": round(self.residual_rms, 8),
            "noise_ppm": round(self.noise_ppm, 2),
        }


@dataclass
class DetrendComparison:
    """
    Farklı detrending yöntemlerinin karşılaştırma sonuçları.

    Attributes
    ----------
    target_id : str
        Hedef TIC ID.
    sector : int
        Sektör numarası.
    results : dict[str, DetrendedLightCurve]
        Yöntem adı → sonuç eşleşmesi.
    best_method : str
        En düşük residual RMS'e sahip yöntem.
    """

    target_id: str
    sector: int
    results: dict[str, DetrendedLightCurve]
    best_method: str

    def summary(self) -> dict:
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "best_method": self.best_method,
            "method_scores": {
                name: round(res.residual_rms * 1e6, 2)
                for name, res in self.results.items()
            },
        }


# ──────────────────────────────────────
# Detrending sınıfı
# ──────────────────────────────────────
class TESSDetrending:
    """
    TESS light curve detrending motoru.

    wotan kütüphanesini kullanarak sistematik trendleri
    fotometrik zaman serilerinden ayırır.

    Transit geçişlerini korumak için pencere genişliği
    beklenen transit süresinden büyük ama yıldız aktivite
    ölçeğinden küçük seçilmelidir.

    Parameters
    ----------
    method : str veya DetrendMethod
        Detrending yöntemi.
    window_length : float
        Kayan pencere genişliği (gün).
        Tavsiye: 0.3–1.5 gün (transit süresi * 3 kadar).
    break_tolerance : float
        Veri boşluğu toleransı. Bu süreden uzun boşluklarda
        her parça bağımsız olarak detrend edilir.
    edge_cutoff : float
        Pencere kenarlarında kesilecek süre (gün).
    cval : float
        Biweight yöntemi için tuning parametresi.
    """

    def __init__(
        self,
        method: str | DetrendMethod = DetrendMethod.BIWEIGHT,
        window_length: float = 0.5,
        break_tolerance: float = 0.5,
        edge_cutoff: float = 0.0,
        cval: float = 5.0,
    ):
        if not _WOTAN_AVAILABLE:
            raise ImportError(
                "wotan kütüphanesi gereklidir: pip install wotan"
            )

        if isinstance(method, str):
            try:
                method = DetrendMethod(method.lower())
            except ValueError:
                raise ValueError(
                    f"Geçersiz detrending yöntemi: '{method}'. "
                    f"Desteklenenler: {[m.value for m in DetrendMethod]}"
                )

        self.method = method
        self.window_length = window_length
        self.break_tolerance = break_tolerance
        self.edge_cutoff = edge_cutoff
        self.cval = cval

        logger.debug(
            f"TESSDetrending — yöntem: {self.method.value}, "
            f"pencere: {window_length}d, "
            f"tolerans: {break_tolerance}d"
        )

    def detrend(self, cleaned: CleanedLightCurve) -> DetrendedLightCurve:
        """
        Temizlenmiş light curve üzerinde trend giderme uygular.

        Parameters
        ----------
        cleaned : CleanedLightCurve
            Temizlenmiş light curve.

        Returns
        -------
        DetrendedLightCurve
            Trend giderilmiş light curve.
        """

        logger.info(
            f"Detrending başlıyor — "
            f"{cleaned.target_id} sektör {cleaned.sector} "
            f"[{self.method.value}, pencere={self.window_length}d]"
        )

        time = cleaned.time.copy()
        flux = cleaned.flux.copy()
        flux_err = cleaned.flux_err.copy()

        # wotan flatten parametreleri
        flatten_kwargs = {
            "time": time,
            "flux": flux,
            "method": self.method.value,
            "window_length": self.window_length,
            "break_tolerance": self.break_tolerance,
            "return_trend": True,
        }

        # Biweight için ek parametreler
        if self.method == DetrendMethod.BIWEIGHT:
            flatten_kwargs["cval"] = self.cval

        # Edge kesme
        if self.edge_cutoff > 0:
            flatten_kwargs["edge_cutoff"] = self.edge_cutoff

        try:
            flattened_flux, trend = flatten(**flatten_kwargs)
        except Exception as e:
            raise RuntimeError(
                f"Detrending başarısız ({self.method.value}): {e}"
            ) from e

        # Trend sıfır veya nan olan noktaları temizle
        valid_mask = (
            np.isfinite(flattened_flux) &
            np.isfinite(trend) &
            (trend > 0)
        )

        if valid_mask.sum() < 50:
            raise ValueError(
                f"Detrending sonrası çok az geçerli nokta: {valid_mask.sum()}"
            )

        n_removed = (~valid_mask).sum()
        if n_removed > 0:
            logger.debug(f"Detrending sonrası {n_removed} nokta çıkarıldı.")

        # Hata ölçekleme: trend bileşenine göre orantılı
        # flux_err_detrended = flux_err / trend (trendin etkisini çıkar)
        trend_valid = trend[valid_mask]
        flux_err_detrended = flux_err[valid_mask] / trend_valid

        result = DetrendedLightCurve(
            target_id=cleaned.target_id,
            sector=cleaned.sector,
            time=time[valid_mask],
            flux=flattened_flux[valid_mask],
            flux_err=flux_err_detrended,
            trend=trend[valid_mask],
            raw_flux=flux[valid_mask],
            method=self.method.value,
            window_length=self.window_length,
            break_tolerance=self.break_tolerance,
            meta=cleaned.meta.copy(),
        )

        logger.info(
            f"Detrending tamamlandı — "
            f"gürültü: {result.noise_ppm:.1f} ppm, "
            f"residual RMS: {result.residual_rms:.6f}, "
            f"geçerli nokta: {result.n_points}"
        )

        return result

    def detrend_with_window_search(
        self,
        cleaned: CleanedLightCurve,
        window_candidates: Optional[list[float]] = None,
    ) -> DetrendedLightCurve:
        """
        Birden fazla pencere genişliğini dener ve en iyisini seçer.

        En düşük residual RMS veren pencere seçilir.

        Parameters
        ----------
        cleaned : CleanedLightCurve
            Temizlenmiş light curve.
        window_candidates : list[float], opsiyonel
            Test edilecek pencere genişlikleri (gün).
            Verilmezse varsayılan set kullanılır.

        Returns
        -------
        DetrendedLightCurve
            En iyi pencere genişliğiyle elde edilen sonuç.
        """

        if window_candidates is None:
            window_candidates = [0.3, 0.5, 0.75, 1.0, 1.5]

        logger.info(
            f"Pencere arama — {cleaned.target_id}: "
            f"{window_candidates}"
        )

        best_result = None
        best_rms = np.inf

        for window in window_candidates:
            try:
                detrend_copy = TESSDetrending(
                    method=self.method,
                    window_length=window,
                    break_tolerance=self.break_tolerance,
                    edge_cutoff=self.edge_cutoff,
                    cval=self.cval,
                )
                result = detrend_copy.detrend(cleaned)

                if result.residual_rms < best_rms:
                    best_rms = result.residual_rms
                    best_result = result

                logger.debug(
                    f"Pencere {window}d → RMS: {result.residual_rms:.6f}"
                )

            except Exception as e:
                logger.warning(f"Pencere {window}d denemesi başarısız: {e}")
                continue

        if best_result is None:
            raise RuntimeError(
                f"{cleaned.target_id}: hiçbir pencere genişliği başarılı olmadı."
            )

        logger.info(
            f"En iyi pencere: {best_result.window_length}d "
            f"(RMS: {best_rms:.6f})"
        )

        return best_result


class DetrendComparator:
    """
    Farklı detrending yöntemlerini karşılaştırır.

    Her yöntemi aynı veri üzerinde çalıştırır ve
    residual RMS'e göre en iyisini seçer.

    Parameters
    ----------
    methods : list[str], opsiyonel
        Test edilecek yöntemler.
    window_length : float
        Pencere genişliği (gün).
    break_tolerance : float
        Boşluk toleransı.
    """

    def __init__(
        self,
        methods: Optional[list[str]] = None,
        window_length: float = 0.5,
        break_tolerance: float = 0.5,
    ):
        if methods is None:
            methods = ["biweight", "cosine", "spline", "median"]

        self.methods = methods
        self.window_length = window_length
        self.break_tolerance = break_tolerance

    def compare(self, cleaned: CleanedLightCurve) -> DetrendComparison:
        """
        Tüm yöntemleri karşılaştırır ve en iyisini belirler.

        Parameters
        ----------
        cleaned : CleanedLightCurve
            Temizlenmiş light curve.

        Returns
        -------
        DetrendComparison
            Tüm yöntemlerin karşılaştırma sonuçları.
        """

        logger.info(
            f"Detrending karşılaştırması — "
            f"{cleaned.target_id}: {self.methods}"
        )

        results = {}
        best_method = None
        best_rms = np.inf

        for method_name in self.methods:
            try:
                detrend = TESSDetrending(
                    method=method_name,
                    window_length=self.window_length,
                    break_tolerance=self.break_tolerance,
                )
                result = detrend.detrend(cleaned)
                results[method_name] = result

                if result.residual_rms < best_rms:
                    best_rms = result.residual_rms
                    best_method = method_name

                logger.debug(
                    f"{method_name}: RMS = {result.residual_rms:.6f}, "
                    f"gürültü = {result.noise_ppm:.1f} ppm"
                )

            except Exception as e:
                logger.warning(f"Yöntem '{method_name}' başarısız: {e}")
                continue

        if not results:
            raise RuntimeError(
                f"{cleaned.target_id}: hiçbir detrending yöntemi başarılı olmadı."
            )

        comparison = DetrendComparison(
            target_id=cleaned.target_id,
            sector=cleaned.sector,
            results=results,
            best_method=best_method,
        )

        logger.info(
            f"En iyi yöntem: {best_method} "
            f"(RMS: {best_rms:.6f}, "
            f"gürültü: {results[best_method].noise_ppm:.1f} ppm)"
        )

        return comparison